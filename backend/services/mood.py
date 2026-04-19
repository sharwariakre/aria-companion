"""
Mood signals service — Phase 3.

Two signal sources fused into a single score:
  1. Acoustic features (librosa) — energy, pitch, speech rate, pause ratio
  2. Transcript sentiment (Ollama LLM) — emotional_state, masking_detected

Final score = 0.4 * acoustic + 0.6 * sentiment.
contradiction_flag is set when the two sources differ by more than 0.4.
"""

import asyncio
import json
import logging
import os
import re
import uuid
from typing import Optional

import httpx
import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Lazy librosa import
# ---------------------------------------------------------------------------

def _librosa():
    import librosa  # noqa: PLC0415
    return librosa


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

async def extract_audio_features(audio_path: str) -> dict:
    """Extract acoustic features from a WAV file. Runs in a thread pool."""
    return await asyncio.to_thread(_extract_sync, audio_path)


def _extract_sync(audio_path: str) -> dict:
    lib = _librosa()

    try:
        y, sr = lib.load(audio_path, sr=None, mono=True)
    except Exception as exc:
        logger.error(f"Could not load audio {audio_path}: {exc}")
        return _empty_features()

    if len(y) == 0 or sr == 0:
        return _empty_features()

    duration = len(y) / sr

    # --- Energy ---
    rms = lib.feature.rms(y=y)[0]
    energy = float(np.mean(rms))

    # --- Pitch (YIN) ---
    try:
        pitches = lib.yin(y, fmin=75, fmax=300)
        voiced = pitches[(pitches > 75) & (pitches < 300)]
        pitch_mean = float(np.mean(voiced)) if len(voiced) > 0 else 0.0
        pitch_std = float(np.std(voiced)) if len(voiced) > 0 else 0.0
    except Exception:
        pitch_mean = 0.0
        pitch_std = 0.0

    # --- Speech rate (voiced frames per second) ---
    voiced_frames = int(np.sum(rms > 0.01))
    speech_rate = float(voiced_frames / duration) if duration > 0 else 0.0

    # --- Pause ratio ---
    total_frames = len(rms)
    silent_frames = int(np.sum(rms < 0.01))
    pause_ratio = float(silent_frames / total_frames) if total_frames > 0 else 0.5

    features = {
        "energy": round(energy, 6),
        "pitch_mean": round(pitch_mean, 2),
        "pitch_std": round(pitch_std, 2),
        "speech_rate": round(speech_rate, 4),
        "pause_ratio": round(pause_ratio, 4),
        "duration_seconds": round(duration, 2),
    }
    logger.info(f"Extracted audio features: {features}")
    return features


def _empty_features() -> dict:
    return {
        "energy": 0.0,
        "pitch_mean": 0.0,
        "pitch_std": 0.0,
        "speech_rate": 0.0,
        "pause_ratio": 1.0,
        "duration_seconds": 0.0,
    }


# ---------------------------------------------------------------------------
# Transcript sentiment analysis
# ---------------------------------------------------------------------------

_SENTIMENT_PROMPT = """\
Analyze the emotional state of the user (the person being called — not Aria) \
in this phone call transcript.

Respond with a JSON object only. No explanation, no markdown fences, just raw JSON.

{{
  "sentiment_score": <float 0.0–1.0 — 0.0 = very distressed, 0.5 = neutral, 1.0 = very positive>,
  "emotional_state": <one word — choose from: cheerful, content, neutral, tired, anxious, sad, distressed>,
  "masking_detected": <true if the user seems to be downplaying negative feelings or saying they are fine when the conversation suggests otherwise>,
  "reasoning": <one sentence explaining your assessment>
}}

Transcript:
{transcript}"""


