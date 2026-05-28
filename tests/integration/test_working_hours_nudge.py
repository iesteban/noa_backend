"""Integration tests for the working-hours nudge that fires when a contractor
uses calendar features without having a schedule configured.

See issue #117.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.handlers.calendar import (
    _WORKING_HOURS_NUDGE_FLAG,
    handle_create_appointment,
    handle_get_availability,
    handle_initiate_appointment,
)
from app.calendar.base import CalendarEvent
from app.models.appointment import CalendarProviderEnum, CalendarToken
from tests.integration.conftest import (
    make_client,
    make_contractor,
    make_session,
    make_working_hours,
)

_NUDGE_MARKER = "[SYSTEM NUDGE"
_NUDGE_TEXT = "aún no tienes horario laboral configurado"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_token(db: AsyncSession, contractor_id: object) -> CalendarToken:
    import uuid as _uuid
    token = CalendarToken(
        contractor_id=contractor_id,  # type: ignore[arg-type]
        provider=CalendarProviderEnum.google,
        state=str(_uuid.uuid4()),
        access_token="access-token",
        refresh_token="refresh-token",
    )
    db.add(token)
    await db.flush()
    return token


def _fake_provider() -> object:
    provider = AsyncMock()
    provider.list_events = AsyncMock(return_value=[])
    provider.create_event = AsyncMock(return_value="gcal-event-id")
    return provider


def _appt_input(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "starts_at": "2027-06-01T10:00:00",
        "duration_minutes": 60,
        "description": "Visita fontanería",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# get_availability
# ---------------------------------------------------------------------------

class TestNudgeOnGetAvailability:
    async def test_nudge_shown_when_no_working_hours(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await _make_token(db, contractor.id)

        result = await handle_get_availability(
            {"date_from": "2026-05-04", "date_to": "2026-05-04"},
            db,
            session,
            _provider=_fake_provider(),  # type: ignore[call-arg]
        )

        assert _NUDGE_MARKER in result
        assert _NUDGE_TEXT in result
        assert session.context.get(_WORKING_HOURS_NUDGE_FLAG) is True

    async def test_nudge_shown_when_calendar_not_connected(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_get_availability(
            {"date_from": "2026-05-04", "date_to": "2026-05-04"}, db, session
        )

        # Without token: nudge still surfaces alongside the connect prompt.
        assert "/auth/google/connect" in result
        assert _NUDGE_MARKER in result
        assert session.context.get(_WORKING_HOURS_NUDGE_FLAG) is True

    async def test_nudge_not_shown_when_working_hours_set(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await make_working_hours(db, contractor, 0)  # Monday
        await _make_token(db, contractor.id)

        result = await handle_get_availability(
            {"date_from": "2026-05-04", "date_to": "2026-05-04"},
            db,
            session,
            _provider=_fake_provider(),  # type: ignore[call-arg]
        )

        assert _NUDGE_MARKER not in result
        assert _WORKING_HOURS_NUDGE_FLAG not in session.context

    async def test_nudge_not_repeated_within_same_session(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await _make_token(db, contractor.id)

        first = await handle_get_availability(
            {"date_from": "2026-05-04", "date_to": "2026-05-04"},
            db,
            session,
            _provider=_fake_provider(),  # type: ignore[call-arg]
        )
        second = await handle_get_availability(
            {"date_from": "2026-05-05", "date_to": "2026-05-05"},
            db,
            session,
            _provider=_fake_provider(),  # type: ignore[call-arg]
        )

        assert _NUDGE_MARKER in first
        assert _NUDGE_MARKER not in second

    async def test_nudge_not_shown_on_validation_error(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_get_availability(
            {"date_from": "not-a-date", "date_to": "2026-05-04"}, db, session
        )

        assert _NUDGE_MARKER not in result
        assert _WORKING_HOURS_NUDGE_FLAG not in session.context


# ---------------------------------------------------------------------------
# create_appointment
# ---------------------------------------------------------------------------

class TestNudgeOnCreateAppointment:
    async def test_nudge_shown_when_no_working_hours(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_create_appointment(_appt_input(), db, session)

        assert "Cita creada" in result
        assert _NUDGE_MARKER in result
        assert session.context.get(_WORKING_HOURS_NUDGE_FLAG) is True

    async def test_nudge_not_shown_when_working_hours_set(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        # Configure all 7 days so _check_working_hours passes for any starts_at.
        for dow in range(7):
            await make_working_hours(db, contractor, dow)

        result = await handle_create_appointment(_appt_input(), db, session)

        assert "Cita creada" in result
        assert _NUDGE_MARKER not in result

    async def test_nudge_not_shown_on_validation_error(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_create_appointment(
            _appt_input(starts_at="2020-01-01T10:00:00"), db, session
        )

        assert "pasado" in result.lower()
        assert _NUDGE_MARKER not in result
        assert _WORKING_HOURS_NUDGE_FLAG not in session.context

    async def test_nudge_does_not_repeat_after_first_calendar_action(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await _make_token(db, contractor.id)

        first = await handle_create_appointment(
            _appt_input(starts_at="2027-06-01T10:00:00"),
            db,
            session,
            _provider=_fake_provider(),  # type: ignore[call-arg]
        )
        second = await handle_get_availability(
            {"date_from": "2027-06-02", "date_to": "2027-06-02"},
            db,
            session,
            _provider=_fake_provider(),  # type: ignore[call-arg]
        )

        assert _NUDGE_MARKER in first
        assert _NUDGE_MARKER not in second


# ---------------------------------------------------------------------------
# initiate_appointment
# ---------------------------------------------------------------------------

class TestNudgeOnInitiateAppointment:
    async def test_nudge_shown_when_no_working_hours(
        self, db: AsyncSession, monkeypatch: object
    ) -> None:
        import app.ai.handlers.calendar as calendar_module

        async def _fake_send(*_args: object, **_kwargs: object) -> str:
            return "Plantilla enviada ✓"

        monkeypatch.setattr(  # type: ignore[attr-defined]
            calendar_module,
            "_send_appointment_request_template",
            _fake_send,
        )

        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)

        result = await handle_initiate_appointment(
            {
                "client_id": str(client.id),
                "duration_minutes": 60,
                "description": "fontanería",
            },
            db,
            session,
        )

        assert "Cita pendiente creada" in result
        assert _NUDGE_MARKER in result
        assert session.context.get(_WORKING_HOURS_NUDGE_FLAG) is True


# ---------------------------------------------------------------------------
# Cross-action behaviour
# ---------------------------------------------------------------------------

class TestNudgeFlagPersistsAcrossActions:
    async def test_busy_calendar_event_does_not_skip_nudge_flag_set(
        self, db: AsyncSession
    ) -> None:
        """Even when get_availability returns 'no hay huecos', the nudge fires."""
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await _make_token(db, contractor.id)

        provider = AsyncMock()
        provider.list_events = AsyncMock(
            return_value=[
                CalendarEvent(
                    id="evt1",
                    starts_at=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
                    ends_at=datetime(2026, 5, 4, 18, 0, tzinfo=UTC),
                    summary="Busy all day",
                )
            ]
        )

        result = await handle_get_availability(
            {"date_from": "2026-05-04", "date_to": "2026-05-04"},
            db,
            session,
            _provider=provider,  # type: ignore[call-arg]
        )

        assert "No hay huecos" in result
        assert _NUDGE_MARKER in result
