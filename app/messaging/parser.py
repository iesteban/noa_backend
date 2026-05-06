from __future__ import annotations

import logging
import re

from app.messaging.types import InboundMessage, MessageType
from app.schemas.telegram import TelegramUpdate

logger = logging.getLogger(__name__)

_VCARD_TYPE_LABELS: dict[str, str] = {
    "cell": "móvil",
    "mobile": "móvil",
    "work": "trabajo",
    "home": "casa",
    "main": "principal",
}


def _parse_vcard_phones(vcard: str) -> list[tuple[str, str]]:
    """Return (number, label) pairs from vCard TEL entries."""
    results = []
    for line in vcard.splitlines():
        if not line.upper().startswith("TEL"):
            continue
        # TEL;TYPE=CELL:+34600123456  or  TEL:+34600123456
        colon = line.find(":")
        if colon == -1:
            continue
        number = re.sub(r"[\s\-\(\)]", "", line[colon + 1:]).strip()
        if not number:
            continue
        type_match = re.search(r"TYPE=([^;:]+)", line, re.IGNORECASE)
        raw_types = type_match.group(1).lower().split(",") if type_match else []
        label = next(
            (_VCARD_TYPE_LABELS[t] for t in raw_types if t in _VCARD_TYPE_LABELS),
            "teléfono",
        )
        results.append((number, label))
    return results


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
        contact = message.contact
        name = " ".join(p for p in [contact.first_name, contact.last_name] if p)

        phones: list[tuple[str, str]] = []
        if contact.vcard:
            phones = _parse_vcard_phones(contact.vcard)
        if not phones:
            phones = [(contact.phone_number, "teléfono")]

        if len(phones) == 1:
            number, label = phones[0]
            text = f"[Contacto compartido]\nNombre: {name}\nTeléfono: {number}"
        else:
            lines = [f"[Contacto compartido]\nNombre: {name}\nTeléfonos disponibles:"]
            for i, (number, label) in enumerate(phones, 1):
                lines.append(f"  {i}. {number} ({label})")
            text = "\n".join(lines)

        return InboundMessage(
            update_id=update.update_id,
            chat_id=chat_id,
            phone_number=contact.phone_number,
            message_type=MessageType.contact,
            text=text,
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
