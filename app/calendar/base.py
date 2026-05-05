from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.models.appointment import Appointment


@dataclass
class CalendarEvent:
    id: str
    starts_at: datetime
    ends_at: datetime
    summary: str


class CalendarProvider(Protocol):
    async def create_event(self, appointment: Appointment) -> str:
        """Create a calendar event and return the external event ID."""
        ...

    async def update_event(self, external_id: str, appointment: Appointment) -> None: ...

    async def delete_event(self, external_id: str) -> None: ...

    async def list_events(
        self, contractor_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[CalendarEvent]: ...
