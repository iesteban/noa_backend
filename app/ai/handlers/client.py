"""Client-mode tool handlers: availability, booking, invoices, payment, escalation."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dispatcher import register
from app.ai.handlers.calendar import (
    _WORK_END,
    _WORK_START,
    _compute_free_slots,
    _get_token,
)
from app.ai.handlers.working_hours import load_working_hours
from app.calendar.base import CalendarProvider
from app.calendar.google import GoogleCalendarProvider
from app.messaging.telegram_sender import send_message as telegram_send
from app.messaging.whatsapp_sender import send_message as whatsapp_send
from app.models.appointment import (
    Appointment,
    AppointmentStatus,
    BookedBy,
    CalendarProviderEnum,
)
from app.models.client import Client
from app.models.contractor import Channel, Contractor
from app.models.invoice import Invoice
from app.models.session import ConversationSession

logger = logging.getLogger(__name__)

_MADRID_TZ = ZoneInfo("Europe/Madrid")
_DEFAULT_DURATION_MINUTES = 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _send_to_contractor(contractor: Contractor, message: str) -> None:
    try:
        if contractor.channel == Channel.telegram and contractor.telegram_chat_id:
            await telegram_send(contractor.telegram_chat_id, message)
        elif contractor.channel == Channel.whatsapp:
            await whatsapp_send(contractor.phone_number, message)
        else:
            logger.warning(
                "Cannot notify contractor %s: channel=%s telegram_chat_id=%s",
                contractor.id,
                contractor.channel,
                contractor.telegram_chat_id,
            )
    except Exception:
        logger.exception("Failed to notify contractor %s", contractor.id)


async def _get_pending_appointment(
    db: AsyncSession, session: ConversationSession
) -> Appointment | None:
    """Return the most recent pending_client appointment for this (contractor, client) pair."""
    if session.client_id is None:
        return None
    result = await db.execute(
        select(Appointment)
        .where(
            Appointment.contractor_id == session.contractor_id,
            Appointment.client_id == session.client_id,
            Appointment.status == AppointmentStatus.pending_client,
        )
        .order_by(Appointment.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _format_slots_madrid(slots: list[tuple[datetime, datetime]]) -> str:
    if not slots:
        return "No hay huecos disponibles en ese rango."
    lines = ["Huecos disponibles:"]
    prev_date: date | None = None
    for start, end in slots:
        start_mad = start.astimezone(_MADRID_TZ)
        end_mad = end.astimezone(_MADRID_TZ)
        d = start_mad.date()
        if d != prev_date:
            lines.append(f"\n{start_mad.strftime('%A %-d %B').capitalize()}:")
            prev_date = d
        lines.append(f"  • {start_mad.strftime('%H:%M')}–{end_mad.strftime('%H:%M')}")
    return "\n".join(lines)


async def _check_slot_conflict(
    db: AsyncSession,
    contractor_id: object,
    starts_at: datetime,
    duration_minutes: int,
) -> bool:
    """Return True if the slot overlaps any scheduled or pending appointment."""
    import uuid as _uuid
    cid: _uuid.UUID = contractor_id  # type: ignore[assignment]
    slot_end = starts_at + timedelta(minutes=duration_minutes)
    result = await db.execute(
        select(Appointment).where(
            Appointment.contractor_id == cid,
            Appointment.status.in_(
                [AppointmentStatus.scheduled, AppointmentStatus.pending_client]
            ),
            Appointment.starts_at < slot_end,
        )
    )
    existing = result.scalars().all()
    return any(
        starts_at < appt.starts_at + timedelta(minutes=appt.duration_minutes)
        for appt in existing
    )


async def _sync_to_calendar(
    db: AsyncSession,
    appointment: Appointment,
    session: ConversationSession,
    provider: CalendarProvider | None,
) -> str:
    if session.contractor_id is None:
        return ""
    token = await _get_token(db, session.contractor_id)
    if token is None:
        return ""
    cal = provider or GoogleCalendarProvider(token, db)
    try:
        event_id = await cal.create_event(appointment)
        appointment.calendar_provider = CalendarProviderEnum.google
        appointment.external_calendar_id = event_id
        await db.flush()
        return " | Sincronizado con Google Calendar ✓"
    except Exception:
        logger.exception(
            "Google Calendar create_event failed for contractor %s", session.contractor_id
        )
        return " | (No se pudo sincronizar con Google Calendar)"


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@register("get_contractor_availability")
async def handle_get_contractor_availability(
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

    pending = await _get_pending_appointment(db, session)
    slot_minutes = pending.duration_minutes if pending else _DEFAULT_DURATION_MINUTES

    token = await _get_token(db, session.contractor_id)
    if token is None:
        return "No hay información de disponibilidad online para esas fechas."

    provider = _provider or GoogleCalendarProvider(token, db)
    working_hours = await load_working_hours(db, session.contractor_id)
    start_dt = datetime.combine(date_from, _WORK_START)
    end_dt = datetime.combine(date_to, _WORK_END)

    try:
        busy = await provider.list_events(session.contractor_id, start_dt, end_dt)
    except Exception:
        logger.exception(
            "Google Calendar list_events failed for contractor %s", session.contractor_id
        )
        return "No se pudo consultar la disponibilidad. Inténtalo de nuevo."

    slots = _compute_free_slots(date_from, date_to, busy, working_hours, slot_minutes)
    return _format_slots_madrid(slots)


@register("book_appointment")
async def handle_book_appointment(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
    _provider: CalendarProvider | None = None,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."
    if session.client_id is None:
        return "Session error: client not identified."

    try:
        starts_at = datetime.fromisoformat(str(tool_input["starts_at"]))
    except (KeyError, ValueError):
        return "starts_at inválido — usa formato ISO 8601."

    description = str(tool_input.get("description", "")).strip()
    if not description:
        return "description es obligatorio."

    # Treat naive datetimes as Madrid local time, not UTC.
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=_MADRID_TZ)

    pending = await _get_pending_appointment(db, session)
    duration_minutes = pending.duration_minutes if pending else _DEFAULT_DURATION_MINUTES

    if await _check_slot_conflict(db, session.contractor_id, starts_at, duration_minutes):
        return "Este horario ya está ocupado. Por favor, elige otro."

    if pending is not None:
        pending.starts_at = starts_at
        pending.description = description
        pending.status = AppointmentStatus.scheduled
        appointment = pending
    else:
        appointment = Appointment(
            contractor_id=session.contractor_id,
            client_id=session.client_id,
            starts_at=starts_at,
            duration_minutes=duration_minutes,
            description=description,
            status=AppointmentStatus.scheduled,
            booked_by=BookedBy.client,
        )
        db.add(appointment)
    await db.flush()

    calendar_note = await _sync_to_calendar(db, appointment, session, _provider)

    contractor_result = await db.execute(
        select(Contractor).where(Contractor.id == session.contractor_id)
    )
    contractor = contractor_result.scalar_one_or_none()
    if contractor is not None:
        client_result = await db.execute(
            select(Client).where(Client.id == session.client_id)
        )
        client = client_result.scalar_one_or_none()
        client_name = client.name if client else "Un cliente"
        starts_str = starts_at.astimezone(_MADRID_TZ).strftime("%-d %b %Y a las %H:%M")
        await _send_to_contractor(
            contractor,
            f"Nueva cita: {client_name} — {description} — {starts_str}",
        )

    starts_str = starts_at.astimezone(_MADRID_TZ).strftime("%-d %b %Y a las %H:%M")
    return (
        f"Cita reservada. {description} | {starts_str}{calendar_note}. "
        "El profesional ha sido notificado."
    )


@register("get_my_invoices")
async def handle_get_my_invoices(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    if session.client_id is None:
        return "Session error: client not identified."

    result = await db.execute(
        select(Invoice)
        .where(Invoice.client_id == session.client_id)
        .order_by(Invoice.created_at.desc())
        .limit(10)
    )
    invoices = result.scalars().all()

    if not invoices:
        return "No tienes facturas con este profesional."

    lines = ["Tus facturas:"]
    for inv in invoices:
        status_label = {
            "draft": "Borrador",
            "sent": "Enviada",
            "paid": "Pagada",
            "overdue": "Vencida",
        }.get(inv.status, inv.status)
        lines.append(f"  • Factura {inv.invoice_number} — {float(inv.total):.2f}€ — {status_label}")
    return "\n".join(lines)


@register("get_payment_info")
async def handle_get_payment_info(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    result = await db.execute(
        select(Contractor).where(Contractor.id == session.contractor_id)
    )
    contractor = result.scalar_one_or_none()
    if contractor is None:
        return "Session error: contractor not found."

    parts: list[str] = []
    if contractor.iban:
        parts.append(f"Transferencia bancaria — IBAN: {contractor.iban}")
    if not parts:
        return "El profesional aún no ha configurado sus datos de pago."
    return "Datos de pago:\n" + "\n".join(parts)


@register("notify_contractor")
async def handle_notify_contractor(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    message = str(tool_input.get("message", "")).strip()
    if not message:
        return "message es obligatorio."

    if session.contractor_id is None:
        return "Session error: contractor not identified."

    contractor_result = await db.execute(
        select(Contractor).where(Contractor.id == session.contractor_id)
    )
    contractor = contractor_result.scalar_one_or_none()
    if contractor is None:
        return "Session error: contractor not found."

    client_name = "Un cliente"
    if session.client_id is not None:
        client_result = await db.execute(
            select(Client).where(Client.id == session.client_id)
        )
        client = client_result.scalar_one_or_none()
        if client is not None:
            client_name = client.name

    await _send_to_contractor(
        contractor,
        f"{client_name} pregunta: \"{message}\"\nResponde aquí y se lo haré llegar.",
    )
    return "Mensaje enviado al profesional. Te responderá en breve."
