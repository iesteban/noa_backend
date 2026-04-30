from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class MessageType(enum.StrEnum):
    text = "text"
    voice = "voice"
    photo = "photo"
    document = "document"
    contact = "contact"
    unknown = "unknown"


class TelegramUser(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None


class TelegramChat(BaseModel):
    id: int
    type: str


class TelegramVoice(BaseModel):
    file_id: str
    file_unique_id: str
    duration: int
    mime_type: str | None = None
    file_size: int | None = None


class TelegramPhotoSize(BaseModel):
    file_id: str
    file_unique_id: str
    width: int
    height: int
    file_size: int | None = None


class TelegramDocument(BaseModel):
    file_id: str
    file_unique_id: str
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None


class TelegramContact(BaseModel):
    phone_number: str
    first_name: str
    last_name: str | None = None
    user_id: int | None = None


class TelegramMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: int
    from_: TelegramUser | None = Field(None, alias="from")
    chat: TelegramChat
    date: int
    text: str | None = None
    voice: TelegramVoice | None = None
    photo: list[TelegramPhotoSize] | None = None
    document: TelegramDocument | None = None
    contact: TelegramContact | None = None
    caption: str | None = None


class TelegramUpdate(BaseModel):
    update_id: int
    message: TelegramMessage | None = None
    edited_message: TelegramMessage | None = None


class InboundMessage(BaseModel):
    update_id: int
    chat_id: int
    # Populated from a contact share; routing (issue #5) resolves from DB by telegram_chat_id
    phone_number: str | None
    message_type: MessageType
    text: str | None
    file_id: str | None
