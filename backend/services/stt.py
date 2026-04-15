"""
Whisper STT service using faster-whisper.

The model is loaded once at module import (lazy, on first use) so the
cold-start penalty only happens on the first transcription request.
"""

import asyncio
import logging
import os
import tempfile
from functools import lru_cache

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model singleton
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_model():
    from faster_whisper import WhisperModel

    logger.info("Loading Whisper base.en model (first-time load)…")
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    logger.info("Whisper model ready.")
    return model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def transcribe_url(recording_url: str, twilio_auth: tuple[str, str] | None = None) -> str:
    """
    Download a Twilio recording URL (or any accessible audio URL) and
    transcribe it with Whisper.  Returns the transcription string, or an
    empty string if the audio could not be fetched / transcribed.

    Twilio recording URLs require HTTP Basic Auth
    (account_sid, auth_token) unless you've opened them publicly.
    """
    if not recording_url:
        return ""

    # Twilio appends no extension — request .wav explicitly for best compat
    url = recording_url if recording_url.endswith((".wav", ".mp3")) else recording_url + ".wav"

    logger.info(f"Downloading recording: {url}")
    audio_bytes = await _download_with_retry(url, auth=twilio_auth)
    if not audio_bytes:
        logger.warning("Recording download returned empty body.")
        return ""

    return await asyncio.to_thread(_transcribe_bytes, audio_bytes)


def _transcribe_bytes(audio_bytes: bytes) -> str:
    """Synchronous transcription — runs in a thread pool via asyncio.to_thread."""
    model = _get_model()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, info = model.transcribe(
            tmp_path,
            beam_size=5,
            language="en",
            vad_filter=True,             # filter out silence/noise
            vad_parameters={"min_silence_duration_ms": 500},
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        logger.info(f"Transcription ({info.language}, {info.duration:.1f}s): '{text}'")
        return text
    finally:
        os.unlink(tmp_path)


async def _download_with_retry(
    url: str,
    auth: tuple[str, str] | None = None,
    retries: int = 5,
    backoff: float = 1.5,
) -> bytes:
    """Download audio with exponential backoff — Twilio recordings can take
    a moment to become available after the action webhook fires."""
    import asyncio

    delay = 1.0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(retries):
            try:
                resp = await client.get(url, auth=auth)
                if resp.status_code == 200:
                    return resp.content
                logger.warning(
                    f"Recording download attempt {attempt + 1}/{retries} "
                    f"returned HTTP {resp.status_code}"
                )
            except httpx.RequestError as exc:
                logger.warning(f"Download attempt {attempt + 1} error: {exc}")

            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay *= backoff

    return b""
