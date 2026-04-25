import asyncio
import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import get_settings
from db.database import init_db
from routers import calls, memory, mood, users

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


async def _prewarm_models():
    """Load Whisper and Kokoro into memory at startup so the first call
    doesn't time out waiting for model downloads / initialisation."""
    import asyncio
    from services.stt import _get_model as get_whisper
    from services.tts import _get_pipeline as get_kokoro

    logger.info("Pre-warming Whisper STT model…")
    await asyncio.to_thread(get_whisper)
    logger.info("Whisper ready.")

    logger.info("Pre-warming Kokoro TTS pipeline…")
    await asyncio.to_thread(get_kokoro)
    logger.info("Kokoro ready.")

    from services.memory_service import _get_embedder as get_embedder
    logger.info("Pre-warming sentence-transformer embedding model…")
    await asyncio.to_thread(get_embedder)
    logger.info("Embedding model ready.")


async def _reconcile_open_calls():
    """On startup, close any calls that never received a Twilio status callback."""
    from datetime import timedelta
    from sqlalchemy import select
    from db.database import AsyncSessionLocal
    from models.user import Call
    from twilio.rest import Client

    async with AsyncSessionLocal() as db:
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        result = await db.execute(
            select(Call).where(
                Call.ended_at.is_(None),
                Call.twilio_call_sid.isnot(None),
                Call.started_at < cutoff,
            )
        )
        open_calls = result.scalars().all()

    if not open_calls:
        return

    logger.info(f"Reconciling {len(open_calls)} open call(s) with Twilio...")
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

    for call in open_calls:
        try:
            twilio_call = client.calls(call.twilio_call_sid).fetch()
            status = twilio_call.status
            duration = int(twilio_call.duration or 0)
            logger.info(f"Reconcile call={call.id}  status={status}  duration={duration}s")

            async with AsyncSessionLocal() as db:
                call = await db.get(Call, call.id)
                if not call or call.ended_at:
                    continue

                has_conversation = bool(call.messages and len(call.messages) > 1)
                is_missed = (
                    status in ("no-answer", "busy", "failed", "canceled")
                    or (status == "completed" and duration < 30 and not has_conversation)
                )

                if is_missed:
                    call.ended_at = datetime.utcnow()
                    await db.commit()
                    from services.missed_call import handle_missed_call
                    await handle_missed_call(call.id, call.user_id)
                elif status == "completed":
                    from services.call_manager import finalise_call, post_call_processing
                    await finalise_call(call, db)
                    asyncio.create_task(post_call_processing(call.id))
                else:
                    call.ended_at = datetime.utcnow()
                    await db.commit()
        except Exception as exc:
            logger.warning(f"Reconcile failed for call={call.id}: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initialising database…")
    await init_db()

    audio_dir = settings.audio_dir
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(os.path.join(audio_dir, "recordings"), exist_ok=True)
    logger.info(f"Audio directory ready at {audio_dir}")

    await _prewarm_models()
    logger.info("All models loaded — Aria is ready to take calls.")

    await _reconcile_open_calls()

    from services.scheduler import scheduler, schedule_all_users
    await schedule_all_users()
    scheduler.start()
    logger.info("Scheduler started.")

    yield

    scheduler.shutdown()
    logger.info("Shutting down Aria backend")


app = FastAPI(
    title="Aria Companion API",
    description="Proactive voice companion for elderly people living alone",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "PATCH", "POST"],
    allow_headers=["*"],
)

# Serve TTS audio files so Twilio can play them via <Play>
audio_dir = get_settings().audio_dir
os.makedirs(audio_dir, exist_ok=True)
app.mount("/audio", StaticFiles(directory=audio_dir), name="audio")

app.include_router(calls.router, prefix="/calls", tags=["calls"])
app.include_router(memory.router, prefix="/memory", tags=["memory"])
app.include_router(mood.router, prefix="/mood", tags=["mood"])
app.include_router(users.router, prefix="/users", tags=["users"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "aria"}
