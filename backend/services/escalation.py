"""
Alert service — sends email notifications to family members.

Uses Gmail SMTP (free). Requires ALERT_EMAIL_FROM and ALERT_EMAIL_TO
in .env, plus an Gmail App Password as ALERT_EMAIL_PASSWORD.

To generate a Gmail App Password:
  myaccount.google.com → Security → 2-Step Verification → App Passwords
"""

import logging
import smtplib
from email.mime.text import MIMEText

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def send_alert(user_name: str, reason: str) -> bool:
    """
    Send an email alert to the configured family address.
    Returns True if the message was accepted by the mail server.
    """
    if not settings.alert_email_to:
        logger.warning("Email alert skipped — ALERT_EMAIL_TO not configured.")
        return False
    if not settings.alert_email_from or not settings.alert_email_password:
        logger.warning("Email alert skipped — ALERT_EMAIL_FROM or ALERT_EMAIL_PASSWORD not set.")
        return False

    subject = f"Aria alert for {user_name}"
    body = f"Hi,\n\nAria flagged {user_name}'s check-in today.\n\n{reason}\n\nPlease check in with them soon.\n\n— Aria"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.alert_email_from
    msg["To"] = settings.alert_email_to

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(settings.alert_email_from, settings.alert_email_password)
            smtp.send_message(msg)
        logger.info(f"Alert email sent to {settings.alert_email_to} — {reason}")
        return True
    except Exception as exc:
        logger.error(f"Email alert failed: {exc}")
        return False
