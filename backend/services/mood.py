"""
Mood signals service — Phase 3.

Extracts acoustic features from call audio using librosa and computes a
mood score relative to the user's personal baseline.

Librosa is imported lazily — it's slow to load and is not pre-warmed at
startup. The first call with audio will take a few extra seconds.
"""

import asyncio
import logging
import os
import uuid
from typing import Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


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
# Mood scoring
# ---------------------------------------------------------------------------

def compute_mood_score(features: dict, baseline: Optional[dict]) -> float:
    """
    Score 0.0–1.0 relative to the user's personal baseline.
      0.0 = much lower energy / engagement than baseline
      0.5 = no baseline yet (neutral)
      1.0 = much higher energy / engagement than baseline

    Higher energy, higher pitch, faster speech rate → higher score.
    Higher pause ratio → lower score.
    """
    if not baseline:
        return 0.5

    def delta_score(val: float, base: float, sensitivity: float = 1.5) -> float:
        if base <= 0:
            return 0.5
        pct = (val - base) / base
        return max(0.0, min(1.0, 0.5 + pct * sensitivity * 0.5))

    energy_score  = delta_score(features.get("energy", 0),       baseline.get("energy", 0))
    pitch_score   = delta_score(features.get("pitch_mean", 0),   baseline.get("pitch_mean", 1), sensitivity=1.0)
    speech_score  = delta_score(features.get("speech_rate", 0),  baseline.get("speech_rate", 0))
    # Higher pause ratio → worse mood → invert
    pause_score   = 1.0 - delta_score(features.get("pause_ratio", 0.5), baseline.get("pause_ratio", 0.5))

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

async def get_user_baseline(user_id: uuid.UUID, db: AsyncSession) -> Optional[dict]:
    """
    Average mood_features from the user's last 3 completed calls.
    Returns None if fewer than 3 calls with features exist.
    """
    result = await db.execute(
        text("""
            SELECT mood_features
            FROM calls
            WHERE user_id  = :user_id
              AND mood_features IS NOT NULL
              AND ended_at  IS NOT NULL
            ORDER BY ended_at DESC
            LIMIT 3
        """),
        {"user_id": str(user_id)},
    )
    rows = result.fetchall()
    if len(rows) < 3:
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
