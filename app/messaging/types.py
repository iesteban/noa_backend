from __future__ import annotations

import enum
from typing import Protocol

from pydantic import BaseModel


class MessageType(enum.StrEnum):
    text = "text"
    voice = "voice"
    photo = "photo"
    document = "document"
    contact = "contact"
    unknown = "unknown"


class InboundMessage(BaseModel):
    update_id: int
    chat_id: int
    phone_number: str | None
    message_type: MessageType
    text: str | None
    file_id: str | None


class MessageSender(Protocol):
    async def __call__(self, chat_id: int, text: str) -> None: ...
