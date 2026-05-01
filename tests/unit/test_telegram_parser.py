import pytest

from app.messaging.parser import parse_update
from app.messaging.types import InboundMessage, MessageType
from app.schemas.telegram import (
    TelegramChat,
    TelegramContact,
    TelegramDocument,
    TelegramMessage,
    TelegramPhotoSize,
    TelegramUpdate,
    TelegramUser,
    TelegramVoice,
)

CHAT = TelegramChat(id=111, type="private")
USER = TelegramUser(id=999, first_name="Pedro")


def _update(message: TelegramMessage) -> TelegramUpdate:
    return TelegramUpdate(update_id=1, message=message)


def _msg(**kwargs: object) -> TelegramMessage:
    return TelegramMessage(message_id=1, chat=CHAT, date=0, **kwargs)  # type: ignore[arg-type]


class TestParseTextMessage:
    def test_returns_inbound_message(self) -> None:
        update = _update(_msg(text="Hola"))
        result = parse_update(update)
        assert isinstance(result, InboundMessage)

    def test_message_type(self) -> None:
        result = parse_update(_update(_msg(text="Hola")))
        assert result is not None
        assert result.message_type == MessageType.text

    def test_text_content(self) -> None:
        result = parse_update(_update(_msg(text="Hola Noa")))
        assert result is not None
        assert result.text == "Hola Noa"

    def test_chat_id(self) -> None:
        result = parse_update(_update(_msg(text="Hi")))
        assert result is not None
        assert result.chat_id == 111

    def test_no_file_id(self) -> None:
        result = parse_update(_update(_msg(text="Hi")))
        assert result is not None
        assert result.file_id is None

    def test_no_phone_number(self) -> None:
        result = parse_update(_update(_msg(text="Hi")))
        assert result is not None
        assert result.phone_number is None


class TestParseVoiceMessage:
    def test_message_type(self) -> None:
        voice = TelegramVoice(file_id="v1", file_unique_id="vu1", duration=5)
        result = parse_update(_update(_msg(voice=voice)))
        assert result is not None
        assert result.message_type == MessageType.voice

    def test_file_id(self) -> None:
        voice = TelegramVoice(file_id="voice-abc", file_unique_id="vu1", duration=5)
        result = parse_update(_update(_msg(voice=voice)))
        assert result is not None
        assert result.file_id == "voice-abc"

    def test_caption_as_text(self) -> None:
        voice = TelegramVoice(file_id="v1", file_unique_id="vu1", duration=5)
        result = parse_update(_update(_msg(voice=voice, caption="nota")))
        assert result is not None
        assert result.text == "nota"

    def test_no_caption(self) -> None:
        voice = TelegramVoice(file_id="v1", file_unique_id="vu1", duration=5)
        result = parse_update(_update(_msg(voice=voice)))
        assert result is not None
        assert result.text is None


class TestParsePhotoMessage:
    def _photo_sizes(self) -> list[TelegramPhotoSize]:
        return [
            TelegramPhotoSize(file_id="small", file_unique_id="s", width=100, height=100),
            TelegramPhotoSize(file_id="large", file_unique_id="l", width=800, height=800),
        ]

    def test_message_type(self) -> None:
        result = parse_update(_update(_msg(photo=self._photo_sizes())))
        assert result is not None
        assert result.message_type == MessageType.photo

    def test_picks_largest_photo(self) -> None:
        result = parse_update(_update(_msg(photo=self._photo_sizes())))
        assert result is not None
        assert result.file_id == "large"

    def test_caption(self) -> None:
        result = parse_update(_update(_msg(photo=self._photo_sizes(), caption="before/after")))
        assert result is not None
        assert result.text == "before/after"


class TestParseDocumentMessage:
    def test_message_type(self) -> None:
        doc = TelegramDocument(file_id="d1", file_unique_id="du1", file_name="factura.pdf")
        result = parse_update(_update(_msg(document=doc)))
        assert result is not None
        assert result.message_type == MessageType.document

    def test_file_id(self) -> None:
        doc = TelegramDocument(file_id="doc-xyz", file_unique_id="du1")
        result = parse_update(_update(_msg(document=doc)))
        assert result is not None
        assert result.file_id == "doc-xyz"


class TestParseContactMessage:
    def test_message_type(self) -> None:
        contact = TelegramContact(phone_number="+34600000001", first_name="Pedro")
        result = parse_update(_update(_msg(contact=contact)))
        assert result is not None
        assert result.message_type == MessageType.contact

    def test_phone_number_extracted(self) -> None:
        contact = TelegramContact(phone_number="+34600000001", first_name="Pedro")
        result = parse_update(_update(_msg(contact=contact)))
        assert result is not None
        assert result.phone_number == "+34600000001"

    def test_no_file_id(self) -> None:
        contact = TelegramContact(phone_number="+34600000001", first_name="Pedro")
        result = parse_update(_update(_msg(contact=contact)))
        assert result is not None
        assert result.file_id is None


class TestParseUnhandledTypes:
    def test_unknown_type_returns_inbound(self) -> None:
        # Message with no recognised content fields
        result = parse_update(_update(_msg()))
        assert result is not None
        assert result.message_type == MessageType.unknown

    def test_unknown_type_no_crash(self) -> None:
        result = parse_update(_update(_msg()))
        assert result is not None

    def test_update_with_no_message_returns_none(self) -> None:
        update = TelegramUpdate(update_id=1)
        assert parse_update(update) is None

    def test_edited_message_is_parsed(self) -> None:
        update = TelegramUpdate(update_id=2, edited_message=_msg(text="edited"))
        result = parse_update(update)
        assert result is not None
        assert result.message_type == MessageType.text
        assert result.text == "edited"


class TestUpdateIdAndChatId:
    def test_update_id_propagated(self) -> None:
        update = TelegramUpdate(update_id=42, message=_msg(text="hi"))
        result = parse_update(update)
        assert result is not None
        assert result.update_id == 42

    def test_chat_id_propagated(self) -> None:
        msg = TelegramMessage(
            message_id=1,
            chat=TelegramChat(id=555, type="private"),
            date=0,
            text="hi",
        )
        result = parse_update(TelegramUpdate(update_id=1, message=msg))
        assert result is not None
        assert result.chat_id == 555


class TestTelegramUpdateParsing:
    """Validate that raw Telegram JSON (with 'from' key) is correctly parsed."""

    def test_from_field_alias(self) -> None:
        raw = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "from": {"id": 99, "first_name": "Ana"},
                "chat": {"id": 111, "type": "private"},
                "date": 0,
                "text": "Hola",
            },
        }
        update = TelegramUpdate.model_validate(raw)
        assert update.message is not None
        assert update.message.from_ is not None
        assert update.message.from_.id == 99

    @pytest.mark.parametrize(
        "field,payload",
        [
            ("text", {"text": "hello"}),
            ("voice", {"voice": {"file_id": "v", "file_unique_id": "vu", "duration": 3}}),
            (
                "photo",
                {
                    "photo": [
                        {"file_id": "p", "file_unique_id": "pu", "width": 100, "height": 100}
                    ]
                },
            ),
            (
                "document",
                {"document": {"file_id": "d", "file_unique_id": "du"}},
            ),
        ],
    )
    def test_message_types_from_raw(self, field: str, payload: dict) -> None:  # type: ignore[type-arg]
        raw = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "chat": {"id": 1, "type": "private"},
                "date": 0,
                **payload,
            },
        }
        update = TelegramUpdate.model_validate(raw)
        result = parse_update(update)
        assert result is not None
        assert result.message_type == MessageType(field)
