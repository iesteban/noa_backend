from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import PrimaryKeyMixin, TimestampMixin


class InstructionScope(enum.StrEnum):
    global_ = "global"
    invoices = "invoices"
    budgets = "budgets"
    reminders = "reminders"
    appointments = "appointments"


class ContractorInstruction(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contractor_instructions"

    contractor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contractors.id"), nullable=False, index=True
    )
    scope: Mapped[InstructionScope] = mapped_column(
        Enum(InstructionScope, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    instruction: Mapped[str] = mapped_column(String(280), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
