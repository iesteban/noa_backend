from __future__ import annotations

import logging

from app.schemas.telegram import InboundMessage, MessageType, TelegramUpdate

logger = logging.getLogger(__name__)


def parse_update(update: TelegramUpdate) -> InboundMessage | None:
    message = update.message or update.edited_message
    if message is None:
        logger.info("Update %d has no message — skipping", update.update_id)
        return None

    chat_id = message.chat.id

    if message.text is not None:
        return InboundMessage(
            update_id=update.update_id,
            chat_id=chat_id,
            phone_number=None,
            message_type=MessageType.text,
            text=message.text,
            file_id=None,
        )

    if message.voice is not None:
        return InboundMessage(
            update_id=update.update_id,
            chat_id=chat_id,
            phone_number=None,
            message_type=MessageType.voice,
            text=message.caption,
            file_id=message.voice.file_id,
        )

    if message.photo is not None and len(message.photo) > 0:
        # Telegram sends multiple sizes; take the largest (last)
        return InboundMessage(
            update_id=update.update_id,
            chat_id=chat_id,
            phone_number=None,
            message_type=MessageType.photo,
            text=message.caption,
            file_id=message.photo[-1].file_id,
        )

    if message.document is not None:
        return InboundMessage(
            update_id=update.update_id,
            chat_id=chat_id,
            phone_number=None,
            message_type=MessageType.document,
            text=message.caption,
            file_id=message.document.file_id,
        )

    if message.contact is not None:
        return InboundMessage(
            update_id=update.update_id,
            chat_id=chat_id,
            phone_number=message.contact.phone_number,
            message_type=MessageType.contact,
            text=None,
            file_id=None,
        )

    logger.info(
        "Update %d message %d: unhandled message type",
        update.update_id,
        message.message_id,
    )
    return InboundMessage(
        update_id=update.update_id,
        chat_id=chat_id,
        phone_number=None,
        message_type=MessageType.unknown,
        text=None,
        file_id=None,
    )
