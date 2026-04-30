from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import UUID, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import PrimaryKeyMixin, TimestampMixin


class UserType(enum.StrEnum):
    contractor = "contractor"
    client = "client"


class MessageRole(enum.StrEnum):
    user = "user"
    assistant = "assistant"


class ConversationSession(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_sessions"
    __table_args__ = (Index("ix_conversation_sessions_phone_number", "phone_number"),)

    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    user_type: Mapped[UserType] = mapped_column(Enum(UserType), nullable=False)
    contractor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contractors.id"), index=True
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), index=True
    )
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    messages: Mapped[list["Message"]] = relationship(back_populates="session")


class Message(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversation_sessions.id"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    media_url: Mapped[str | None] = mapped_column(String(500))

    session: Mapped["ConversationSession"] = relationship(back_populates="messages")
