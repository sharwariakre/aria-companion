"""
Kokoro TTS service.

Synthesises text to a WAV file and returns the filename (relative to the
audio directory) so FastAPI's static file mount can serve it to Twilio.

The Kokoro pipeline is loaded once at module import (lazy).
"""

import asyncio
import logging
import os
import uuid
from functools import lru_cache

import numpy as np
import soundfile as sf

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SAMPLE_RATE = 24_000   # Kokoro's native sample rate
VOICE = "af_heart"     # warm American English female voice


# ---------------------------------------------------------------------------
# Pipeline singleton
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_pipeline():
    from kokoro import KPipeline  # type: ignore

    logger.info("Loading Kokoro TTS pipeline…")
    pipeline = KPipeline(lang_code="a")   # 'a' = American English
    logger.info("Kokoro TTS ready.")
    return pipeline


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def synthesise(text: str, speed: float = 0.88) -> str:
    """
    Convert `text` to speech and save it to the audio directory.

    Returns the **filename** (e.g. ``"abc123.wav"``) that can be appended
    to ``{BASE_URL}/audio/`` to form a playable URL for Twilio.
    """
    filename = f"{uuid.uuid4().hex}.wav"
    output_path = os.path.join(settings.audio_dir, filename)
    os.makedirs(settings.audio_dir, exist_ok=True)

    await asyncio.to_thread(_synthesise_sync, text, output_path, speed)
    logger.info(f"TTS audio saved: {output_path}")
    return filename


def audio_url(filename: str) -> str:
    """Return the public URL Twilio will use to play this file."""
    return f"{settings.base_url.rstrip('/')}/audio/{filename}"


# ---------------------------------------------------------------------------
# Synchronous implementation (run in thread pool)
# ---------------------------------------------------------------------------

def _synthesise_sync(text: str, output_path: str, speed: float) -> None:
    pipeline = _get_pipeline()

    chunks: list[np.ndarray] = []
    generator = pipeline(text, voice=VOICE, speed=speed, split_pattern=r"(?<=[.!?])\s+")

    for _, _, audio in generator:
        if audio is not None and len(audio) > 0:
            chunks.append(audio)

    if not chunks:
        # Silence fallback — 0.5 s of silence so Twilio doesn't hang
        audio_data = np.zeros(int(SAMPLE_RATE * 0.5), dtype=np.float32)
    else:
        audio_data = np.concatenate(chunks)

    sf.write(output_path, audio_data, SAMPLE_RATE, subtype="PCM_16")
