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
    recipient_id: str  # opaque channel identifier used to send replies back
    phone_number: str | None
    message_type: MessageType
    text: str | None
    file_id: str | None
    external_id: str | None = None  # platform message ID for deduplication (e.g. WhatsApp wamid)


class MessageSender(Protocol):
    async def __call__(
        self,
        recipient_id: str,
        text: str,
        options: list[str] | None = None,
    ) -> None: ...
