"""
ngrok tunnel health check — runs every 60 seconds via APScheduler.

Checks the ngrok local management API (http://localhost:4040/api/tunnels)
to determine if an active tunnel exists. This avoids outbound TLS entirely
and works reliably on macOS pyenv where the system SSL certs are broken.
"""

import logging

import httpx

from services.metrics import NGROK_UP

logger = logging.getLogger(__name__)

_was_up: bool = True  # track previous state to avoid repeated alerts

NGROK_API = "http://localhost:4040/api/tunnels"


async def check_ngrok_health() -> bool:
    global _was_up
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(NGROK_API)
            data = r.json()
            up = bool(data.get("tunnels"))
    except Exception:
        up = False

    NGROK_UP.set(1 if up else 0)

    if not up and _was_up:
        logger.warning("ngrok tunnel is unreachable — calls will fail until it's restored.")

    _was_up = up
    return up
