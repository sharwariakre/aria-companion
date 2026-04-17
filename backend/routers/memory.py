"""
Memory router — read-only endpoints for the family dashboard (Phase 4).
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from models.user import Memory

router = APIRouter()


@router.get("/{user_id}")
async def get_memories(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return all memories for a user, newest first."""
    result = await db.execute(
        select(Memory)
        .where(Memory.user_id == user_id)
        .order_by(Memory.created_at.desc())
    )
    memories = result.scalars().all()

    return [
        {
            "id": str(m.id),
            "content": m.content,
            "source_call_id": str(m.source_call_id) if m.source_call_id else None,
            "created_at": m.created_at.isoformat() if isinstance(m.created_at, datetime) else m.created_at,
        }
        for m in memories
    ]
