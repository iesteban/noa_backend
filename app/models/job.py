import enum
import uuid
from datetime import date

from sqlalchemy import UUID, Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import PrimaryKeyMixin, TimestampMixin


class JobStatus(enum.StrEnum):
    draft = "draft"
    invoiced = "invoiced"


class Job(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"

    contractor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contractors.id"), nullable=False, index=True
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), index=True
    )
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    date: Mapped[date | None] = mapped_column(Date)
    duration_hours: Mapped[float | None] = mapped_column(Numeric(6, 2))
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), nullable=False, default=JobStatus.draft
    )
    voice_note_url: Mapped[str | None] = mapped_column(String(500))

    contractor: Mapped["Contractor"] = relationship(back_populates="jobs")  # noqa: F821
    client: Mapped["Client | None"] = relationship(back_populates="jobs")  # noqa: F821
