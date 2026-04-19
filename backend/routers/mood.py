"""
Mood router — data source for the family dashboard chart (Phase 4).
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from models.user import Call

router = APIRouter()


@router.get("/{user_id}")
async def get_mood_history(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Return all mood scores for a user ordered by date ascending.
    Used by the dashboard to render the weekly mood trend chart.
    """
    result = await db.execute(
        select(
            Call.id, Call.started_at, Call.mood_score, Call.flagged,
            Call.emotional_state, Call.masking_detected, Call.contradiction_flag,
        )
        .where(Call.user_id == user_id, Call.mood_score.isnot(None))
        .order_by(Call.started_at.asc())
    )
    rows = result.all()

    return [
        {
            "call_id": str(r.id),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "mood_score": r.mood_score,
            "flagged": r.flagged,
            "emotional_state": r.emotional_state,
            "masking_detected": r.masking_detected or False,
            "contradiction_flag": r.contradiction_flag or False,
        }
        for r in rows
    ]
