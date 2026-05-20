from __future__ import annotations

import uuid
from datetime import time

from sqlalchemy import Boolean, ForeignKey, Integer, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import PrimaryKeyMixin, TimestampMixin


class WorkingHours(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "working_hours"
    __table_args__ = (
        UniqueConstraint("contractor_id", "day_of_week", name="uq_working_hours_contractor_day"),
    )

    contractor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contractors.id"), nullable=False, index=True
    )
    # 0 = Monday … 6 = Sunday (matches Python's datetime.weekday())
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    is_working_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)

    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from app.models.contractor import Contractor
    contractor: Mapped[Contractor] = relationship(foreign_keys=[contractor_id])
