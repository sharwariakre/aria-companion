"""
Twilio webhook router — handles the full voice call loop.

Flow:
  1. POST /calls/webhook/{user_id}      → call answered, play opening greeting
  2. POST /calls/turn/{user_id}/{call_id} → user recording ready, transcribe → LLM → TTS → loop
  3. POST /calls/status/{call_id}        → Twilio call-status callback (completed / failed)
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.twiml.voice_response import VoiceResponse

from config import get_settings
from db.database import get_db
from models.user import Call, Memory, User
from services.call_manager import (
    build_opening_greeting,
    build_turn_response,
    finalise_call,
    post_call_processing,
)

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Dashboard endpoint — last 7 calls for a user
# ---------------------------------------------------------------------------

@router.get("/{user_id}")
async def get_calls(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return last 7 calls for the dashboard status card and history."""
    result = await db.execute(
        select(
            Call.id, Call.started_at, Call.ended_at,
            Call.turn_count, Call.mood_score, Call.flagged, Call.summary,
            Call.emotional_state, Call.masking_detected, Call.contradiction_flag,
        )
        .where(Call.user_id == user_id)
        .order_by(Call.started_at.desc())
        .limit(7)
    )
    rows = result.all()
    return [
        {
            "call_id": str(r.id),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "duration_seconds": (
                int((r.ended_at - r.started_at).total_seconds())
                if r.started_at and r.ended_at else None
            ),
            "turn_count": r.turn_count,
            "mood_score": r.mood_score,
            "flagged": r.flagged,
            "summary": r.summary,
            "emotional_state": r.emotional_state,
            "masking_detected": r.masking_detected or False,
            "contradiction_flag": r.contradiction_flag or False,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Full call report — single call with transcript, mood features, memories
# ---------------------------------------------------------------------------

@router.get("/{user_id}/{call_id}")
async def get_call_report(
    user_id: uuid.UUID,
    call_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return a full JSON report for a single call."""
    call = await db.get(Call, call_id)
    if not call or call.user_id != user_id:
        raise HTTPException(status_code=404, detail="Call not found")

    # Fetch memories extracted from this call
    mem_result = await db.execute(
        select(Memory.content, Memory.created_at)
        .where(Memory.source_call_id == call_id)
        .order_by(Memory.created_at.asc())
    )
    memories = [{"content": r.content, "created_at": r.created_at.isoformat()} for r in mem_result.all()]

    duration = (
        int((call.ended_at - call.started_at).total_seconds())
        if call.started_at and call.ended_at else None
    )

    return {
        "call_id": str(call.id),
        "twilio_call_sid": call.twilio_call_sid,
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "duration_seconds": duration,
        "turn_count": call.turn_count,
        "flagged": call.flagged,
        "summary": call.summary,
        "mood": {
            "score": call.mood_score,
            "delta": call.mood_delta,
            "features": call.mood_features,
            "sentiment_score": call.sentiment_score,
            "emotional_state": call.emotional_state,
            "masking_detected": call.masking_detected or False,
            "contradiction_flag": call.contradiction_flag or False,
        },
        "transcript": call.transcript,
        "messages": call.messages,
        "retrieved_memories": call.retrieved_memories,
        "extracted_memories": memories,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _twiml_response(twiml: VoiceResponse) -> Response:
    return Response(content=str(twiml), media_type="application/xml")


# ---------------------------------------------------------------------------
# 1. Call answered — play greeting, open first Record
# ---------------------------------------------------------------------------

@router.post("/webhook/{user_id}")
async def call_webhook(
    user_id: uuid.UUID,
    request: Request,
    CallSid: str = Form(...),
    CallStatus: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    logger.info(f"Call answered for user={user_id}  sid={CallSid}  status={CallStatus}")

    # Load user
    user = await db.get(User, user_id)
    if not user:
        twiml = VoiceResponse()
        twiml.say("Sorry, I could not find your profile. Goodbye.")
        twiml.hangup()
        return _twiml_response(twiml)

    # Create (or locate) DB call record — trigger_call.py pre-creates one and
    # stores the call_sid so we can find it here.
    result = await db.execute(
        select(Call)
        .where(Call.user_id == user_id, Call.twilio_call_sid == CallSid)
    )
    call = result.scalars().first()

    if not call:
        call = Call(
            user_id=user_id,
            twilio_call_sid=CallSid,
            started_at=datetime.utcnow(),
            messages=[],
            turn_count=0,
        )
        db.add(call)
        await db.commit()
        await db.refresh(call)

    # Generate opening TTS audio
    twiml = await build_opening_greeting(user, call, db)
    return _twiml_response(twiml)


# ---------------------------------------------------------------------------
# 2. Recording ready — transcribe, run LLM, speak response, loop
# ---------------------------------------------------------------------------

@router.post("/turn/{user_id}/{call_id}")
async def call_turn(
    user_id: uuid.UUID,
    call_id: uuid.UUID,
    request: Request,
    CallSid: str = Form(...),
    RecordingUrl: str = Form(default=""),
    RecordingStatus: str = Form(default=""),
    RecordingDuration: str = Form(default="0"),
    Digits: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    logger.info(
        f"Turn received  user={user_id}  call={call_id}  "
        f"recording_status={RecordingStatus}  duration={RecordingDuration}s"
    )

    user = await db.get(User, user_id)
    call = await db.get(Call, call_id)

    if not user or not call:
        twiml = VoiceResponse()
        twiml.say("Something went wrong. Goodbye.")
        twiml.hangup()
        return _twiml_response(twiml)

    twiml = await build_turn_response(
        user=user,
        call=call,
        recording_url=RecordingUrl,
        db=db,
    )
    return _twiml_response(twiml)


# ---------------------------------------------------------------------------
# 3. Call-status callback — mark call ended in DB
# ---------------------------------------------------------------------------

@router.post("/status/{call_id}")
async def call_status(
    call_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    CallDuration: str = Form(default="0"),
    db: AsyncSession = Depends(get_db),
):
    logger.info(f"Call status update  call={call_id}  status={CallStatus}")

    if CallStatus in ("completed", "failed", "busy", "no-answer", "canceled"):
        call = await db.get(Call, call_id)
        if call and not call.ended_at:
            await finalise_call(call, db)
            # Memory extraction + mood scoring run after we respond to Twilio
            background_tasks.add_task(post_call_processing, call_id)

    return Response(status_code=204)
