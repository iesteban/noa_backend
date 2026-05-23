"""Integration tests for working hours handlers — real PostgreSQL."""
from __future__ import annotations

from datetime import UTC, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.handlers.working_hours import handle_get_working_hours, handle_set_working_hours
from app.models.working_hours import WorkingHours
from tests.integration.conftest import make_contractor, make_session, make_working_hours


class TestSetWorkingHours:
    async def test_creates_new_rows(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_set_working_hours(
            {
                "schedule": [
                    {
                        "day_of_week": 0,
                        "is_working_day": True,
                        "start_time": "08:00",
                        "end_time": "18:00",
                    },
                    {
                        "day_of_week": 1,
                        "is_working_day": True,
                        "start_time": "08:00",
                        "end_time": "18:00",
                    },
                ]
            },
            db,
            session,
        )

        assert "Lunes" in result
        assert "Martes" in result
        rows = (
            await db.execute(
                select(WorkingHours).where(WorkingHours.contractor_id == contractor.id)
            )
        ).scalars().all()
        assert len(rows) == 2

    async def test_upserts_existing_row(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await make_working_hours(db, contractor, 0, start_time=time(9, 0), end_time=time(17, 0))

        await handle_set_working_hours(
            {
                "schedule": [
                    {
                        "day_of_week": 0,
                        "is_working_day": True,
                        "start_time": "08:00",
                        "end_time": "20:00",
                    },
                ]
            },
            db,
            session,
        )

        rows = (
            await db.execute(
                select(WorkingHours).where(WorkingHours.contractor_id == contractor.id)
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].start_time == time(8, 0)
        assert rows[0].end_time == time(20, 0)

    async def test_sets_day_off(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        await handle_set_working_hours(
            {"schedule": [{"day_of_week": 6, "is_working_day": False}]},
            db,
            session,
        )

        rows = (
            await db.execute(
                select(WorkingHours).where(WorkingHours.contractor_id == contractor.id)
            )
        ).scalars().all()
        assert len(rows) == 1
        assert not rows[0].is_working_day
        assert rows[0].start_time is None
        assert rows[0].end_time is None

    async def test_missing_times_when_working_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_set_working_hours(
            {"schedule": [{"day_of_week": 0, "is_working_day": True}]},
            db,
            session,
        )

        assert "obligatorio" in result.lower()

    async def test_end_before_start_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_set_working_hours(
            {
                "schedule": [
                    {
                        "day_of_week": 0,
                        "is_working_day": True,
                        "start_time": "18:00",
                        "end_time": "08:00",
                    }
                ]
            },
            db,
            session,
        )

        assert "end_time" in result or "posterior" in result

    async def test_invalid_day_of_week_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_set_working_hours(
            {
                "schedule": [
                    {
                        "day_of_week": 7,
                        "is_working_day": True,
                        "start_time": "09:00",
                        "end_time": "18:00",
                    }
                ]
            },
            db,
            session,
        )

        assert "fuera de rango" in result

    async def test_data_isolation(self, db: AsyncSession) -> None:
        contractor_a = await make_contractor(db)
        contractor_b = await make_contractor(db)
        session_a = await make_session(db, contractor_a)

        await handle_set_working_hours(
            {
                "schedule": [
                    {
                        "day_of_week": 0,
                        "is_working_day": True,
                        "start_time": "09:00",
                        "end_time": "18:00",
                    }
                ]
            },
            db,
            session_a,
        )

        rows_b = (
            await db.execute(
                select(WorkingHours).where(WorkingHours.contractor_id == contractor_b.id)
            )
        ).scalars().all()
        assert len(rows_b) == 0


class TestGetWorkingHours:
    async def test_returns_default_message_when_no_schedule(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_get_working_hours({}, db, session)

        assert "No tienes horario" in result
        assert "por defecto" in result

    async def test_returns_configured_schedule(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await make_working_hours(db, contractor, 0, start_time=time(8, 0), end_time=time(17, 0))
        await make_working_hours(db, contractor, 6, is_working_day=False)

        result = await handle_get_working_hours({}, db, session)

        assert "Lunes" in result
        assert "08:00" in result
        assert "17:00" in result
        assert "Domingo" in result
        assert "No disponible" in result


class TestCreateAppointmentWorkingHoursWarning:
    """Tests the working-hours check inside handle_create_appointment."""

    async def test_no_warning_when_no_schedule_configured(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)

        from app.ai.handlers.calendar import _check_working_hours

        result = await _check_working_hours(
            db, contractor.id, datetime(2027, 6, 7, 10, 0, tzinfo=UTC)
        )

        assert result is None

    async def test_warns_on_day_off(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        # Sunday = weekday 6
        await make_working_hours(db, contractor, 6, is_working_day=False)

        from app.ai.handlers.calendar import _check_working_hours

        # 2027-06-06 is a Sunday
        result = await _check_working_hours(
            db, contractor.id, datetime(2027, 6, 6, 10, 0, tzinfo=UTC)
        )

        assert result is not None
        assert "domingo" in result.lower()

    async def test_warns_on_out_of_hours_time(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        # Monday = 0
        await make_working_hours(db, contractor, 0, start_time=time(9, 0), end_time=time(17, 0))

        from app.ai.handlers.calendar import _check_working_hours

        # 2027-06-07 is a Monday — 19:00 is outside 09:00–17:00
        result = await _check_working_hours(
            db, contractor.id, datetime(2027, 6, 7, 19, 0, tzinfo=UTC)
        )

        assert result is not None
        assert "09:00" in result
        assert "17:00" in result

    async def test_no_warning_within_hours(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        await make_working_hours(db, contractor, 0, start_time=time(8, 0), end_time=time(18, 0))

        from app.ai.handlers.calendar import _check_working_hours

        # Monday at 10:00
        result = await _check_working_hours(
            db, contractor.id, datetime(2027, 6, 7, 10, 0, tzinfo=UTC)
        )

        assert result is None


class TestGetAvailabilityWithWorkingHours:
    """Tests that get_availability respects working hours."""

    async def test_saturday_included_when_configured(self, db: AsyncSession) -> None:
        import uuid as _uuid
        from unittest.mock import AsyncMock

        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        # Configure Saturday as a working day
        await make_working_hours(db, contractor, 5, start_time=time(9, 0), end_time=time(13, 0))
        # Mon-Fri must also be configured so that schedule is non-empty
        for dow in range(5):
            await make_working_hours(
                db, contractor, dow, start_time=time(9, 0), end_time=time(18, 0)
            )

        from app.ai.handlers.calendar import handle_get_availability
        from app.models.appointment import CalendarProviderEnum, CalendarToken

        token = CalendarToken(
            contractor_id=contractor.id,
            provider=CalendarProviderEnum.google,
            state=str(_uuid.uuid4()),
            access_token="tok",
            refresh_token="ref",
        )
        db.add(token)
        await db.flush()

        provider = AsyncMock()
        provider.list_events = AsyncMock(return_value=[])

        # 2026-05-02 is a Saturday
        result = await handle_get_availability(
            {"date_from": "2026-05-02", "date_to": "2026-05-02"},
            db,
            session,
            _provider=provider,
        )

        assert "09:00" in result

    async def test_sunday_excluded_when_marked_off(self, db: AsyncSession) -> None:
        import uuid as _uuid
        from unittest.mock import AsyncMock

        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        # Only Monday configured; Sunday explicitly off
        await make_working_hours(db, contractor, 0, start_time=time(9, 0), end_time=time(18, 0))
        await make_working_hours(db, contractor, 6, is_working_day=False)

        from app.ai.handlers.calendar import handle_get_availability
        from app.models.appointment import CalendarProviderEnum, CalendarToken

        token = CalendarToken(
            contractor_id=contractor.id,
            provider=CalendarProviderEnum.google,
            state=str(_uuid.uuid4()),
            access_token="tok",
            refresh_token="ref",
        )
        db.add(token)
        await db.flush()

        provider = AsyncMock()
        provider.list_events = AsyncMock(return_value=[])

        # 2026-05-03 is a Sunday
        result = await handle_get_availability(
            {"date_from": "2026-05-03", "date_to": "2026-05-03"},
            db,
            session,
            _provider=provider,
        )

        assert "No hay huecos" in result
