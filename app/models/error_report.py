from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    UUID,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import PrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.contractor import Contractor


class Platform(enum.StrEnum):
    telegram = "telegram"
    whatsapp = "whatsapp"


class ErrorReport(PrimaryKeyMixin, Base):
    __tablename__ = "error_reports"
    __table_args__ = (
        Index("ix_error_reports_contractor_created", "contractor_id", "created_at"),
    )

    contractor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contractors.id"), nullable=False
    )
    platform: Mapped[Platform] = mapped_column(Enum(Platform), nullable=False)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    contractor: Mapped[Contractor] = relationship(back_populates="error_reports")  # noqa: F821
