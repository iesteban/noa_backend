from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TwilioWebhook(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_sid: str = Field(alias="MessageSid")
    from_number: str = Field(alias="From")   # "whatsapp:+34600123456"
    to_number: str = Field(alias="To")       # "whatsapp:+14155238886"
    body: str = Field(default="", alias="Body")
    num_media: int = Field(default=0, alias="NumMedia")
    media_url_0: str | None = Field(default=None, alias="MediaUrl0")
    media_content_type_0: str | None = Field(default=None, alias="MediaContentType0")
