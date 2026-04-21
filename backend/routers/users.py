"""
Users router — Phase 5.

Endpoints:
  GET  /users                        — list all users (for dashboard selector)
  PATCH /users/{user_id}/call-time   — update call time + reschedule
"""

import uuid
from datetime import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from models.user import User

router = APIRouter()


class CallTimeUpdate(BaseModel):
    call_time: str   # "HH:MM" 24-hour format
    timezone: str    # IANA timezone, e.g. "America/New_York"


@router.get("/")
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User.id, User.name, User.phone_number, User.call_time, User.timezone))
    return [
        {
            "user_id": str(r.id),
            "name": r.name,
            "phone_number": r.phone_number,
            "call_time": r.call_time.strftime("%H:%M"),
            "timezone": r.timezone,
        }
        for r in result.all()
    ]


@router.patch("/{user_id}/call-time")
async def update_call_time(
    user_id: uuid.UUID,
    body: CallTimeUpdate,
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        h, m = map(int, body.call_time.split(":"))
        user.call_time = time(h, m)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail="call_time must be HH:MM format")

    import pytz
    try:
        pytz.timezone(body.timezone)
    except pytz.UnknownTimeZoneError:
        raise HTTPException(status_code=422, detail=f"Unknown timezone: {body.timezone}")

    user.timezone = body.timezone
    await db.commit()

    # Reschedule the APScheduler job with the new time
    from services.scheduler import schedule_user
    schedule_user(user)

    return {
        "user_id": str(user.id),
        "call_time": user.call_time.strftime("%H:%M"),
        "timezone": user.timezone,
    }
