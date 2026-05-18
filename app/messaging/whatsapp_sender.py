from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_GRAPH_API = "https://graph.facebook.com/v19.0"

# WhatsApp platform limits for interactive messages.
_WA_BUTTON_MAX = 3       # max buttons in a reply-button message
_WA_LIST_MAX = 10        # max rows in a list message
_WA_BUTTON_TITLE = 20    # max chars for a reply-button title
_WA_LIST_TITLE = 24      # max chars for a list-row title


def _text_payload(recipient_id: str, text: str) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "text",
        "text": {"body": text},
    }


def _reply_buttons_payload(
    recipient_id: str, text: str, options: list[str]
) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": str(i), "title": opt}}
                    for i, opt in enumerate(options)
                ]
            },
        },
    }


def _list_payload(
    recipient_id: str, text: str, options: list[str]
) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": text},
            "action": {
                "button": "Ver opciones",
                "sections": [
                    {
                        "rows": [
                            {"id": str(i), "title": opt}
                            for i, opt in enumerate(options)
                        ]
                    }
                ],
            },
        },
    }


async def send_message(
    recipient_id: str,
    text: str,
    options: list[str] | None = None,
) -> None:
    """Send a WhatsApp message via the Meta Graph API.

    When options are provided:
    - ≤3 options with short titles → reply buttons (interactive/button)
    - ≤10 options with titles ≤24 chars → list message (interactive/list)
    - Otherwise → numbered plain-text fallback
    """
    if options:
        if (
            len(options) <= _WA_BUTTON_MAX
            and all(len(o) <= _WA_BUTTON_TITLE for o in options)
        ):
            payload = _reply_buttons_payload(recipient_id, text, options)
        elif (
            len(options) <= _WA_LIST_MAX
            and all(len(o) <= _WA_LIST_TITLE for o in options)
        ):
            payload = _list_payload(recipient_id, text, options)
        else:
            numbered = "\n".join(f"{i + 1}. {opt}" for i, opt in enumerate(options))
            payload = _text_payload(recipient_id, f"{text}\n{numbered}")
    else:
        payload = _text_payload(recipient_id, text)

    url = f"{_GRAPH_API}/{settings.whatsapp_phone_number_id}/messages"
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
