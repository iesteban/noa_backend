from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dispatcher import register
from app.calendar.base import CalendarEvent, CalendarProvider
from app.calendar.google import GoogleCalendarProvider
from app.config import settings
from app.models.appointment import (
    Appointment,
    AppointmentStatus,
    BookedBy,
    CalendarProviderEnum,
    CalendarToken,
)
from app.models.session import ConversationSession

logger = logging.getLogger(__name__)

_WORK_START = time(9, 0)
_WORK_END = time(18, 0)
_SLOT_MINUTES = 60
_MAX_SLOTS = 10


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_token(
    db: AsyncSession, contractor_id: uuid.UUID
) -> CalendarToken | None:
    result = await db.execute(
        select(CalendarToken).where(
            CalendarToken.contractor_id == contractor_id,
            CalendarToken.access_token.is_not(None),
        )
    )
    return result.scalar_one_or_none()


def _connect_url(state: str) -> str:
    base = settings.google_redirect_uri.replace("/auth/google/callback", "")
    return f"{base}/auth/google/connect?state={state}"


def _compute_free_slots(
    date_from: date,
    date_to: date,
    busy: list[CalendarEvent],
) -> list[tuple[datetime, datetime]]:
    slots: list[tuple[datetime, datetime]] = []
    current = date_from
    while current <= date_to and len(slots) < _MAX_SLOTS:
        if current.weekday() < 5:  # Mon–Fri
            slot_start = datetime.combine(current, _WORK_START, tzinfo=UTC)
            day_end = datetime.combine(current, _WORK_END, tzinfo=UTC)
            while slot_start + timedelta(minutes=_SLOT_MINUTES) <= day_end:
                slot_end = slot_start + timedelta(minutes=_SLOT_MINUTES)
                if not any(
                    slot_start < ev.ends_at and slot_end > ev.starts_at for ev in busy
                ):
                    slots.append((slot_start, slot_end))
                    if len(slots) >= _MAX_SLOTS:
                        break
                slot_start = slot_end
        current += timedelta(days=1)
    return slots


def _format_slots(slots: list[tuple[datetime, datetime]]) -> str:
    if not slots:
        return "No hay huecos disponibles en ese rango."
    lines = ["Huecos disponibles:"]
    prev_date: date | None = None
    for start, _ in slots:
        d = start.date()
        if d != prev_date:
            lines.append(f"\n{start.strftime('%A %-d %B').capitalize()}:")
            prev_date = d
        lines.append(f"  • {start.strftime('%H:%M')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@register("connect_google_calendar")
async def handle_connect_google_calendar(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    state = str(uuid.uuid4())

    # Remove any existing token (pending or active) so the INSERT doesn't conflict.
    await db.execute(
        delete(CalendarToken).where(
            CalendarToken.contractor_id == session.contractor_id,
            CalendarToken.provider == CalendarProviderEnum.google,
        )
    )

    token = CalendarToken(
        contractor_id=session.contractor_id,
        provider=CalendarProviderEnum.google,
        state=state,
    )
    db.add(token)
    await db.flush()

    url = _connect_url(state)
    return (
        f"Para conectar Google Calendar haz clic en este enlace "
        f"(válido para una sola vez):\n{url}"
    )


@register("get_availability")
async def handle_get_availability(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
    _provider: CalendarProvider | None = None,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    try:
        date_from = date.fromisoformat(str(tool_input["date_from"]))
        date_to = date.fromisoformat(str(tool_input["date_to"]))
    except (KeyError, ValueError):
        return "Fechas inválidas — usa formato YYYY-MM-DD."

    if date_to < date_from:
        return "date_to debe ser igual o posterior a date_from."

    token = await _get_token(db, session.contractor_id)
    if token is None:
        state = str(uuid.uuid4())
        await db.execute(
            delete(CalendarToken).where(
                CalendarToken.contractor_id == session.contractor_id,
                CalendarToken.provider == CalendarProviderEnum.google,
                CalendarToken.access_token.is_(None),
            )
        )
        pending = CalendarToken(
            contractor_id=session.contractor_id,
            provider=CalendarProviderEnum.google,
            state=state,
        )
        db.add(pending)
        await db.flush()
        url = _connect_url(state)
        return (
            "No tienes Google Calendar conectado. "
            f"Conéctalo aquí para ver tu disponibilidad real:\n{url}"
        )

    provider = _provider or GoogleCalendarProvider(token, db)
    start_dt = datetime.combine(date_from, _WORK_START, tzinfo=UTC)
    end_dt = datetime.combine(date_to, _WORK_END, tzinfo=UTC)

    try:
        busy = await provider.list_events(session.contractor_id, start_dt, end_dt)
    except Exception:
        logger.exception(
            "Google Calendar list_events failed for contractor %s", session.contractor_id
        )
        return "No se pudo consultar el calendario. Inténtalo de nuevo."

    slots = _compute_free_slots(date_from, date_to, busy)
    return _format_slots(slots)


@register("create_appointment")
async def handle_create_appointment(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
    _provider: CalendarProvider | None = None,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    try:
        starts_at = datetime.fromisoformat(str(tool_input["starts_at"]))
    except (KeyError, ValueError):
        return "starts_at inválido — usa formato ISO 8601."

    try:
        duration_minutes = int(tool_input["duration_minutes"])
    except (KeyError, TypeError, ValueError):
        return "duration_minutes inválido — debe ser un entero."

    description = str(tool_input.get("description", "")).strip()
    if not description:
        return "description es obligatorio."

    client_id: uuid.UUID | None = None
    raw_client = tool_input.get("client_id")
    if raw_client:
        try:
            client_id = uuid.UUID(str(raw_client))
        except ValueError:
            return "client_id inválido — debe ser un UUID."

    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)

    if starts_at < datetime.now(UTC):
        return "starts_at está en el pasado — usa una fecha y hora futuras."

    appointment = Appointment(
        contractor_id=session.contractor_id,
        client_id=client_id,
        starts_at=starts_at,
        duration_minutes=duration_minutes,
        description=description,
        status=AppointmentStatus.scheduled,
        booked_by=BookedBy.contractor,
    )
    db.add(appointment)
    await db.flush()

    calendar_note = ""
    token = await _get_token(db, session.contractor_id)
    if token is not None:
        provider = _provider or GoogleCalendarProvider(token, db)
        try:
            event_id = await provider.create_event(appointment)
            appointment.calendar_provider = CalendarProviderEnum.google
            appointment.external_calendar_id = event_id
            await db.flush()
            calendar_note = " | Sincronizado con Google Calendar ✓"
        except Exception:
            logger.exception(
                "Google Calendar create_event failed for contractor %s", session.contractor_id
            )
            calendar_note = " | (No se pudo sincronizar con Google Calendar)"

    starts_str = starts_at.strftime("%-d %b %Y a las %H:%M")
    return (
        f"Cita creada."
        f" id={appointment.id}"
        f" | {description}"
        f" | {starts_str}"
        f" | {duration_minutes} min"
        f"{calendar_note}"
    )
