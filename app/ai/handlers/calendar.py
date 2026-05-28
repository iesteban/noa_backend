from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dispatcher import register
from app.ai.handlers.working_hours import load_working_hours
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
from app.models.client import Client
from app.models.contractor import Contractor
from app.models.session import ConversationSession
from app.models.working_hours import WorkingHours

logger = logging.getLogger(__name__)

_WORK_START = time(9, 0)
_WORK_END = time(18, 0)
_SLOT_MINUTES = 60
_MAX_SLOTS = 10

_WORKING_HOURS_NUDGE_FLAG = "working_hours_nudge_shown"
_WORKING_HOURS_NUDGE_INSTRUCTION = (
    "\n\n[SYSTEM NUDGE — show to contractor on top of the answer above, "
    "only once per session]\n"
    "El contratista aún no tiene horario laboral configurado. "
    "Pregúntale en este turno, después de tu respuesta normal: "
    "«Por cierto, aún no tienes horario laboral configurado. "
    "¿Quieres indicarme en qué horas quieres que se agenden las citas automáticamente?» "
    "Si dice que sí, recoge los días y horas y llama a set_working_hours. "
    "Si dice que ahora no, sigue con la conversación normal y no insistas más en este turno."
)


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
    working_hours: dict[int, WorkingHours] | None = None,
    slot_minutes: int = _SLOT_MINUTES,
) -> list[tuple[datetime, datetime]]:
    slots: list[tuple[datetime, datetime]] = []
    current = date_from
    while current <= date_to and len(slots) < _MAX_SLOTS:
        dow = current.weekday()
        if working_hours:
            wh = working_hours.get(dow)
            if wh is None or not wh.is_working_day or not wh.start_time or not wh.end_time:
                current += timedelta(days=1)
                continue
            work_start = wh.start_time
            work_end = wh.end_time
        else:
            # Default: Mon–Fri 09:00–18:00
            if dow >= 5:
                current += timedelta(days=1)
                continue
            work_start = _WORK_START
            work_end = _WORK_END

        slot_start = datetime.combine(current, work_start, tzinfo=UTC)
        day_end = datetime.combine(current, work_end, tzinfo=UTC)
        while slot_start + timedelta(minutes=slot_minutes) <= day_end:
            slot_end = slot_start + timedelta(minutes=slot_minutes)
            if not any(slot_start < ev.ends_at and slot_end > ev.starts_at for ev in busy):
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


_DAY_NAMES_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


async def _check_working_hours(
    db: AsyncSession,
    contractor_id: uuid.UUID,
    starts_at: datetime,
) -> str | None:
    """Return a warning string if starts_at is outside working hours, else None."""
    schedule = await load_working_hours(db, contractor_id)
    if not schedule:
        return None

    dow = starts_at.weekday()
    wh = schedule.get(dow)
    day_name = _DAY_NAMES_ES[dow]

    if wh is None:
        return None

    if not wh.is_working_day:
        return (
            f"El {day_name} no está en tu horario habitual. "
            "¿Confirmas igualmente? (llama a create_appointment con force=true si sí)"
        )

    appt_time = starts_at.time()
    if wh.start_time and wh.end_time:
        if appt_time < wh.start_time or appt_time >= wh.end_time:
            return (
                f"Las {starts_at.strftime('%H:%M')} del {day_name} están fuera de tu horario "
                f"({wh.start_time.strftime('%H:%M')}–{wh.end_time.strftime('%H:%M')}). "
                "¿Confirmas igualmente? (llama a create_appointment con force=true si sí)"
            )

    return None


