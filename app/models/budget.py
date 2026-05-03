from __future__ import annotations

import datetime
import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import UUID, Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.contractor import Contractor


class BudgetStatus(enum.StrEnum):
    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    rejected = "rejected"
    invoiced = "invoiced"


class Budget(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "budgets"

    contractor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contractors.id"), nullable=False, index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True
    )
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[datetime.date | None] = mapped_column(Date)
    status: Mapped[BudgetStatus] = mapped_column(
        Enum(BudgetStatus), nullable=False, default=BudgetStatus.draft
    )
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    pdf_url: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))

    contractor: Mapped[Contractor] = relationship()
    client: Mapped[Client] = relationship()
    lines: Mapped[list[BudgetLine]] = relationship(back_populates="budget")


class BudgetLine(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "budget_lines"

    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.id"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    iva_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    budget: Mapped[Budget] = relationship(back_populates="lines")
