"""
SMS escalation service.

Centralises all outbound SMS alerts so call_manager and mood scoring
both use the same function.
"""

import logging

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def send_sms(to_number: str, user_name: str, reason: str) -> bool:
    """
    Send an SMS alert to a family member.
    Returns True if the message was accepted by Twilio.
    """
    if not to_number:
        logger.warning("SMS escalation skipped — no family phone number configured.")
        return False
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        logger.warning("SMS escalation skipped — Twilio credentials not set.")
        return False

    try:
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        client.messages.create(
            to=to_number,
            from_=settings.twilio_phone_number,
            body=f"Aria alert for {user_name}: {reason} Please check in with them soon.",
        )
        logger.info(f"Escalation SMS sent to {to_number} — {reason}")
        return True
    except Exception as exc:
        logger.error(f"SMS escalation failed: {exc}")
        return False
