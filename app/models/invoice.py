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
    from app.models.job import Job


class InvoiceStatus(enum.StrEnum):
    draft = "draft"
    sent = "sent"
    paid = "paid"
    overdue = "overdue"


class Invoice(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "invoices"

    contractor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contractors.id"), nullable=False, index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    due_date: Mapped[datetime.date | None] = mapped_column(Date)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.draft
    )
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    iva_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    irpf_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    pdf_url: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))

    contractor: Mapped[Contractor] = relationship()
    client: Mapped[Client] = relationship()
    lines: Mapped[list[InvoiceLine]] = relationship(back_populates="invoice")


class InvoiceLine(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "invoice_lines"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id")
    )
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    iva_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    irpf_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")
    job: Mapped[Job | None] = relationship()
