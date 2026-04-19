"""
Call manager — orchestrates the full call lifecycle.

Responsibilities:
  • Trigger an outbound Twilio call (pre-generates greeting before dialing)
  • Build the opening-greeting TwiML (instant response on call answer)
  • Build each turn's TwiML (transcribe → LLM → TTS → Record loop)
  • Finalise the call record (fast — just writes ended_at + transcript)
  • post_call_processing() — background task for memory extraction + mood scoring
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

from config import get_settings
from models.user import Call, User
from services import escalation as escalation_service
from services import llm as llm_service
from services import memory_service
from services import mood as mood_service
from services import stt as stt_service
from services import tts as tts_service

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_TURNS = 12
SILENCE_TIMEOUT = 6
MAX_RECORD_SECONDS = 60
MOOD_ALERT_THRESHOLD = 0.35   # flag if mood drops below this vs baseline


# ---------------------------------------------------------------------------
# Outbound call trigger
# ---------------------------------------------------------------------------

async def trigger_outbound_call(user: User, db: AsyncSession) -> str:
    """
    Pre-generate the greeting (memories → LLM → TTS) BEFORE dialing so the
    webhook can respond instantly and never hit Twilio's 15-second timeout.
    """
    from datetime import date

    call_record = Call(
        user_id=user.id,
        started_at=datetime.utcnow(),
        messages=[],
        turn_count=0,
    )
    db.add(call_record)
    await db.commit()
    await db.refresh(call_record)

    # For the opening, use recent memories so Aria follows up on the last call.
    # During the call, cosine search is used for contextual retrieval.
    memories = await memory_service.get_recent_memories(user.id, db)
    call_record.retrieved_memories = memories or None

    # Fetch previous call's opening so Aria doesn't repeat the same follow-up topic
    prev_result = await db.execute(
        select(Call)
        .where(Call.user_id == user.id, Call.id != call_record.id, Call.messages.isnot(None))
        .order_by(Call.started_at.desc())
        .limit(1)
    )
    prev_call = prev_result.scalars().first()
    prev_opening = None
    if prev_call and prev_call.messages:
        first_msg = prev_call.messages[0] if prev_call.messages else None
        if first_msg and first_msg.get("role") == "assistant":
            prev_opening = first_msg["content"]

    # Generate opening LLM response
    llm_resp = await llm_service.generate_opening(user.name, memories=memories, prev_opening=prev_opening)
    call_record.messages = [{"role": "assistant", "content": llm_resp.text}]

    # Synthesise TTS audio
    filename = await tts_service.synthesise(llm_resp.text)
    call_record.greeting_audio = filename
    await db.commit()
    logger.info(f"Greeting pre-generated: {filename}")

    # Dial
    webhook_url = f"{settings.base_url.rstrip('/')}/calls/webhook/{user.id}"
    status_url = f"{settings.base_url.rstrip('/')}/calls/status/{call_record.id}"

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    call = client.calls.create(
        to=user.phone_number,
        from_=settings.twilio_phone_number,
        url=webhook_url,
        status_callback=status_url,
        status_callback_event=["completed", "failed", "busy", "no-answer"],
        status_callback_method="POST",
    )

    call_record.twilio_call_sid = call.sid
    await db.commit()

    logger.info(f"Outbound call created  sid={call.sid}  to={user.phone_number}")
    return call.sid


# ---------------------------------------------------------------------------
# Opening greeting
# ---------------------------------------------------------------------------

async def build_opening_greeting(
    user: User, call: Call, db: AsyncSession
) -> VoiceResponse:
    """Play pre-generated greeting and open first <Record>. Responds in ms."""
    filename = call.greeting_audio
    if not filename:
        logger.warning(f"No pre-generated greeting for call={call.id}, generating now.")
        memories = call.retrieved_memories or ""
        llm_resp = await llm_service.generate_opening(user.name, memories=memories)
        messages = list(call.messages or [])
        messages.append({"role": "assistant", "content": llm_resp.text})
        call.messages = messages
        await db.commit()
        filename = await tts_service.synthesise(llm_resp.text)

    play_url = tts_service.audio_url(filename)
    turn_url = _turn_url(user.id, call.id)

    twiml = VoiceResponse()
    twiml.play(play_url)
    twiml.record(
        action=turn_url,
        method="POST",
        timeout=SILENCE_TIMEOUT,
        max_length=MAX_RECORD_SECONDS,
        play_beep=False,
        transcribe=False,
    )
    twiml.redirect(turn_url, method="POST")
    return twiml


# ---------------------------------------------------------------------------
# Per-turn handler
# ---------------------------------------------------------------------------

async def build_turn_response(
    user: User,
    call: Call,
    recording_url: str,
    db: AsyncSession,
) -> VoiceResponse:
    auth = None
    if settings.twilio_account_sid and settings.twilio_auth_token:
        auth = (settings.twilio_account_sid, settings.twilio_auth_token)

    # Save recording for mood analysis later
    turn_num = (call.turn_count or 0) + 1
    recording_save_path = _recording_path(call.id, turn_num)

    transcript = await stt_service.transcribe_url(
        recording_url, twilio_auth=auth, save_path=recording_save_path
    )
    logger.info(f"User said: '{transcript}'  (call={call.id}  turn={turn_num})")

    # Detect user-initiated goodbye so Aria wraps up naturally
    _goodbye_phrases = {"bye", "goodbye", "good bye", "talk later", "got to go", "gotta go", "take care", "have a good day"}
    user_said_bye = any(phrase in transcript.lower() for phrase in _goodbye_phrases) if transcript else False

    messages = list(call.messages or [])
    if transcript:
        messages.append({"role": "user", "content": transcript})

    call.turn_count = turn_num

    memories = call.retrieved_memories or ""
    llm_resp = await llm_service.chat(messages, user_name=user.name, memories=memories)
    logger.info(f"Aria: '{llm_resp.text}'  end={llm_resp.should_end}  escalate={llm_resp.should_escalate}")

    messages.append({"role": "assistant", "content": llm_resp.text})
    call.messages = messages

    if llm_resp.should_escalate:
        call.flagged = True
        if user.family_phone:
            escalation_service.send_sms(
                user.family_phone, user.name,
                "They mentioned something concerning during their call."
            )

    await db.commit()

    filename = await tts_service.synthesise(llm_resp.text)
    play_url = tts_service.audio_url(filename)

    twiml = VoiceResponse()
    twiml.play(play_url)

    # Don't end mid-conversation if Aria just asked a question
    ends_with_question = llm_resp.text.rstrip().endswith("?")
    should_hang_up = (
        (llm_resp.should_end and not ends_with_question)
        or user_said_bye
        or call.turn_count >= MAX_TURNS
    )

    if should_hang_up:
        if not llm_resp.should_end:
            farewell = await tts_service.synthesise(
                f"It was so lovely talking with you today, {user.name}. "
                "Take care, and I'll call again soon."
            )
            twiml.play(tts_service.audio_url(farewell))
        twiml.hangup()
    else:
        turn_url = _turn_url(user.id, call.id)
        twiml.record(
            action=turn_url,
            method="POST",
            timeout=SILENCE_TIMEOUT,
            max_length=MAX_RECORD_SECONDS,
            play_beep=False,
            transcribe=False,
        )
        twiml.redirect(turn_url, method="POST")

    return twiml


# ---------------------------------------------------------------------------
# Finalise call (fast — called synchronously in status callback)
# ---------------------------------------------------------------------------

async def finalise_call(call: Call, db: AsyncSession) -> None:
    """Write ended_at and flatten transcript. Heavy work runs in background."""
    call.ended_at = datetime.utcnow()

    messages = call.messages or []
    lines = [
        f"{'Aria' if m['role'] == 'assistant' else 'User'}: {m['content']}"
        for m in messages
    ]
    call.transcript = "\n".join(lines)
    await db.commit()
    logger.info(f"Call finalised  id={call.id}  turns={call.turn_count}")


# ---------------------------------------------------------------------------
# Post-call processing (background task — owns its own DB session)
# ---------------------------------------------------------------------------

async def post_call_processing(call_id: uuid.UUID) -> None:
    """
    Runs after a call ends as a FastAPI BackgroundTask.
    Uses its own DB session — safe to run after the HTTP response is sent.

    1. Memory extraction (LLM fact extraction + pgvector storage)
    2. Mood scoring (librosa features + baseline comparison)
    3. SMS escalation if mood drops significantly below baseline
    """
    from db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        call = await db.get(Call, call_id)
        if not call:
            logger.warning(f"post_call_processing: call {call_id} not found.")
            return

        user = await db.get(User, call.user_id)

        # 1. Memory extraction
        if call.transcript:
            await memory_service.extract_and_store_memories(
                call.user_id, call.id, call.transcript, db
            )

        # 2. Mood scoring
        await _score_and_save_mood(call, user, db)


async def _score_and_save_mood(call: Call, user: User | None, db: AsyncSession) -> None:
    """Find per-turn recordings, extract features, compute score, persist."""
    recordings_dir = os.path.join(settings.audio_dir, "recordings")
    if not os.path.isdir(recordings_dir):
        logger.info("No recordings directory — skipping mood scoring.")
        return

    # Collect all recordings saved for this call, in turn order
    prefix = str(call.id)
    recording_files = sorted([
        os.path.join(recordings_dir, f)
        for f in os.listdir(recordings_dir)
        if f.startswith(prefix) and f.endswith(".wav")
    ])

    if not recording_files:
        logger.info(f"No recordings found for call={call.id} — skipping mood.")
        return

    MIN_TURNS_FOR_MOOD = 3
    if (call.turn_count or 0) < MIN_TURNS_FOR_MOOD:
        logger.info(f"Call too short ({call.turn_count} turns) — skipping mood scoring.")
        return

    # Concatenate into one file
    combined_path = os.path.join(recordings_dir, f"{call.id}_combined.wav")
    ok = await mood_service.concatenate_recordings(recording_files, combined_path)
    if not ok:
        logger.warning(f"Could not concatenate recordings for call={call.id}.")
        return

    try:
        features = await mood_service.extract_audio_features(combined_path)

        # Commit features first so the baseline query sees this call's data,
        # then exclude this call from the baseline window so it isn't self-referential.
        call.mood_features = features
        await db.commit()

        # Run acoustic scoring and transcript sentiment in parallel
        baseline_task = mood_service.get_user_baseline(call.user_id, db, exclude_call_id=call.id)
        sentiment_task = mood_service.analyze_transcript_sentiment(call.transcript or "")
        baseline, sentiment = await asyncio.gather(baseline_task, sentiment_task)

        score, contradiction = mood_service.compute_mood_score(features, baseline, sentiment)

        call.mood_score = score
        call.mood_delta = round(score - 0.5, 3)
        call.sentiment_score = sentiment.get("sentiment_score")
        call.emotional_state = sentiment.get("emotional_state")
        call.masking_detected = sentiment.get("masking_detected", False)
        call.contradiction_flag = contradiction

        # Escalate on significant mood dip (only once we have a real baseline)
        if baseline is not None and score < MOOD_ALERT_THRESHOLD:
            call.flagged = True
            if user and user.family_phone:
                escalation_service.send_sms(
                    user.family_phone,
                    user.name if user else "the user",
                    f"Their mood score today was {score:.2f}, notably lower than their recent baseline.",
                )

        await db.commit()
        logger.info(f"Mood scored  call={call.id}  score={score}  baseline={'yes' if baseline else 'building'}")
    finally:
        # Clean up individual turn recordings; keep combined for audit if needed
        for p in recording_files:
            try:
                os.remove(p)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _turn_url(user_id: uuid.UUID, call_id: uuid.UUID) -> str:
    return f"{settings.base_url.rstrip('/')}/calls/turn/{user_id}/{call_id}"


def _recording_path(call_id: uuid.UUID, turn: int) -> str:
    recordings_dir = os.path.join(settings.audio_dir, "recordings")
    return os.path.join(recordings_dir, f"{call_id}_{turn:03d}.wav")
