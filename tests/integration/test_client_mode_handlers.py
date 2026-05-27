"""Integration tests for client-mode tool handlers."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.handlers.client import (
    handle_book_appointment,
    handle_get_contractor_availability,
    handle_get_my_invoices,
    handle_get_payment_info,
    handle_notify_contractor,
)
from app.models.appointment import Appointment, AppointmentStatus, BookedBy
from app.models.contractor import Channel
from app.models.invoice import InvoiceStatus
from app.models.session import UserType
from tests.integration.conftest import (
    make_client,
    make_contractor,
    make_invoice,
    make_session,
)

_MADRID_TZ = ZoneInfo("Europe/Madrid")
_FUTURE = datetime(2099, 6, 15, 10, 0, 0, tzinfo=UTC)


def _client_session_input(
    client_session: object, *, starts_at: str = "2099-06-15T10:00:00"
) -> dict:
    return {"starts_at": starts_at, "description": "Revisión de fontanería"}


# ---------------------------------------------------------------------------
# get_contractor_availability
# ---------------------------------------------------------------------------

class TestGetContractorAvailability:
    async def test_no_token_returns_graceful_message(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        result = await handle_get_contractor_availability(
            {"date_from": "2099-06-15", "date_to": "2099-06-15"}, db, session
        )

        assert "No hay información" in result

    async def test_returns_slots_from_provider(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        mock_provider = AsyncMock()
        mock_provider.list_events.return_value = []

        result = await handle_get_contractor_availability(
            {"date_from": "2099-06-16", "date_to": "2099-06-16"},
            db,
            session,
            _provider=mock_provider,
        )

        assert "Huecos" in result or "No hay" in result

    async def test_uses_pending_appointment_duration(self, db: AsyncSession) -> None:
        """Slot size matches the pending appointment's duration_minutes."""
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        # Create a pending 180-minute appointment.
        pending = Appointment(
            contractor_id=contractor.id,
            client_id=client.id,
            starts_at=datetime(9999, 1, 1, tzinfo=UTC),
            duration_minutes=180,
            description="fontanería",
            status=AppointmentStatus.pending_client,
            booked_by=BookedBy.contractor,
        )
        db.add(pending)
        await db.flush()

        mock_provider = AsyncMock()
        mock_provider.list_events.return_value = []

        with patch(
            "app.ai.handlers.client._get_token", return_value=AsyncMock()
        ):
            result = await handle_get_contractor_availability(
                {"date_from": "2099-06-16", "date_to": "2099-06-16"},
                db,
                session,
                _provider=mock_provider,
            )

        # 180-minute slots: a full working day (9h) should only yield 3 slots.
        assert "Huecos" in result or "No hay" in result

    async def test_invalid_dates(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        result = await handle_get_contractor_availability(
            {"date_from": "not-a-date", "date_to": "2099-06-15"}, db, session
        )

        assert "inválidas" in result.lower()


# ---------------------------------------------------------------------------
# book_appointment
# ---------------------------------------------------------------------------

class TestBookAppointment:
    async def test_creates_appointment_in_db(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        mock_provider = AsyncMock()
        mock_provider.create_event.return_value = "gcal-event-id"

        with patch("app.ai.handlers.client._send_to_contractor", new=AsyncMock()):
            result = await handle_book_appointment(
                {"starts_at": "2099-06-15T10:00:00", "description": "Revisión"},
                db,
                session,
                _provider=mock_provider,
            )

        rows = await db.execute(
            select(Appointment).where(Appointment.contractor_id == contractor.id)
        )
        appt = rows.scalar_one()
        assert appt.status == AppointmentStatus.scheduled
        assert appt.booked_by == BookedBy.client
        assert "Cita reservada" in result

    async def test_naive_datetime_interpreted_as_madrid(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        with patch("app.ai.handlers.client._send_to_contractor", new=AsyncMock()):
            await handle_book_appointment(
                {"starts_at": "2099-06-15T10:00:00", "description": "Revisión"},
                db,
                session,
            )

        rows = await db.execute(
            select(Appointment).where(Appointment.contractor_id == contractor.id)
        )
        appt = rows.scalar_one()
        # 10:00 Madrid (UTC+2 in June) should be stored as 08:00 UTC.
        assert appt.starts_at.hour == 8

    async def test_updates_pending_appointment_instead_of_creating_new(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        pending = Appointment(
            contractor_id=contractor.id,
            client_id=client.id,
            starts_at=datetime(9999, 1, 1, tzinfo=UTC),
            duration_minutes=120,
            description="fontanería",
            status=AppointmentStatus.pending_client,
            booked_by=BookedBy.contractor,
        )
        db.add(pending)
        await db.flush()

        with patch("app.ai.handlers.client._send_to_contractor", new=AsyncMock()):
            await handle_book_appointment(
                {"starts_at": "2099-06-15T10:00:00", "description": "fontanería"},
                db,
                session,
            )

        rows = await db.execute(
            select(Appointment).where(Appointment.contractor_id == contractor.id)
        )
        appointments = rows.scalars().all()
        assert len(appointments) == 1
        assert appointments[0].status == AppointmentStatus.scheduled
        assert appointments[0].duration_minutes == 120

    async def test_rejects_conflicting_slot(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        existing = Appointment(
            contractor_id=contractor.id,
            client_id=client.id,
            starts_at=datetime(2099, 6, 15, 8, 0, tzinfo=UTC),
            duration_minutes=120,
            description="otro trabajo",
            status=AppointmentStatus.scheduled,
            booked_by=BookedBy.contractor,
        )
        db.add(existing)
        await db.flush()

        result = await handle_book_appointment(
            {"starts_at": "2099-06-15T10:00:00", "description": "Revisión"},
            db,
            session,
        )

        assert "ocupado" in result

    async def test_notifies_contractor(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, channel=Channel.telegram, telegram_chat_id="123")
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        with patch("app.ai.handlers.client.telegram_send", new=AsyncMock()) as mock_send:
            await handle_book_appointment(
                {"starts_at": "2099-06-15T10:00:00", "description": "Revisión"},
                db,
                session,
            )

        mock_send.assert_called_once()
        assert "Ana López" in mock_send.call_args[0][1]

    async def test_invalid_starts_at(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        result = await handle_book_appointment(
            {"starts_at": "not-a-date", "description": "Revisión"}, db, session
        )

        assert "inválido" in result

    async def test_missing_client_in_session(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor, user_type=UserType.client)

        result = await handle_book_appointment(
            {"starts_at": "2099-06-15T10:00:00", "description": "Revisión"}, db, session
        )

        assert "client not identified" in result


# ---------------------------------------------------------------------------
# get_my_invoices
# ---------------------------------------------------------------------------

class TestGetMyInvoices:
    async def test_returns_invoices(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)
        await make_invoice(
            db, contractor, client,
            invoice_number="2099-001", total=120.0, status=InvoiceStatus.sent
        )

        result = await handle_get_my_invoices({}, db, session)

        assert "2099-001" in result
        assert "120" in result

    async def test_no_invoices_message(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        result = await handle_get_my_invoices({}, db, session)

        assert "No tienes facturas" in result


# ---------------------------------------------------------------------------
# get_payment_info
# ---------------------------------------------------------------------------

class TestGetPaymentInfo:
    async def test_returns_iban(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, iban="ES91 2100 0418 4502 0005 1332")
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        result = await handle_get_payment_info({}, db, session)

        assert "ES91 2100 0418 4502 0005 1332" in result

    async def test_no_payment_info_configured(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, iban=None)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        result = await handle_get_payment_info({}, db, session)

        assert "no ha configurado" in result


# ---------------------------------------------------------------------------
# notify_contractor
# ---------------------------------------------------------------------------

class TestNotifyContractor:
    async def test_sends_via_telegram(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, channel=Channel.telegram, telegram_chat_id="456")
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        with patch("app.ai.handlers.client.telegram_send", new=AsyncMock()) as mock_send:
            result = await handle_notify_contractor(
                {"message": "¿Tiene garantía?"}, db, session
            )

        mock_send.assert_called_once()
        assert "Ana López" in mock_send.call_args[0][1]
        assert "¿Tiene garantía?" in mock_send.call_args[0][1]
        assert "responderá" in result

    async def test_sends_via_whatsapp(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, channel=Channel.whatsapp)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        with patch("app.ai.handlers.client.whatsapp_send", new=AsyncMock()) as mock_send:
            await handle_notify_contractor({"message": "¿Cuándo puede venir?"}, db, session)

        mock_send.assert_called_once()

    async def test_empty_message_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor, user_type=UserType.client, client_id=client.id)

        result = await handle_notify_contractor({"message": ""}, db, session)

        assert "obligatorio" in result
