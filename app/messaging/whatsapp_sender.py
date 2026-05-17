from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_GRAPH_API = "https://graph.facebook.com/v19.0"


async def send_message(recipient_id: str, text: str) -> None:
    """Send a WhatsApp message via the Meta Graph API. recipient_id is an E.164 phone number."""
    url = f"{_GRAPH_API}/{settings.whatsapp_phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "text",
        "text": {"body": text},
    }
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            if not r.is_success:
                logger.error(
                    "Meta WhatsApp send failed to %s: %s %s",
                    recipient_id,
                    r.status_code,
                    r.text,
                )
            r.raise_for_status()
    except Exception:
        logger.exception("Meta WhatsApp send failed to %s", recipient_id)
