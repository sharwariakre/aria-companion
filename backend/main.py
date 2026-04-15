import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import get_settings
from db.database import init_db
from routers import calls

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initialising database…")
    await init_db()

    audio_dir = settings.audio_dir
    os.makedirs(audio_dir, exist_ok=True)
    logger.info(f"Audio directory ready at {audio_dir}")

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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "aria"}
