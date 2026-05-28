from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.error_report import ErrorReport
    from app.models.job import Job


class Channel(enum.StrEnum):
    telegram = "telegram"
    whatsapp = "whatsapp"


class Contractor(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contractors"

    phone_number: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_name: Mapped[str | None] = mapped_column(String(255))
    nif: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    iban: Mapped[str | None] = mapped_column(String(34))
    invoice_counter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    iva_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.21)
    irpf_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.15)
    channel: Mapped[Channel] = mapped_column(
        Enum(Channel), nullable=False, default=Channel.telegram
    )
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    clients: Mapped[list[Client]] = relationship(back_populates="contractor")  # noqa: F821
    jobs: Mapped[list[Job]] = relationship(back_populates="contractor")  # noqa: F821
    error_reports: Mapped[list[ErrorReport]] = relationship(back_populates="contractor")  # noqa: F821