async def _maybe_working_hours_nudge(
    db: AsyncSession,
    session: ConversationSession,
    contractor_id: uuid.UUID,
) -> str:
    """Return a one-shot nudge suffix when working hours are unset, else ''.

    The nudge fires at most once per session: it is gated by a flag stored on
    session.context. Once shown — or once working hours have been configured —
    subsequent calls in the same or future sessions return an empty string.
    """
    if session.context.get(_WORKING_HOURS_NUDGE_FLAG):
        return ""
    schedule = await load_working_hours(db, contractor_id)
    if schedule:
        return ""
    session.context = {**session.context, _WORKING_HOURS_NUDGE_FLAG: True}
    await db.flush()
    return _WORKING_HOURS_NUDGE_INSTRUCTION


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
        nudge = await _maybe_working_hours_nudge(db, session, session.contractor_id)
        return (
            "No tienes Google Calendar conectado. "
            f"Conéctalo aquí para ver tu disponibilidad real:\n{url}{nudge}"
        )

    provider = _provider or GoogleCalendarProvider(token, db)
    working_hours = await load_working_hours(db, session.contractor_id)

    start_dt = datetime.combine(date_from, _WORK_START, tzinfo=UTC)
    end_dt = datetime.combine(date_to, _WORK_END, tzinfo=UTC)

    try:
        busy = await provider.list_events(session.contractor_id, start_dt, end_dt)
    except Exception:
        logger.exception(
            "Google Calendar list_events failed for contractor %s", session.contractor_id
        )
        return "No se pudo consultar el calendario. Inténtalo de nuevo."

    slots = _compute_free_slots(date_from, date_to, busy, working_hours or None)
    nudge = await _maybe_working_hours_nudge(db, session, session.contractor_id)
    return _format_slots(slots) + nudge


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

    force = bool(tool_input.get("force", False))

    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)

    if starts_at < datetime.now(UTC):
        return "starts_at está en el pasado — usa una fecha y hora futuras."

    if not force:
        warning = await _check_working_hours(db, session.contractor_id, starts_at)
        if warning:
            return warning

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
    nudge = await _maybe_working_hours_nudge(db, session, session.contractor_id)
    return (
        f"Cita creada."
        f" id={appointment.id}"
        f" | {description}"
        f" | {starts_str}"
        f" | {duration_minutes} min"
        f"{calendar_note}{nudge}"
    )


async def _create_pending_appointment(
    db: AsyncSession,
    contractor_id: uuid.UUID,
    client_id: uuid.UUID,
    duration_minutes: int,
    description: str,
) -> Appointment:
    # Placeholder start; updated when the client confirms a specific slot.
    placeholder_starts_at = datetime(9999, 1, 1, 0, 0, 0, tzinfo=UTC)
    appointment = Appointment(
        contractor_id=contractor_id,
        client_id=client_id,
        starts_at=placeholder_starts_at,
        duration_minutes=duration_minutes,
        description=description,
        status=AppointmentStatus.pending_client,
        booked_by=BookedBy.contractor,
    )
    db.add(appointment)
    await db.flush()
    return appointment


async def _send_appointment_request_template(
    client: Client,
    contractor: Contractor,
    description: str,
) -> str:
    from app.messaging.whatsapp_sender import send_template_message

    client_first_name = client.name.split()[0]
    business_name = contractor.business_name or contractor.name
    try:
        await send_template_message(
            recipient_id=client.phone_number,
            template_name="appointment_request_v2",
            language_code="es",
            body_parameters=[client_first_name, business_name, description],
        )
        return "Plantilla de WhatsApp enviada al cliente ✓"
    except Exception:
        logger.exception("WhatsApp template send failed for client %s", client.id)
        return "No se pudo enviar el mensaje de WhatsApp al cliente"


@register("initiate_appointment")
async def handle_initiate_appointment(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    raw_client = tool_input.get("client_id")
    if not raw_client:
        return "client_id es obligatorio."
    try:
        client_id = uuid.UUID(str(raw_client))
    except ValueError:
        return "client_id inválido — debe ser un UUID."

    try:
        duration_minutes = int(tool_input["duration_minutes"])
    except (KeyError, TypeError, ValueError):
        return "duration_minutes inválido — debe ser un entero."

    description = str(tool_input.get("description", "")).strip()
    if not description:
        return "description es obligatorio."

    client_result = await db.execute(
        select(Client).where(
            Client.id == client_id,
            Client.contractor_id == session.contractor_id,
        )
    )
    client = client_result.scalar_one_or_none()
    if client is None:
        return "Cliente no encontrado."

    contractor_result = await db.execute(
        select(Contractor).where(Contractor.id == session.contractor_id)
    )
    contractor = contractor_result.scalar_one_or_none()
    if contractor is None:
        return "Session error: contractor not found."

    appointment = await _create_pending_appointment(
        db, session.contractor_id, client_id, duration_minutes, description
    )
    send_note = await _send_appointment_request_template(client, contractor, description)
    nudge = await _maybe_working_hours_nudge(db, session, session.contractor_id)

    return (
        f"Cita pendiente creada. id={appointment.id} | "
        f"Cliente: {client.name} | Duración: {duration_minutes} min | "
        f"Servicio: {description} | {send_note}{nudge}"
    )
