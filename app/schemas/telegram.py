from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
    vcard: str | None = None


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


