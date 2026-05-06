"""Integration tests for calendar tool handlers — real PostgreSQL, mocked Google API."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.handlers.calendar import (
    handle_connect_google_calendar,
    handle_create_appointment,
    handle_get_availability,
)
from app.calendar.base import CalendarEvent
from app.models.appointment import (
    Appointment,
    AppointmentStatus,
    CalendarProviderEnum,
    CalendarToken,
)
from tests.integration.conftest import make_contractor, make_session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_token(
    db: AsyncSession,
    contractor_id: object,
    *,
    connected: bool = True,
) -> CalendarToken:
    import uuid
    token = CalendarToken(
        contractor_id=contractor_id,  # type: ignore[arg-type]
        provider=CalendarProviderEnum.google,
        state=str(uuid.uuid4()),
        access_token="access-token" if connected else None,
        refresh_token="refresh-token" if connected else None,
    )
    db.add(token)
    await db.flush()
    return token


def _fake_provider(events: list[CalendarEvent] | None = None) -> object:
    provider = AsyncMock()
    provider.list_events = AsyncMock(return_value=events or [])
    provider.create_event = AsyncMock(return_value="gcal-event-id-123")
    return provider


# ---------------------------------------------------------------------------
# connect_google_calendar
# ---------------------------------------------------------------------------

class TestConnectGoogleCalendar:
    async def test_creates_pending_token(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_connect_google_calendar({}, db, session)

        rows = await db.execute(
            select(CalendarToken).where(CalendarToken.contractor_id == contractor.id)
        )
        token = rows.scalar_one()
        assert token.access_token is None
        assert token.provider == CalendarProviderEnum.google
        assert token.state in result

    async def test_returns_connect_url(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_connect_google_calendar({}, db, session)

        assert "/auth/google/connect?state=" in result

    async def test_replaces_existing_pending_token(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await _make_token(db, contractor.id, connected=False)

        await handle_connect_google_calendar({}, db, session)

        rows = await db.execute(
            select(CalendarToken).where(CalendarToken.contractor_id == contractor.id)
        )
        tokens = rows.scalars().all()
        assert len(tokens) == 1

    async def test_replaces_existing_active_token(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await _make_token(db, contractor.id, connected=True)

        result = await handle_connect_google_calendar({}, db, session)

        rows = await db.execute(
            select(CalendarToken).where(CalendarToken.contractor_id == contractor.id)
        )
        tokens = rows.scalars().all()
        assert len(tokens) == 1
        assert tokens[0].access_token is None
        assert "/auth/google/connect?state=" in result


# ---------------------------------------------------------------------------
# get_availability
# ---------------------------------------------------------------------------

class TestGetAvailability:
    async def test_no_token_returns_connect_prompt(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_get_availability(
            {"date_from": "2026-05-05", "date_to": "2026-05-07"}, db, session
        )

        assert "/auth/google/connect" in result

    async def test_returns_free_slots_when_calendar_empty(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await _make_token(db, contractor.id)
        provider = _fake_provider(events=[])

        result = await handle_get_availability(
            {"date_from": "2026-05-04", "date_to": "2026-05-04"},
            db,
            session,
            _provider=provider,  # type: ignore[call-arg]
        )

        assert "09:00" in result
        assert "Huecos disponibles" in result

    async def test_busy_slot_excluded(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await _make_token(db, contractor.id)

        busy_event = CalendarEvent(
            id="evt1",
            starts_at=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            ends_at=datetime(2026, 5, 4, 10, 0, tzinfo=UTC),
            summary="Existing appointment",
        )
        provider = _fake_provider(events=[busy_event])

        result = await handle_get_availability(
            {"date_from": "2026-05-04", "date_to": "2026-05-04"},
            db,
            session,
            _provider=provider,  # type: ignore[call-arg]
        )

        assert "09:00" not in result
        assert "10:00" in result

    async def test_invalid_dates_return_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_get_availability(
            {"date_from": "not-a-date", "date_to": "2026-05-07"}, db, session
        )

        assert "inválid" in result.lower()

    async def test_date_to_before_date_from_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_get_availability(
            {"date_from": "2026-05-10", "date_to": "2026-05-07"}, db, session
        )

        assert "date_to" in result

    async def test_weekend_days_excluded(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await _make_token(db, contractor.id)
        provider = _fake_provider(events=[])

        # 2026-05-02 and 2026-05-03 are Saturday and Sunday
        result = await handle_get_availability(
            {"date_from": "2026-05-02", "date_to": "2026-05-03"},
            db,
            session,
            _provider=provider,  # type: ignore[call-arg]
        )

        assert "No hay huecos" in result


# ---------------------------------------------------------------------------
# create_appointment
# ---------------------------------------------------------------------------

class TestCreateAppointment:
    def _input(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "starts_at": "2026-05-05T10:00:00",
            "duration_minutes": 60,
            "description": "Visita fontanería",
        }
        base.update(overrides)
        return base

    async def test_appointment_persisted_in_db(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        await handle_create_appointment(self._input(), db, session)

        rows = await db.execute(
            select(Appointment).where(Appointment.contractor_id == contractor.id)
        )
        appointments = rows.scalars().all()
        assert len(appointments) == 1
        assert appointments[0].description == "Visita fontanería"

    async def test_appointment_has_correct_fields(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        await handle_create_appointment(
            self._input(duration_minutes=90, description="Reparación caldera"),
            db,
            session,
        )

        rows = await db.execute(
            select(Appointment).where(Appointment.contractor_id == contractor.id)
        )
        appt = rows.scalars().one()
        assert appt.duration_minutes == 90
        assert appt.status == AppointmentStatus.scheduled
        assert appt.starts_at == datetime(2026, 5, 5, 10, 0, tzinfo=UTC)

    async def test_syncs_to_google_calendar_when_connected(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await _make_token(db, contractor.id)
        provider = _fake_provider()

        result = await handle_create_appointment(
            self._input(),
            db,
            session,
            _provider=provider,  # type: ignore[call-arg]
        )

        assert "Google Calendar ✓" in result
        rows = await db.execute(
            select(Appointment).where(Appointment.contractor_id == contractor.id)
        )
        appt = rows.scalars().one()
        assert appt.external_calendar_id == "gcal-event-id-123"
        assert appt.calendar_provider == CalendarProviderEnum.google

    async def test_creates_appointment_without_calendar(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_create_appointment(self._input(), db, session)

        assert "Cita creada" in result
        rows = await db.execute(
            select(Appointment).where(Appointment.contractor_id == contractor.id)
        )
        appt = rows.scalars().one()
        assert appt.external_calendar_id is None

    async def test_google_calendar_failure_still_saves_appointment(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await _make_token(db, contractor.id)

        failing_provider = AsyncMock()
        failing_provider.create_event = AsyncMock(side_effect=Exception("Google API down"))

        result = await handle_create_appointment(
            self._input(),
            db,
            session,
            _provider=failing_provider,  # type: ignore[call-arg]
        )

        assert "Cita creada" in result
        assert "No se pudo sincronizar" in result
        rows = await db.execute(
            select(Appointment).where(Appointment.contractor_id == contractor.id)
        )
        assert len(rows.scalars().all()) == 1

    async def test_invalid_starts_at_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_create_appointment(
            self._input(starts_at="not-a-datetime"), db, session
        )

        assert "inválido" in result.lower()

    async def test_confirmation_contains_description_and_time(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_create_appointment(
            self._input(description="Cambio de caldera", starts_at="2026-05-05T14:30:00"),
            db,
            session,
        )

        assert "Cambio de caldera" in result
        assert "14:30" in result
