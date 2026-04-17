"""
Call manager — orchestrates the full call lifecycle.

Responsibilities:
  • Trigger an outbound Twilio call
  • Build the opening-greeting TwiML (on call answer)
  • Build each turn's TwiML (transcribe → LLM → TTS → Record loop)
  • Finalise the call record in the database
  • Trigger an SMS escalation when the LLM sets the ESCALATE flag
"""

import logging
import uuid
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

from config import get_settings
from models.user import Call, User
from services import llm as llm_service
from services import memory_service
from services import stt as stt_service
from services import tts as tts_service

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_TURNS = 12          # end call after this many exchanges
SILENCE_TIMEOUT = 6    # seconds of silence before Twilio stops recording
MAX_RECORD_SECONDS = 60 # max seconds per user turn


# ---------------------------------------------------------------------------
# Outbound call trigger
# ---------------------------------------------------------------------------

async def trigger_outbound_call(user: User, db: AsyncSession) -> str:
    """
    Create a Twilio outbound call to the user.
    Pre-creates a Call DB record and passes the call_id in the webhook URL
    so we can find the record when Twilio hits the webhook.

    Returns the Twilio call SID.
    """
    call_record = Call(
        user_id=user.id,
        started_at=datetime.utcnow(),
        messages=[],
        turn_count=0,
    )
    db.add(call_record)
    await db.commit()
    await db.refresh(call_record)

    webhook_url = (
        f"{settings.base_url.rstrip('/')}/calls/webhook/{user.id}"
    )
    status_url = (
        f"{settings.base_url.rstrip('/')}/calls/status/{call_record.id}"
    )

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    call = client.calls.create(
        to=user.phone_number,
        from_=settings.twilio_phone_number,
        url=webhook_url,
        status_callback=status_url,
        status_callback_event=["completed", "failed", "busy", "no-answer"],
        status_callback_method="POST",
    )

    # Store the Twilio SID so the webhook can locate this record
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
    """
    Generate the opening greeting TTS audio and return TwiML that plays it
    then opens the first <Record> to capture the user's response.
    """
    from datetime import date

    # Retrieve relevant memories and inject into system prompt
    context = f"Today is {date.today().strftime('%A, %B %d %Y')}. Calling {user.name}."
    memories = await memory_service.get_relevant_memories(user.id, context, db)
    call.retrieved_memories = memories or None

    llm_resp = await llm_service.generate_opening(user.name, memories=memories)

    # Persist first assistant turn
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
    # Fallback if <Record> gets no audio at all
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
    """
    1. Download & transcribe the user's recording.
    2. Append user turn to conversation history.
    3. Call Ollama for a response.
    4. Synthesise response audio.
    5. Return TwiML: <Play> + <Record> (or <Hangup> if conversation ends).
    """
    # --- Transcribe ---
    auth = None
    if settings.twilio_account_sid and settings.twilio_auth_token:
        auth = (settings.twilio_account_sid, settings.twilio_auth_token)

    transcript = await stt_service.transcribe_url(recording_url, twilio_auth=auth)
    logger.info(f"User said: '{transcript}'  (call={call.id})")

    messages = list(call.messages or [])

    if transcript:
        messages.append({"role": "user", "content": transcript})

    call.turn_count = (call.turn_count or 0) + 1

    # --- LLM — pass through memories that were fetched at call start ---
    memories = call.retrieved_memories or ""
    llm_resp = await llm_service.chat(messages, user_name=user.name, memories=memories)
    logger.info(f"Aria says: '{llm_resp.text}'  end={llm_resp.should_end}  escalate={llm_resp.should_escalate}")

    messages.append({"role": "assistant", "content": llm_resp.text})
    call.messages = messages

    # --- Persist ---
    if llm_resp.should_escalate:
        call.flagged = True
    await db.commit()

    # --- TTS ---
    filename = await tts_service.synthesise(llm_resp.text)
    play_url = tts_service.audio_url(filename)

    # --- Build TwiML ---
    twiml = VoiceResponse()
    twiml.play(play_url)

    should_hang_up = (
        llm_resp.should_end
        or call.turn_count >= MAX_TURNS
        or not transcript  # user said nothing after a prompt
    )

    if should_hang_up:
        if not llm_resp.should_end:
            # Max turns reached gracefully
            farewell = await tts_service.synthesise(
                f"It was so lovely talking with you today, {user.name}. Take care, and I'll call again soon."
            )
            twiml.play(tts_service.audio_url(farewell))

        twiml.hangup()

        # Trigger SMS alert asynchronously (don't block the TwiML response)
        if llm_resp.should_escalate and user.family_phone:
            _send_escalation_sms(user)
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
# Finalise call record
# ---------------------------------------------------------------------------

async def finalise_call(call: Call, db: AsyncSession) -> None:
    """Write ended_at, flatten the transcript, then extract and store memories."""
    call.ended_at = datetime.utcnow()

    messages = call.messages or []
    lines = []
    for msg in messages:
        speaker = "Aria" if msg["role"] == "assistant" else "User"
        lines.append(f"{speaker}: {msg['content']}")
    call.transcript = "\n".join(lines)

    await db.commit()
    logger.info(f"Call finalised  id={call.id}  turns={call.turn_count}")

    # Extract facts from the transcript and store as embeddings for future calls
    if call.transcript:
        await memory_service.extract_and_store_memories(
            user_id=call.user_id,
            call_id=call.id,
            transcript=call.transcript,
            db=db,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _turn_url(user_id: uuid.UUID, call_id: uuid.UUID) -> str:
    return f"{settings.base_url.rstrip('/')}/calls/turn/{user_id}/{call_id}"


def _send_escalation_sms(user: User) -> None:
    """Fire-and-forget SMS to family member via Twilio."""
    try:
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        client.messages.create(
            to=user.family_phone,
            from_=settings.twilio_phone_number,
            body=(
                f"Aria alert: {user.name} may need a check-in. "
                "They mentioned something during their daily call that warrants attention. "
                "Please reach out to them soon."
            ),
        )
        logger.info(f"Escalation SMS sent to {user.family_phone}")
    except Exception as exc:
        logger.error(f"SMS escalation failed: {exc}")
