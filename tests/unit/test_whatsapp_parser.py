"""Unit tests for app.messaging.whatsapp_parser."""
from __future__ import annotations

from app.messaging.types import MessageType
from app.messaging.whatsapp_parser import parse_whatsapp
from app.schemas.whatsapp import TwilioWebhook


def _webhook(**kwargs: object) -> TwilioWebhook:
    defaults: dict[str, object] = {
        "MessageSid": "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "From": "whatsapp:+34600123456",
        "To": "whatsapp:+14155238886",
        "Body": "Hola",
        "NumMedia": "0",
    }
    return TwilioWebhook.model_validate({**defaults, **kwargs})


class TestTextMessage:
    def test_message_type(self) -> None:
        result = parse_whatsapp(_webhook(Body="Hola"))
        assert result.message_type == MessageType.text

    def test_text_content(self) -> None:
        result = parse_whatsapp(_webhook(Body="Necesito una factura"))
        assert result.text == "Necesito una factura"

    def test_empty_body(self) -> None:
        result = parse_whatsapp(_webhook(Body=""))
        assert result.message_type == MessageType.text
        assert result.text == ""

    def test_no_file_id(self) -> None:
        result = parse_whatsapp(_webhook())
        assert result.file_id is None


class TestPhoneStripping:
    def test_strips_whatsapp_prefix(self) -> None:
        result = parse_whatsapp(_webhook(From="whatsapp:+34600999888"))
        assert result.recipient_id == "+34600999888"
        assert result.phone_number == "+34600999888"

    def test_recipient_id_equals_phone_number(self) -> None:
        result = parse_whatsapp(_webhook(From="whatsapp:+34611223344"))
        assert result.recipient_id == result.phone_number


class TestVoiceMessage:
    def test_message_type(self) -> None:
        result = parse_whatsapp(
            _webhook(
                NumMedia="1",
                MediaUrl0="https://api.twilio.com/voice.ogg",
                MediaContentType0="audio/ogg",
                Body="",
            )
        )
        assert result.message_type == MessageType.voice

    def test_file_id_is_media_url(self) -> None:
        url = "https://api.twilio.com/voice.ogg"
        result = parse_whatsapp(
            _webhook(NumMedia="1", MediaUrl0=url, MediaContentType0="audio/ogg", Body="")
        )
        assert result.file_id == url

    def test_caption_preserved_as_text(self) -> None:
        result = parse_whatsapp(
            _webhook(
                NumMedia="1",
                MediaUrl0="https://api.twilio.com/voice.ogg",
                MediaContentType0="audio/ogg",
                Body="nota de voz",
            )
        )
        assert result.text == "nota de voz"

    def test_empty_body_becomes_none(self) -> None:
        result = parse_whatsapp(
            _webhook(NumMedia="1", MediaUrl0="https://x", MediaContentType0="audio/ogg", Body="")
        )
        assert result.text is None


class TestPhotoMessage:
    def test_message_type(self) -> None:
        result = parse_whatsapp(
            _webhook(
                NumMedia="1",
                MediaUrl0="https://api.twilio.com/photo.jpg",
                MediaContentType0="image/jpeg",
                Body="foto",
            )
        )
        assert result.message_type == MessageType.photo

    def test_caption_as_text(self) -> None:
        result = parse_whatsapp(
            _webhook(
                NumMedia="1",
                MediaUrl0="https://api.twilio.com/photo.jpg",
                MediaContentType0="image/jpeg",
                Body="antes/después",
            )
        )
        assert result.text == "antes/después"

    def test_png_is_photo(self) -> None:
        result = parse_whatsapp(
            _webhook(NumMedia="1", MediaUrl0="https://x", MediaContentType0="image/png", Body="")
        )
        assert result.message_type == MessageType.photo


class TestDocumentMessage:
    def test_pdf_is_document(self) -> None:
        result = parse_whatsapp(
            _webhook(
                NumMedia="1",
                MediaUrl0="https://api.twilio.com/file.pdf",
                MediaContentType0="application/pdf",
                Body="",
            )
        )
        assert result.message_type == MessageType.document

    def test_file_id_set(self) -> None:
        url = "https://api.twilio.com/file.pdf"
        result = parse_whatsapp(
            _webhook(NumMedia="1", MediaUrl0=url, MediaContentType0="application/pdf", Body="")
        )
        assert result.file_id == url


class TestUpdateId:
    def test_update_id_is_int(self) -> None:
        result = parse_whatsapp(_webhook())
        assert isinstance(result.update_id, int)

    def test_update_id_non_negative(self) -> None:
        result = parse_whatsapp(_webhook())
        assert result.update_id >= 0
