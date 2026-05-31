from __future__ import annotations

import logging

from app.messaging.contacts import format_contact_text, parse_vcard_phones
from app.messaging.types import InboundMessage, MessageType
from app.schemas.telegram import TelegramUpdate

logger = logging.getLogger(__name__)


def parse_update(update: TelegramUpdate) -> InboundMessage | None:
    # Inline keyboard button tap — treat the callback data as a regular text message.
    if update.callback_query is not None:
        cq = update.callback_query
        if cq.message is None or not cq.data:
            return None
        return InboundMessage(
            update_id=update.update_id,
            recipient_id=str(cq.message.chat.id),
            phone_number=None,
            message_type=MessageType.text,
            text=cq.data,
            file_id=None,
            external_id=str(update.update_id),
        )

    message = update.message or update.edited_message
    if message is None:
        logger.info("Update %d has no message — skipping", update.update_id)
        return None

    recipient_id = str(message.chat.id)

    if message.text is not None:
        return InboundMessage(
            update_id=update.update_id,
            recipient_id=recipient_id,
            phone_number=None,
            message_type=MessageType.text,
            text=message.text,
            file_id=None,
            external_id=str(update.update_id),
        )

    if message.voice is not None:
        return InboundMessage(
            update_id=update.update_id,
            recipient_id=recipient_id,
            phone_number=None,
            message_type=MessageType.voice,
            text=message.caption,
            file_id=message.voice.file_id,
            external_id=str(update.update_id),
        )

    if message.photo is not None and len(message.photo) > 0:
        # Telegram sends multiple sizes; take the largest (last)
        return InboundMessage(
            update_id=update.update_id,
            recipient_id=recipient_id,
            phone_number=None,
            message_type=MessageType.photo,
            text=message.caption,
            file_id=message.photo[-1].file_id,
            external_id=str(update.update_id),
        )

    if message.document is not None:
        return InboundMessage(
            update_id=update.update_id,
            recipient_id=recipient_id,
            phone_number=None,
            message_type=MessageType.document,
            text=message.caption,
            file_id=message.document.file_id,
            external_id=str(update.update_id),
        )

    if message.contact is not None:
        contact = message.contact
        name = " ".join(p for p in [contact.first_name, contact.last_name] if p)

        phones: list[tuple[str, str]] = []
        if contact.vcard:
            phones = parse_vcard_phones(contact.vcard)
        if not phones:
            phones = [(contact.phone_number, "teléfono")]

        text = format_contact_text(name, phones)

        return InboundMessage(
            update_id=update.update_id,
            recipient_id=recipient_id,
            phone_number=contact.phone_number,
            message_type=MessageType.contact,
            text=text,
            file_id=None,
            external_id=str(update.update_id),
        )

    logger.info(
        "Update %d message %d: unhandled message type",
        update.update_id,
        message.message_id,
    )
    return InboundMessage(
        update_id=update.update_id,
        recipient_id=recipient_id,
        phone_number=None,
        message_type=MessageType.unknown,
        text=None,
        file_id=None,
        external_id=str(update.update_id),
    )
