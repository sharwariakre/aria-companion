import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import get_settings
from db.database import init_db
from routers import calls, memory

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initialising database…")
    await init_db()

    audio_dir = settings.audio_dir
    os.makedirs(audio_dir, exist_ok=True)
    logger.info(f"Audio directory ready at {audio_dir}")

    await _prewarm_models()
    logger.info("All models loaded — Aria is ready to take calls.")

    yield

    # Shutdown (nothing special needed for Phase 1)
    logger.info("Shutting down Aria backend")


app = FastAPI(
    title="Aria Companion API",
    description="Proactive voice companion for elderly people living alone",
    version="0.1.0",
    lifespan=lifespan,
)

# Serve TTS audio files so Twilio can play them via <Play>
audio_dir = get_settings().audio_dir
os.makedirs(audio_dir, exist_ok=True)
app.mount("/audio", StaticFiles(directory=audio_dir), name="audio")

app.include_router(calls.router, prefix="/calls", tags=["calls"])
app.include_router(memory.router, prefix="/memory", tags=["memory"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "aria"}
