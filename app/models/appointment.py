from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.contractor import Contractor


class CalendarProviderEnum(enum.StrEnum):
    google = "google"
    apple = "apple"


class AppointmentStatus(enum.StrEnum):
    pending_client = "pending_client"
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


class BookedBy(enum.StrEnum):
    contractor = "contractor"
    client = "client"


class Appointment(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "appointments"

    contractor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contractors.id"), nullable=False, index=True
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointmentstatus"),
        nullable=False,
        default=AppointmentStatus.scheduled,
    )
    calendar_provider: Mapped[CalendarProviderEnum | None] = mapped_column(
        Enum(CalendarProviderEnum, name="calendarprovider"), nullable=True
    )
    external_calendar_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    booked_by: Mapped[BookedBy] = mapped_column(
        Enum(BookedBy, name="bookedby"),
        nullable=False,
        default=BookedBy.contractor,
    )

    contractor: Mapped[Contractor] = relationship(foreign_keys=[contractor_id])


class CalendarToken(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "calendar_tokens"
    __table_args__ = (
        UniqueConstraint("contractor_id", "provider", name="uq_calendar_token_contractor_provider"),
    )

    contractor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contractors.id"), nullable=False, index=True
    )
    provider: Mapped[CalendarProviderEnum] = mapped_column(
        Enum(CalendarProviderEnum, name="calendarprovider"),
        nullable=False,
    )
    # OAuth state UUID — used to match the callback to the pending token.
    state: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # PKCE code_verifier generated at /connect, consumed at /callback.
    code_verifier: Mapped[str | None] = mapped_column(String(128), nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_connected(self) -> bool:
        return self.access_token is not None
