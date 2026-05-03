from __future__ import annotations

from typing import Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import PrimaryKeyMixin, TimestampMixin


class OnboardingSession(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "onboarding_sessions"

    chat_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
