"""Unit tests for GoogleCalendarProvider._build_event_body."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.appointment import BookedBy


def _make_appointment(
    *,
    description: str = "Reparación grifo",
    starts_at: datetime = datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
    duration_minutes: int = 60,
    booked_by: BookedBy = BookedBy.contractor,
    client_id: object = None,
    contractor_id: object = None,
) -> object:
    appt = SimpleNamespace(
        description=description,
        starts_at=starts_at,
        duration_minutes=duration_minutes,
        booked_by=booked_by,
        client_id=client_id,
        contractor_id=contractor_id,
    )
    return appt


def _make_client(
    *,
    name: str = "Ana López",
    phone_number: str = "+34600000001",
    nif: str | None = None,
    notes: str | None = None,
) -> object:
    return SimpleNamespace(name=name, phone_number=phone_number, nif=nif, notes=notes)


def _make_contractor(*, name: str = "Pedro García", business_name: str | None = None) -> object:
    return SimpleNamespace(name=name, business_name=business_name)


def _provider() -> object:
    """Return a GoogleCalendarProvider with a stubbed DB session."""
    from app.calendar.google import GoogleCalendarProvider

    token = SimpleNamespace(
        access_token="tok",
        refresh_token="ref",
        expires_at=None,
    )
    db = MagicMock()
    return GoogleCalendarProvider(token, db)  # type: ignore[arg-type]


class TestBuildEventBody:
    def test_summary_is_appointment_description(self) -> None:
        appt = _make_appointment(description="Cambio de caldera")
        body = _provider()._build_event_body(appt, None, None)  # type: ignore[attr-defined]
        assert body["summary"] == "Cambio de caldera"

    def test_start_and_end_times(self) -> None:
        appt = _make_appointment(
            starts_at=datetime(2026, 6, 1, 9, 30, tzinfo=UTC), duration_minutes=90
        )
        body = _provider()._build_event_body(appt, None, None)  # type: ignore[attr-defined]
        assert "09:30" in body["start"]["dateTime"]
        assert "11:00" in body["end"]["dateTime"]
        assert body["start"]["timeZone"] == "Europe/Madrid"
        assert body["end"]["timeZone"] == "Europe/Madrid"

    def test_no_client_no_description_field(self) -> None:
        appt = _make_appointment(booked_by=BookedBy.contractor)
        body = _provider()._build_event_body(appt, None, None)  # type: ignore[attr-defined]
        assert "description" not in body

    def test_client_name_and_phone_in_description(self) -> None:
        appt = _make_appointment()
        client = _make_client(name="Ana López", phone_number="+34600000001")
        body = _provider()._build_event_body(appt, client, None)  # type: ignore[attr-defined]
        assert "Ana López" in body["description"]
        assert "+34600000001" in body["description"]

    def test_client_nif_included_when_present(self) -> None:
        appt = _make_appointment()
        client = _make_client(nif="12345678Z")
        body = _provider()._build_event_body(appt, client, None)  # type: ignore[attr-defined]
        assert "12345678Z" in body["description"]

    def test_client_nif_omitted_when_none(self) -> None:
        appt = _make_appointment()
        client = _make_client(nif=None)
        body = _provider()._build_event_body(appt, client, None)  # type: ignore[attr-defined]
        assert "NIF" not in body["description"]

    def test_client_notes_included_when_present(self) -> None:
        appt = _make_appointment()
        client = _make_client(notes="Cliente preferente")
        body = _provider()._build_event_body(appt, client, None)  # type: ignore[attr-defined]
        assert "Cliente preferente" in body["description"]

    def test_client_notes_omitted_when_none(self) -> None:
        appt = _make_appointment()
        client = _make_client(notes=None)
        body = _provider()._build_event_body(appt, client, None)  # type: ignore[attr-defined]
        assert "Notas" not in body["description"]

    def test_booked_by_client_adds_indicator(self) -> None:
        appt = _make_appointment(booked_by=BookedBy.client)
        client = _make_client()
        body = _provider()._build_event_body(appt, client, None)  # type: ignore[attr-defined]
        assert "Reservada por el cliente" in body["description"]

    def test_booked_by_contractor_no_indicator(self) -> None:
        appt = _make_appointment(booked_by=BookedBy.contractor)
        client = _make_client()
        body = _provider()._build_event_body(appt, client, None)  # type: ignore[attr-defined]
        assert "Reservada por el cliente" not in body["description"]

    def test_booked_by_client_no_client_still_adds_indicator(self) -> None:
        appt = _make_appointment(booked_by=BookedBy.client)
        body = _provider()._build_event_body(appt, None, None)  # type: ignore[attr-defined]
        assert "Reservada por el cliente" in body["description"]
