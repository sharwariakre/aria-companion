"""
Daily call scheduler — Phase 5.

Loads all users on startup and schedules a daily outbound call at each
user's configured call_time in their timezone. Uses APScheduler's
AsyncIOScheduler so jobs run on the same event loop as the rest of the app.
"""

import logging

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(job_defaults={"misfire_grace_time": 600})


async def _call_user(user_id: str) -> None:
    """Job target — opens a DB session and fires the outbound call."""
    from db.database import AsyncSessionLocal
    from models.user import User
    from services.call_manager import trigger_outbound_call

    async with AsyncSessionLocal() as db:
        import uuid
        user = await db.get(User, uuid.UUID(user_id))
        if not user:
            logger.warning(f"Scheduled call: user {user_id} not found, skipping.")
            return
        try:
            sid = await trigger_outbound_call(user, db)
            logger.info(f"Scheduled call placed for {user.name} — SID {sid}")
        except Exception as exc:
            logger.error(f"Scheduled call failed for {user.name}: {exc}")


def schedule_user(user) -> None:
    """Add or replace the daily job for a single user."""
    tz = pytz.timezone(user.timezone)
    trigger = CronTrigger(
        hour=user.call_time.hour,
        minute=user.call_time.minute,
        timezone=tz,
    )
    scheduler.add_job(
        _call_user,
        trigger=trigger,
        args=[str(user.id)],
        id=f"daily_call_{user.id}",
        replace_existing=True,
    )
    logger.info(
        f"Scheduled daily call for {user.name} at "
        f"{user.call_time.strftime('%H:%M')} {user.timezone}"
    )


async def schedule_all_users() -> None:
    """Load every user from the DB and schedule their daily call."""
    from db.database import AsyncSessionLocal
    from models.user import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()

    for user in users:
        schedule_user(user)

    logger.info(f"Scheduler: {len(users)} user(s) scheduled.")
