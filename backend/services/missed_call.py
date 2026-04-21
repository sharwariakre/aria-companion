"""
Missed call handler — Phase 5.

When a scheduled call comes back as no-answer, busy, or failed:
  1. If this is the first attempt, schedule a one-time retry 30 minutes later.
  2. If this is already a retry, send a missed-call email alert to the family.
"""

import logging
import uuid
from datetime import datetime, timedelta

from apscheduler.triggers.date import DateTrigger

from services import escalation as escalation_service
from services.scheduler import scheduler

logger = logging.getLogger(__name__)


async def handle_missed_call(call_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Called from the Twilio status callback when a call is not answered."""
    from db.database import AsyncSessionLocal
    from models.user import Call, User

    async with AsyncSessionLocal() as db:
        call = await db.get(Call, call_id)
        user = await db.get(User, user_id)

        if not call or not user:
            return

        call.missed = True
        await db.commit()

        if call.is_retry:
            # Second failure — alert family
            started_str = (
                call.started_at.strftime("%I:%M %p") if call.started_at else "scheduled time"
            )
            retry_str = datetime.utcnow().strftime("%I:%M %p")
            escalation_service.send_alert(
                user.name,
                f"Aria tried to reach {user.name} at {started_str} and again at {retry_str} "
                f"but couldn't get through. A family check-in may be helpful.",
            )
            logger.info(f"Missed call alert sent for {user.name} after two failed attempts.")
        else:
            # First failure — schedule a retry in 30 minutes
            retry_time = datetime.utcnow() + timedelta(minutes=30)
            scheduler.add_job(
                _retry_call,
                trigger=DateTrigger(run_date=retry_time),
                args=[str(user.id)],
                id=f"retry_call_{call_id}",
                replace_existing=True,
            )
            logger.info(
                f"Call not answered for {user.name} — retry scheduled at {retry_time.strftime('%H:%M UTC')}"
            )


async def _retry_call(user_id: str) -> None:
    """Fire a retry call marked as is_retry=True."""
    from db.database import AsyncSessionLocal
    from models.user import Call, User
    from services.call_manager import trigger_outbound_call
    import uuid as _uuid

    async with AsyncSessionLocal() as db:
        user = await db.get(User, _uuid.UUID(user_id))
        if not user:
            return

        # Pre-mark the call record as a retry before dialing
        call = Call(
            user_id=user.id,
            started_at=datetime.utcnow(),
            messages=[],
            turn_count=0,
            is_retry=True,
        )
        db.add(call)
        await db.commit()
        await db.refresh(call)

        try:
            sid = await trigger_outbound_call(user, db)
            logger.info(f"Retry call placed for {user.name} — SID {sid}")
        except Exception as exc:
            call.missed = True
            await db.commit()
            logger.error(f"Retry call failed for {user.name}: {exc}")
            escalation_service.send_alert(
                user.name,
                f"Aria tried to reach {user.name} twice but couldn't connect. Please check in.",
            )
