from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MetaTextContent(BaseModel):
    body: str


class MetaMediaContent(BaseModel):
    id: str
    mime_type: str
    caption: str | None = None
    voice: bool = False


class MetaMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_: str = Field(alias="from")
    timestamp: str
    type: str
    text: MetaTextContent | None = None
    audio: MetaMediaContent | None = None
    image: MetaMediaContent | None = None
    document: MetaMediaContent | None = None


class MetaValue(BaseModel):
    messaging_product: str
    messages: list[MetaMessage] = []


class MetaChange(BaseModel):
    value: MetaValue
    field: str


class MetaEntry(BaseModel):
    id: str
    changes: list[MetaChange]


class MetaWebhook(BaseModel):
    object: str
    entry: list[MetaEntry]
