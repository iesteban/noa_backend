from __future__ import annotations

from app.messaging.contacts import format_contact_text, parse_vcard_phones
from app.messaging.types import InboundMessage, MessageType
from app.schemas.whatsapp import MetaWebhook


def parse_whatsapp(webhook: MetaWebhook) -> InboundMessage | None:
    """Extract the first inbound message from a Meta webhook payload.

    Returns None for status updates and other non-message events.
    """
    try:
        message = webhook.entry[0].changes[0].value.messages[0]
    except IndexError:
        return None

    # Meta sends wa_id without the leading "+"; normalise to E.164.
    phone_number = f"+{message.from_}"
    update_id = abs(hash(message.id)) & 0x7FFF_FFFF

    if message.type == "audio" and message.audio:
        return InboundMessage(
            update_id=update_id,
            recipient_id=phone_number,
            phone_number=phone_number,
            message_type=MessageType.voice,
            text=None,
            file_id=message.audio.id,
        )

    if message.type == "image" and message.image:
        return InboundMessage(
            update_id=update_id,
            recipient_id=phone_number,
            phone_number=phone_number,
            message_type=MessageType.photo,
            text=message.image.caption,
            file_id=message.image.id,
        )

    if message.type == "document" and message.document:
        return InboundMessage(
            update_id=update_id,
            recipient_id=phone_number,
            phone_number=phone_number,
            message_type=MessageType.document,
            text=message.document.caption,
            file_id=message.document.id,
        )

    if message.type == "contacts" and message.contacts:
        contact = message.contacts[0]
        name = contact.name.formatted_name

        phones: list[tuple[str, str]] = []
        if contact.vcard:
            phones = parse_vcard_phones(contact.vcard)
        if not phones:
            phones = [
                (p.phone, (p.type or "teléfono").lower()) for p in contact.phones if p.phone
            ]

        text = (
            format_contact_text(name, phones)
            if phones
            else f"[Contacto compartido]\nNombre: {name}"
        )
        return InboundMessage(
            update_id=update_id,
            recipient_id=phone_number,
            phone_number=phone_number,
            message_type=MessageType.contact,
            text=text,
            file_id=None,
        )

    if message.type == "interactive" and message.interactive:
        interactive = message.interactive
        if interactive.button_reply:
            tapped = interactive.button_reply.title
        elif interactive.list_reply:
            tapped = interactive.list_reply.title
        else:
            tapped = None
        if tapped:
            return InboundMessage(
                update_id=update_id,
                recipient_id=phone_number,
                phone_number=phone_number,
                message_type=MessageType.text,
                text=tapped,
                file_id=None,
            )

    if message.type == "text" and message.text:
        return InboundMessage(
            update_id=update_id,
            recipient_id=phone_number,
            phone_number=phone_number,
            message_type=MessageType.text,
            text=message.text.body,
            file_id=None,
        )

    return InboundMessage(
        update_id=update_id,
        recipient_id=phone_number,
        phone_number=phone_number,
        message_type=MessageType.unknown,
        text=None,
        file_id=None,
    )
