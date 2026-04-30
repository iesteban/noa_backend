from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import UUID, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.contractor import Contractor
    from app.models.job import Job


class Client(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("contractor_id", "phone_number", name="uq_client_contractor_phone"),
        Index("ix_clients_phone_number", "phone_number"),
    )

    contractor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contractors.id"), nullable=False, index=True
    )
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    nif: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(String(2000))

    contractor: Mapped[Contractor] = relationship(back_populates="clients")  # noqa: F821
    jobs: Mapped[list[Job]] = relationship(back_populates="client")  # noqa: F821
