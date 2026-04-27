"""
ngrok tunnel health check — runs every 60 seconds via APScheduler.

Pings GET {base_url}/health and updates the NGROK_UP gauge.
Sends a Gmail alert if the tunnel goes down.
"""

import logging

import httpx

from config import get_settings
from services.metrics import NGROK_UP

logger = logging.getLogger(__name__)
settings = get_settings()

_was_up: bool = True  # track previous state to avoid repeated alerts


async def check_ngrok_health() -> bool:
    global _was_up
    url = settings.base_url.rstrip("/") + "/health"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(url)
            up = r.status_code == 200
    except Exception:
        up = False

    NGROK_UP.set(1 if up else 0)

    if not up and _was_up:
        logger.warning("ngrok tunnel is unreachable — calls will fail until it's restored.")
        from services import escalation as escalation_service
        escalation_service.send_alert(
            "System",
            "Aria's ngrok tunnel may be down — calls will fail until it's restored.",
        )

    _was_up = up
    return up
