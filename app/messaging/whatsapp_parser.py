from __future__ import annotations

from app.messaging.types import InboundMessage, MessageType
from app.schemas.whatsapp import TwilioWebhook

_WHATSAPP_PREFIX = "whatsapp:"


def parse_whatsapp(webhook: TwilioWebhook) -> InboundMessage:
    """Convert a Twilio webhook payload into a channel-agnostic InboundMessage."""
    phone_number = webhook.from_number.removeprefix(_WHATSAPP_PREFIX)

    # Use a stable integer derived from the MessageSid for logging purposes only.
    update_id = abs(hash(webhook.message_sid)) & 0x7FFF_FFFF

    if webhook.num_media > 0 and webhook.media_content_type_0 and webhook.media_url_0:
        content_type = webhook.media_content_type_0
        if content_type.startswith("audio/"):
            msg_type = MessageType.voice
        elif content_type.startswith("image/"):
            msg_type = MessageType.photo
        else:
            msg_type = MessageType.document

        return InboundMessage(
            update_id=update_id,
            recipient_id=phone_number,
            phone_number=phone_number,
            message_type=msg_type,
            text=webhook.body or None,
            file_id=webhook.media_url_0,
        )

    return InboundMessage(
        update_id=update_id,
        recipient_id=phone_number,
        phone_number=phone_number,
        message_type=MessageType.text,
        text=webhook.body,
        file_id=None,
    )
