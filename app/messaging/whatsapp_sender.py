from __future__ import annotations

import asyncio
import logging

from twilio.rest import Client

from app.config import settings

logger = logging.getLogger(__name__)

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _client


def _send_sync(to: str, body: str) -> None:
    _get_client().messages.create(
        from_=f"whatsapp:{settings.twilio_whatsapp_from}",
        to=f"whatsapp:{to}",
        body=body,
    )


async def send_message(recipient_id: str, text: str) -> None:
    """Send a WhatsApp message via Twilio. recipient_id is an E.164 phone number."""
    try:
        await asyncio.to_thread(_send_sync, recipient_id, text)
    except Exception:
        logger.exception("Twilio send failed to %s", recipient_id)
