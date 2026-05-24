from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot{token}"
_SEND_MESSAGE_URL = _BASE + "/sendMessage"
_ANSWER_CALLBACK_URL = _BASE + "/answerCallbackQuery"
_EDIT_REPLY_MARKUP_URL = _BASE + "/editMessageReplyMarkup"

# Telegram inline buttons are readable up to 8 per message; above that we fall
# back to a numbered plain-text list so the user can still reply by typing.
_TELEGRAM_BUTTON_LIMIT = 8


async def send_message(
    recipient_id: str,
    text: str,
    options: list[str] | None = None,
) -> None:
    """Send a text message (with optional inline keyboard) to a Telegram chat."""
    url = _SEND_MESSAGE_URL.format(token=settings.telegram_bot_token)
    payload: dict[str, object] = {"chat_id": int(recipient_id), "text": text}

    if options:
        if len(options) <= _TELEGRAM_BUTTON_LIMIT:
            # Each option gets its own row; callback_data is the option text
            # (truncated to Telegram's 64-byte limit).
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [{"text": opt, "callback_data": opt[:64]}]
                    for opt in options
                ]
            }
        else:
            numbered = "\n".join(f"{i + 1}. {opt}" for i, opt in enumerate(options))
            payload["text"] = f"{text}\n{numbered}"

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
    if not resp.is_success:
        logger.error(
            "Telegram sendMessage failed: status=%d body=%s",
            resp.status_code,
            resp.text,
        )


async def ack_callback_query(callback_query_id: str) -> None:
    """Acknowledge a callback query to dismiss the loading indicator."""
    url = _ANSWER_CALLBACK_URL.format(token=settings.telegram_bot_token)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json={"callback_query_id": callback_query_id})
    except Exception:
        logger.warning("Failed to ack Telegram callback_query %s", callback_query_id)


async def remove_inline_keyboard(chat_id: str, message_id: int) -> None:
    """Remove the inline keyboard from a bot message immediately after a button is tapped."""
    url = _EDIT_REPLY_MARKUP_URL.format(token=settings.telegram_bot_token)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                url,
                json={
                    "chat_id": int(chat_id),
                    "message_id": message_id,
                    "reply_markup": {"inline_keyboard": []},
                },
            )
    except Exception:
        logger.warning(
            "Failed to remove inline keyboard from message %d in chat %s",
            message_id,
            chat_id,
        )
