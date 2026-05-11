"""Unit tests for app.messaging.whatsapp_parser."""
from __future__ import annotations

from app.messaging.types import MessageType
from app.messaging.whatsapp_parser import parse_whatsapp
from app.schemas.whatsapp import MetaWebhook


def _webhook(
    from_number: str = "34600123456",
    msg_type: str = "text",
    body: str = "Hola",
    media_id: str | None = None,
    media_mime: str | None = None,
    caption: str | None = None,
) -> MetaWebhook:
    message: dict = {
        "from": from_number,
        "id": "wamid.abc123",
        "timestamp": "1700000000",
        "type": msg_type,
    }
    if msg_type == "text":
        message["text"] = {"body": body}
    elif msg_type == "audio":
        message["audio"] = {
            "id": media_id or "media-id-1",
            "mime_type": media_mime or "audio/ogg; codecs=opus",
            "voice": True,
        }
    elif msg_type == "image":
        message["image"] = {
            "id": media_id or "media-id-2",
            "mime_type": media_mime or "image/jpeg",
            "caption": caption,
        }
    elif msg_type == "document":
        message["document"] = {
            "id": media_id or "media-id-3",
            "mime_type": media_mime or "application/pdf",
            "caption": caption,
        }

    return MetaWebhook.model_validate({
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "waba-id",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "messages": [message],
                },
                "field": "messages",
            }],
        }],
    })


def _status_webhook() -> MetaWebhook:
    return MetaWebhook.model_validate({
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "waba-id",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "statuses": [{
                        "id": "wamid.xyz", "status": "delivered",
                        "timestamp": "1700000001", "recipient_id": "34600123456",
                    }],
                },
                "field": "messages",
            }],
        }],
    })


class TestTextMessage:
    def test_message_type(self) -> None:
        result = parse_whatsapp(_webhook(body="Hola"))
        assert result is not None
        assert result.message_type == MessageType.text

    def test_text_content(self) -> None:
        result = parse_whatsapp(_webhook(body="Necesito una factura"))
        assert result is not None
        assert result.text == "Necesito una factura"

    def test_empty_body(self) -> None:
        result = parse_whatsapp(_webhook(body=""))
        assert result is not None
        assert result.message_type == MessageType.text
        assert result.text == ""

    def test_no_file_id(self) -> None:
        result = parse_whatsapp(_webhook())
        assert result is not None
        assert result.file_id is None


class TestPhoneNormalisation:
    def test_prepends_plus(self) -> None:
        result = parse_whatsapp(_webhook(from_number="34600999888"))
        assert result is not None
        assert result.recipient_id == "+34600999888"
        assert result.phone_number == "+34600999888"

    def test_recipient_id_equals_phone_number(self) -> None:
        result = parse_whatsapp(_webhook(from_number="34611223344"))
        assert result is not None
        assert result.recipient_id == result.phone_number


class TestVoiceMessage:
    def test_message_type(self) -> None:
        result = parse_whatsapp(_webhook(msg_type="audio"))
        assert result is not None
        assert result.message_type == MessageType.voice

    def test_file_id_is_media_id(self) -> None:
        result = parse_whatsapp(_webhook(msg_type="audio", media_id="audio-media-id"))
        assert result is not None
        assert result.file_id == "audio-media-id"

    def test_text_is_none(self) -> None:
        result = parse_whatsapp(_webhook(msg_type="audio"))
        assert result is not None
        assert result.text is None


class TestPhotoMessage:
    def test_message_type(self) -> None:
        result = parse_whatsapp(_webhook(msg_type="image"))
        assert result is not None
        assert result.message_type == MessageType.photo

    def test_file_id_is_media_id(self) -> None:
        result = parse_whatsapp(_webhook(msg_type="image", media_id="image-media-id"))
        assert result is not None
        assert result.file_id == "image-media-id"

    def test_caption_as_text(self) -> None:
        result = parse_whatsapp(_webhook(msg_type="image", caption="antes/después"))
        assert result is not None
        assert result.text == "antes/después"


class TestDocumentMessage:
    def test_message_type(self) -> None:
        result = parse_whatsapp(_webhook(msg_type="document"))
        assert result is not None
        assert result.message_type == MessageType.document

    def test_file_id_set(self) -> None:
        result = parse_whatsapp(_webhook(msg_type="document", media_id="doc-media-id"))
        assert result is not None
        assert result.file_id == "doc-media-id"


class TestStatusUpdate:
    def test_returns_none_for_status_update(self) -> None:
        result = parse_whatsapp(_status_webhook())
        assert result is None


class TestUpdateId:
    def test_update_id_is_int(self) -> None:
        result = parse_whatsapp(_webhook())
        assert result is not None
        assert isinstance(result.update_id, int)

    def test_update_id_non_negative(self) -> None:
        result = parse_whatsapp(_webhook())
        assert result is not None
        assert result.update_id >= 0