async def analyze_transcript_sentiment(transcript: str) -> dict:
    """
    Ask Ollama to assess the emotional content of a call transcript.
    Returns a dict with sentiment_score, emotional_state, masking_detected, reasoning.
    Falls back to neutral defaults on any error.
    """
    _default = {
        "sentiment_score": 0.5,
        "emotional_state": "neutral",
        "masking_detected": False,
        "reasoning": "Sentiment analysis unavailable.",
    }

    if not transcript or not transcript.strip():
        return _default

    prompt = _SENTIMENT_PROMPT.format(transcript=transcript)

    try:
        async with httpx.AsyncClient(
            base_url=settings.ollama_base_url, timeout=120.0
        ) as client:
            resp = await client.post(
                "/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()
    except Exception as exc:
        logger.error(f"Sentiment analysis LLM call failed: {exc}")
        return _default

    # Strip markdown fences if the model wraps the JSON anyway
    raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try extracting the first {...} block
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning(f"Could not parse sentiment JSON: {raw[:200]}")
                return _default
        else:
            logger.warning(f"No JSON found in sentiment response: {raw[:200]}")
            return _default

    result = {
        "sentiment_score": float(data.get("sentiment_score", 0.5)),
        "emotional_state": str(data.get("emotional_state", "neutral")).lower(),
        "masking_detected": bool(data.get("masking_detected", False)),
        "reasoning": str(data.get("reasoning", "")),
    }
    result["sentiment_score"] = max(0.0, min(1.0, result["sentiment_score"]))
    logger.info(f"Sentiment: {result}")
    return result


# ---------------------------------------------------------------------------
# Mood scoring
# ---------------------------------------------------------------------------

def compute_mood_score(
    features: dict,
    baseline: Optional[dict],
    sentiment: Optional[dict] = None,
) -> tuple[float, bool]:
    """
    Returns (combined_score, contradiction_flag).

    combined_score: 0.0–1.0
      - If sentiment available: 0.4 * acoustic + 0.6 * sentiment_score
      - If no sentiment:        acoustic score only
      - If no baseline:         sentiment_score (or 0.5 if no sentiment either)

    contradiction_flag: True when acoustic and sentiment scores differ by > 0.4
    """
    acoustic_score = _compute_acoustic_score(features, baseline)
    sentiment_score = sentiment.get("sentiment_score", 0.5) if sentiment else None

    if sentiment_score is None:
        return acoustic_score, False

    combined = round(acoustic_score * 0.4 + sentiment_score * 0.6, 3)
    contradiction = abs(acoustic_score - sentiment_score) > 0.4
    return combined, contradiction


def _compute_acoustic_score(features: dict, baseline: Optional[dict]) -> float:
    """
    Acoustic-only score 0.0–1.0 relative to the user's personal baseline.
    Returns 0.5 when no baseline is available.
    """
    if not baseline:
        return 0.5

    def delta_score(val: float, base: float, sensitivity: float = 1.5) -> float:
        if base <= 0:
            return 0.5
        pct = (val - base) / base
        return max(0.0, min(1.0, 0.5 + pct * sensitivity * 0.5))

    energy_score = delta_score(features.get("energy", 0),      baseline.get("energy", 0))
    pitch_score  = delta_score(features.get("pitch_mean", 0),  baseline.get("pitch_mean", 1), sensitivity=1.0)
    speech_score = delta_score(features.get("speech_rate", 0), baseline.get("speech_rate", 0))
    pause_score  = 1.0 - delta_score(features.get("pause_ratio", 0.5), baseline.get("pause_ratio", 0.5))

    score = (
        energy_score * 0.35
        + pitch_score  * 0.25
        + speech_score * 0.25
        + pause_score  * 0.15
    )
    return round(max(0.0, min(1.0, score)), 3)


# ---------------------------------------------------------------------------
# Baseline query
# ---------------------------------------------------------------------------

async def get_user_baseline(
    user_id: uuid.UUID,
    db: AsyncSession,
    exclude_call_id: Optional[uuid.UUID] = None,
) -> Optional[dict]:
    """
    Average mood_features from the user's last 2 completed calls (excluding the
    current call). Returns None if fewer than 2 prior calls with features exist.
    Requiring only 2 prior calls means the 3rd real call gets the first score.
    """
    result = await db.execute(
        text("""
            SELECT mood_features
            FROM calls
            WHERE user_id       = :user_id
              AND mood_features IS NOT NULL
              AND ended_at      IS NOT NULL
              AND id            != :exclude_id
            ORDER BY ended_at DESC
            LIMIT 3
        """),
        {
            "user_id": str(user_id),
            "exclude_id": str(exclude_call_id) if exclude_call_id else "00000000-0000-0000-0000-000000000000",
        },
    )
    rows = result.fetchall()
    if len(rows) < 2:
        return None

    keys = ["energy", "pitch_mean", "pitch_std", "speech_rate", "pause_ratio"]
    baseline: dict = {}
    for key in keys:
        vals = [row[0][key] for row in rows if row[0] and key in row[0]]
        baseline[key] = float(np.mean(vals)) if vals else 0.0
    return baseline


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

async def concatenate_recordings(paths: list[str], output_path: str) -> bool:
    """Concatenate per-turn WAV files into a single file for analysis."""
    return await asyncio.to_thread(_concat_sync, paths, output_path)


def _concat_sync(paths: list[str], output_path: str) -> bool:
    import soundfile as sf

    lib = _librosa()
    chunks, sr_ref = [], None

    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            y, sr = lib.load(p, sr=None, mono=True)
            if sr_ref is None:
                sr_ref = sr
            chunks.append(y)
        except Exception as exc:
            logger.warning(f"Skipping recording {p}: {exc}")

    if not chunks or sr_ref is None:
        return False

    sf.write(output_path, np.concatenate(chunks), sr_ref, subtype="PCM_16")
    return True
