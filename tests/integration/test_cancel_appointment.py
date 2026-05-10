"""Integration tests for cancel_appointment contractor tool handler."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.handlers.calendar import handle_cancel_appointment
from app.models.appointment import (
    Appointment,
    AppointmentStatus,
    BookedBy,
    CalendarProviderEnum,
    CalendarToken,
)
from app.models.session import UserType
from tests.integration.conftest import make_client, make_contractor, make_session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_appointment(
    db: AsyncSession,
    contractor_id: object,
    client_id: object | None = None,
    *,
    status: AppointmentStatus = AppointmentStatus.scheduled,
    external_calendar_id: str | None = None,
) -> Appointment:

    appt = Appointment(
        contractor_id=contractor_id,  # type: ignore[arg-type]
        client_id=client_id,  # type: ignore[arg-type]
        starts_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
        duration_minutes=60,
        description="Reparación fontanería",
        status=status,
        booked_by=BookedBy.client,
        calendar_provider=CalendarProviderEnum.google if external_calendar_id else None,
        external_calendar_id=external_calendar_id,
    )
    db.add(appt)
    await db.flush()
    return appt


async def _make_token(db: AsyncSession, contractor_id: object) -> CalendarToken:
    import uuid

    token = CalendarToken(
        contractor_id=contractor_id,  # type: ignore[arg-type]
        provider=CalendarProviderEnum.google,
        state=str(uuid.uuid4()),
        access_token="access-token",
        refresh_token="refresh-token",
    )
    db.add(token)
    await db.flush()
    return token


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCancelAppointment:
    async def test_appointment_marked_cancelled(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        appt = await _make_appointment(db, contractor.id)

        with patch("app.ai.handlers.calendar.telegram_send", new=AsyncMock()):
            result = await handle_cancel_appointment(
                {"appointment_id": str(appt.id)}, db, session
            )

        assert "cancelada" in result.lower()
        row = await db.execute(select(Appointment).where(Appointment.id == appt.id))
        assert row.scalar_one().status == AppointmentStatus.cancelled

    async def test_removes_google_calendar_event(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await _make_token(db, contractor.id)
        appt = await _make_appointment(
            db, contractor.id, external_calendar_id="gcal-evt-999"
        )

        fake_provider = AsyncMock()
        fake_provider.delete_event = AsyncMock()

        with (
            patch("app.ai.handlers.calendar.GoogleCalendarProvider", return_value=fake_provider),
            patch("app.ai.handlers.calendar.telegram_send", new=AsyncMock()),
        ):
            await handle_cancel_appointment({"appointment_id": str(appt.id)}, db, session)

        fake_provider.delete_event.assert_awaited_once_with("gcal-evt-999")

    async def test_notifies_client_via_telegram(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, channel="telegram", telegram_chat_id="111")
        client = await make_client(db, contractor)
        client_session = await make_session(
            db,
            contractor,
            user_type=UserType.client,
            phone_number="99887766",
            client_id=client.id,
        )
        appt = await _make_appointment(db, contractor.id, client_id=client.id)
        session = await make_session(db, contractor)

        with patch("app.ai.handlers.calendar.telegram_send", new=AsyncMock()) as mock_tg:
            await handle_cancel_appointment({"appointment_id": str(appt.id)}, db, session)

        mock_tg.assert_awaited_once_with(client_session.phone_number, mock_tg.call_args[0][1])
        assert "cancelada" in mock_tg.call_args[0][1].lower()

    async def test_notifies_client_via_whatsapp(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        client_session = await make_session(
            db,
            contractor,
            user_type=UserType.client,
            phone_number=client.phone_number,
            client_id=client.id,
            channel="whatsapp",
        )
        appt = await _make_appointment(db, contractor.id, client_id=client.id)
        session = await make_session(db, contractor)

        with patch("app.ai.handlers.calendar.whatsapp_send", new=AsyncMock()) as mock_wa:
            await handle_cancel_appointment({"appointment_id": str(appt.id)}, db, session)

        mock_wa.assert_awaited_once_with(client_session.phone_number, mock_wa.call_args[0][1])

    async def test_calendar_failure_still_cancels(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await _make_token(db, contractor.id)
        appt = await _make_appointment(
            db, contractor.id, external_calendar_id="gcal-evt-fail"
        )

        failing_provider = AsyncMock()
        failing_provider.delete_event = AsyncMock(side_effect=Exception("Google down"))

        with (
            patch("app.ai.handlers.calendar.GoogleCalendarProvider", return_value=failing_provider),
            patch("app.ai.handlers.calendar.telegram_send", new=AsyncMock()),
        ):
            result = await handle_cancel_appointment(
                {"appointment_id": str(appt.id)}, db, session
            )

        assert "cancelada" in result.lower()
        row = await db.execute(select(Appointment).where(Appointment.id == appt.id))
        assert row.scalar_one().status == AppointmentStatus.cancelled

    async def test_already_cancelled_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        appt = await _make_appointment(
            db, contractor.id, status=AppointmentStatus.cancelled
        )

        result = await handle_cancel_appointment(
            {"appointment_id": str(appt.id)}, db, session
        )

        assert "ya estaba cancelada" in result.lower()

    async def test_completed_appointment_cannot_be_cancelled(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        appt = await _make_appointment(
            db, contractor.id, status=AppointmentStatus.completed
        )

        result = await handle_cancel_appointment(
            {"appointment_id": str(appt.id)}, db, session
        )

        assert "completada" in result.lower()

    async def test_cannot_cancel_other_contractors_appointment(self, db: AsyncSession) -> None:
        contractor_a = await make_contractor(db, phone_number="+34600000011")
        contractor_b = await make_contractor(db, phone_number="+34600000022")
        appt = await _make_appointment(db, contractor_a.id)
        session_b = await make_session(db, contractor_b)

        result = await handle_cancel_appointment(
            {"appointment_id": str(appt.id)}, db, session_b
        )

        assert "no encontrada" in result.lower()
        row = await db.execute(select(Appointment).where(Appointment.id == appt.id))
        assert row.scalar_one().status == AppointmentStatus.scheduled

    async def test_invalid_uuid_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_cancel_appointment(
            {"appointment_id": "not-a-uuid"}, db, session
        )

        assert "inválido" in result.lower()
