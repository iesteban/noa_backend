"""Integration tests for client-mode tool handlers (book_appointment, notify_contractor, etc.)."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.handlers.client import (
    handle_book_appointment,
    handle_get_contractor_availability,
    handle_notify_contractor,
)
from app.calendar.base import CalendarEvent
from app.models.appointment import (
    Appointment,
    AppointmentStatus,
    BookedBy,
    CalendarProviderEnum,
    CalendarToken,
)
from app.models.contractor import Channel
from app.models.session import UserType
from tests.integration.conftest import make_client, make_contractor, make_session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _fake_provider(events: list[CalendarEvent] | None = None) -> object:
    provider = AsyncMock()
    provider.list_events = AsyncMock(return_value=events or [])
    provider.create_event = AsyncMock(return_value="gcal-event-id-456")
    return provider


async def _make_client_session(db: AsyncSession) -> tuple[object, object, object]:
    """Return (contractor, client, client_session)."""
    contractor = await make_contractor(db)
    client = await make_client(db, contractor)
    session = await make_session(
        db,
        contractor,
        user_type=UserType.client,
        phone_number=client.phone_number,
        client_id=client.id,
    )
    return contractor, client, session


# ---------------------------------------------------------------------------
# get_contractor_availability
# ---------------------------------------------------------------------------


class TestGetContractorAvailability:
    async def test_no_token_returns_no_availability_message(self, db: AsyncSession) -> None:
        _, _, session = await _make_client_session(db)

        result = await handle_get_contractor_availability(
            {"date_from": "2026-05-05", "date_to": "2026-05-07"}, db, session
        )

        assert "disponibilidad" in result.lower()
        # Must not expose the OAuth connect URL to the client.
        assert "/auth/google" not in result

    async def test_returns_free_slots_when_calendar_empty(self, db: AsyncSession) -> None:
        contractor, _, session = await _make_client_session(db)
        await _make_token(db, contractor.id)
        provider = _fake_provider(events=[])

        result = await handle_get_contractor_availability(
            {"date_from": "2026-05-04", "date_to": "2026-05-04"},
            db,
            session,
            _provider=provider,  # type: ignore[call-arg]
        )

        assert "09:00" in result
        assert "Huecos disponibles" in result

    async def test_busy_slot_excluded(self, db: AsyncSession) -> None:
        contractor, _, session = await _make_client_session(db)
        await _make_token(db, contractor.id)

        busy_event = CalendarEvent(
            id="evt1",
            starts_at=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            ends_at=datetime(2026, 5, 4, 10, 0, tzinfo=UTC),
            summary="Existing appointment",
        )
        provider = _fake_provider(events=[busy_event])

        result = await handle_get_contractor_availability(
            {"date_from": "2026-05-04", "date_to": "2026-05-04"},
            db,
            session,
            _provider=provider,  # type: ignore[call-arg]
        )

        assert "09:00" not in result
        assert "10:00" in result

    async def test_invalid_dates_return_error(self, db: AsyncSession) -> None:
        _, _, session = await _make_client_session(db)

        result = await handle_get_contractor_availability(
            {"date_from": "not-a-date", "date_to": "2026-05-07"}, db, session
        )

        assert "inválid" in result.lower()

    async def test_date_to_before_date_from_returns_error(self, db: AsyncSession) -> None:
        _, _, session = await _make_client_session(db)

        result = await handle_get_contractor_availability(
            {"date_from": "2026-05-10", "date_to": "2026-05-07"}, db, session
        )

        assert "date_to" in result


# ---------------------------------------------------------------------------
# book_appointment
# ---------------------------------------------------------------------------


class TestBookAppointment:
    def _input(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "starts_at": "2026-05-05T10:00:00",
            "description": "Gotera en el baño",
        }
        base.update(overrides)
        return base

    async def test_appointment_persisted_in_db(self, db: AsyncSession) -> None:
        contractor, _, session = await _make_client_session(db)

        with patch("app.ai.handlers.client._send_to_contractor", new=AsyncMock()):
            await handle_book_appointment(self._input(), db, session)

        rows = await db.execute(
            select(Appointment).where(Appointment.contractor_id == contractor.id)
        )
        appointments = rows.scalars().all()
        assert len(appointments) == 1
        assert appointments[0].description == "Gotera en el baño"

    async def test_appointment_booked_by_client(self, db: AsyncSession) -> None:
        contractor, client, session = await _make_client_session(db)

        with patch("app.ai.handlers.client._send_to_contractor", new=AsyncMock()):
            await handle_book_appointment(self._input(), db, session)

        rows = await db.execute(
            select(Appointment).where(Appointment.contractor_id == contractor.id)
        )
        appt = rows.scalars().one()
        assert appt.booked_by == BookedBy.client
        assert appt.client_id == client.id
        assert appt.status == AppointmentStatus.scheduled
        assert appt.starts_at == datetime(2026, 5, 5, 10, 0, tzinfo=UTC)

    async def test_syncs_to_google_calendar_when_connected(self, db: AsyncSession) -> None:
        contractor, _, session = await _make_client_session(db)
        await _make_token(db, contractor.id)
        provider = _fake_provider()

        with patch("app.ai.handlers.client._send_to_contractor", new=AsyncMock()):
            result = await handle_book_appointment(
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
        assert appt.external_calendar_id == "gcal-event-id-456"
        assert appt.calendar_provider == CalendarProviderEnum.google

    async def test_google_calendar_failure_still_saves_appointment(
        self, db: AsyncSession
    ) -> None:
        contractor, _, session = await _make_client_session(db)
        await _make_token(db, contractor.id)

        failing_provider = AsyncMock()
        failing_provider.create_event = AsyncMock(side_effect=Exception("Google API down"))

        with patch("app.ai.handlers.client._send_to_contractor", new=AsyncMock()):
            result = await handle_book_appointment(
                self._input(),
                db,
                session,
                _provider=failing_provider,  # type: ignore[call-arg]
            )

        assert "Cita reservada" in result
        assert "No se pudo sincronizar" in result
        rows = await db.execute(
            select(Appointment).where(Appointment.contractor_id == contractor.id)
        )
        assert len(rows.scalars().all()) == 1

    async def test_notifies_contractor_on_booking(self, db: AsyncSession) -> None:
        contractor, client, session = await _make_client_session(db)
        mock_send = AsyncMock()

        with patch("app.ai.handlers.client._send_to_contractor", new=mock_send):
            await handle_book_appointment(self._input(), db, session)

        mock_send.assert_awaited_once()
        sent_contractor, sent_text = mock_send.call_args[0]
        assert sent_contractor.id == contractor.id
        assert client.name in sent_text
        assert "Gotera en el baño" in sent_text

    async def test_result_contains_description_and_time(self, db: AsyncSession) -> None:
        _, _, session = await _make_client_session(db)

        with patch("app.ai.handlers.client._send_to_contractor", new=AsyncMock()):
            result = await handle_book_appointment(
                self._input(description="Revisión caldera", starts_at="2026-06-10T14:30:00"),
                db,
                session,
            )

        assert "Revisión caldera" in result
        assert "14:30" in result

    async def test_invalid_starts_at_returns_error(self, db: AsyncSession) -> None:
        _, _, session = await _make_client_session(db)

        result = await handle_book_appointment(
            self._input(starts_at="not-a-datetime"), db, session
        )

        assert "inválido" in result.lower()

    async def test_missing_description_returns_error(self, db: AsyncSession) -> None:
        _, _, session = await _make_client_session(db)

        result = await handle_book_appointment(
            {"starts_at": "2026-05-05T10:00:00", "description": "  "}, db, session
        )

        assert "obligatorio" in result


# ---------------------------------------------------------------------------
# notify_contractor
# ---------------------------------------------------------------------------


class TestNotifyContractor:
    async def test_sends_telegram_message(self, db: AsyncSession) -> None:
        contractor, client, session = await _make_client_session(db)
        contractor.channel = Channel.telegram
        contractor.telegram_chat_id = "98765"
        await db.flush()

        with patch("app.ai.handlers.client.telegram_send", new=AsyncMock()) as mock_tg:
            result = await handle_notify_contractor(
                {"message": "¿Tiene garantía la reparación?"}, db, session
            )

        mock_tg.assert_awaited_once()
        recipient, sent_text = mock_tg.call_args[0]
        assert recipient == "98765"
        assert client.name in sent_text
        assert "garantía" in sent_text
        assert "responderá" in result.lower()

    async def test_sends_whatsapp_message_when_channel_whatsapp(
        self, db: AsyncSession
    ) -> None:
        contractor, _, session = await _make_client_session(db)
        contractor.channel = Channel.whatsapp
        await db.flush()

        with patch("app.ai.handlers.client.whatsapp_send", new=AsyncMock()) as mock_wa:
            result = await handle_notify_contractor(
                {"message": "Quiero un presupuesto"}, db, session
            )

        mock_wa.assert_awaited_once()
        recipient, _ = mock_wa.call_args[0]
        assert recipient == contractor.phone_number
        assert "responderá" in result.lower()

    async def test_includes_client_name_in_notification(self, db: AsyncSession) -> None:
        contractor, client, session = await _make_client_session(db)
        contractor.channel = Channel.telegram
        contractor.telegram_chat_id = "11111"
        await db.flush()

        with patch("app.ai.handlers.client.telegram_send", new=AsyncMock()) as mock_tg:
            await handle_notify_contractor(
                {"message": "¿Cuándo pueden venir?"}, db, session
            )

        _, sent_text = mock_tg.call_args[0]
        assert client.name in sent_text

    async def test_empty_message_returns_error(self, db: AsyncSession) -> None:
        _, _, session = await _make_client_session(db)

        result = await handle_notify_contractor({"message": ""}, db, session)

        assert "obligatorio" in result
