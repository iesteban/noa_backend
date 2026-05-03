from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.calendar.base import CalendarEvent
from app.config import settings
from app.models.appointment import CalendarToken

if TYPE_CHECKING:
    from app.models.appointment import Appointment

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarProvider:
    def __init__(self, token: CalendarToken, db: AsyncSession) -> None:
        self._token = token
        self._db = db

    # ------------------------------------------------------------------
    # Internal helpers (sync — run in executor)
    # ------------------------------------------------------------------

    def _build_credentials(self) -> Any:
        from google.oauth2.credentials import Credentials

        return Credentials(  # type: ignore[no-untyped-call]
            token=self._token.access_token,
            refresh_token=self._token.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=_SCOPES,
        )

    def _refresh_if_needed(self, creds: Any) -> Any:
        from google.auth.transport.requests import Request

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds

    def _sync_list_events(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        from googleapiclient.discovery import build

        creds = self._refresh_if_needed(self._build_credentials())
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start.astimezone(UTC).isoformat(),
                timeMax=end.astimezone(UTC).isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        self._maybe_update_token(creds)
        return result.get("items", [])  # type: ignore[no-any-return]

    def _sync_create_event(self, body: dict[str, Any]) -> str:
        from googleapiclient.discovery import build

        creds = self._refresh_if_needed(self._build_credentials())
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        event = service.events().insert(calendarId="primary", body=body).execute()
        self._maybe_update_token(creds)
        return str(event["id"])

    def _sync_update_event(self, external_id: str, body: dict[str, Any]) -> None:
        from googleapiclient.discovery import build

        creds = self._refresh_if_needed(self._build_credentials())
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        service.events().update(calendarId="primary", eventId=external_id, body=body).execute()
        self._maybe_update_token(creds)

    def _sync_delete_event(self, external_id: str) -> None:
        from googleapiclient.discovery import build

        creds = self._refresh_if_needed(self._build_credentials())
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        service.events().delete(calendarId="primary", eventId=external_id).execute()

    def _maybe_update_token(self, creds: Any) -> None:
        """Store refreshed credentials back on the token object (flushed by caller)."""
        if creds.token and creds.token != self._token.access_token:
            self._token.access_token = creds.token
            self._token.expires_at = creds.expiry

    # ------------------------------------------------------------------
    # CalendarProvider protocol implementation
    # ------------------------------------------------------------------

    async def list_events(
        self, contractor_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        loop = asyncio.get_event_loop()
        items = await loop.run_in_executor(None, self._sync_list_events, start, end)
        await self._db.flush()
        return [self._parse_event(item) for item in items]

    async def create_event(self, appointment: Appointment) -> str:
        from datetime import timedelta

        ends_at = appointment.starts_at + timedelta(minutes=appointment.duration_minutes)
        body = {
            "summary": appointment.description,
            "start": {
                "dateTime": appointment.starts_at.isoformat(),
                "timeZone": "Europe/Madrid",
            },
            "end": {
                "dateTime": ends_at.isoformat(),
                "timeZone": "Europe/Madrid",
            },
        }
        loop = asyncio.get_event_loop()
        event_id = await loop.run_in_executor(None, self._sync_create_event, body)
        await self._db.flush()
        return event_id

    async def update_event(self, external_id: str, appointment: Appointment) -> None:
        from datetime import timedelta

        ends_at = appointment.starts_at + timedelta(minutes=appointment.duration_minutes)
        body = {
            "summary": appointment.description,
            "start": {
                "dateTime": appointment.starts_at.isoformat(),
                "timeZone": "Europe/Madrid",
            },
            "end": {
                "dateTime": ends_at.isoformat(),
                "timeZone": "Europe/Madrid",
            },
        }
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_update_event, external_id, body)
        await self._db.flush()

    async def delete_event(self, external_id: str) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_delete_event, external_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_event(item: dict[str, Any]) -> CalendarEvent:
        def _parse_dt(val: str) -> datetime:
            if val.endswith("Z"):
                val = val[:-1] + "+00:00"
            return datetime.fromisoformat(val)

        start = item.get("start", {})
        end = item.get("end", {})
        starts_at = _parse_dt(start.get("dateTime") or start.get("date", ""))
        ends_at = _parse_dt(end.get("dateTime") or end.get("date", ""))
        return CalendarEvent(
            id=item["id"],
            starts_at=starts_at,
            ends_at=ends_at,
            summary=item.get("summary", ""),
        )
