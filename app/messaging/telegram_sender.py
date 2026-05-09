from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_SEND_MESSAGE_URL = "https://api.telegram.org/bot{token}/sendMessage"


async def send_message(recipient_id: str, text: str) -> None:
    """Send a text message to a Telegram chat via the Bot API."""
    url = _SEND_MESSAGE_URL.format(token=settings.telegram_bot_token)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"chat_id": int(recipient_id), "text": text})
    if not resp.is_success:
        logger.error(
            "Telegram sendMessage failed: status=%d body=%s",
            resp.status_code,
            resp.text,
        )
