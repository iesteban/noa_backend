"""Client-mode tool handlers: get_contractor_availability, book_appointment, notify_contractor."""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dispatcher import register
from app.ai.handlers.calendar import (
    _WORK_END,
    _WORK_START,
    _compute_free_slots,
    _format_slots,
    _get_token,
)
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
from app.models.session import ConversationSession

logger = logging.getLogger(__name__)

_DEFAULT_DURATION_MINUTES = 60


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

    token = await _get_token(db, session.contractor_id)
    if token is None:
        return "No hay información de disponibilidad online para esas fechas."

    provider = _provider or GoogleCalendarProvider(token, db)
    start_dt = datetime.combine(date_from, _WORK_START, tzinfo=UTC)
    end_dt = datetime.combine(date_to, _WORK_END, tzinfo=UTC)

    try:
        busy = await provider.list_events(session.contractor_id, start_dt, end_dt)
    except Exception:
        logger.exception(
            "Google Calendar list_events failed for contractor %s", session.contractor_id
        )
        return "No se pudo consultar la disponibilidad. Inténtalo de nuevo."

    slots = _compute_free_slots(date_from, date_to, busy)
    return _format_slots(slots)


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

    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)

    appointment = Appointment(
        contractor_id=session.contractor_id,
        client_id=session.client_id,
        starts_at=starts_at,
        duration_minutes=_DEFAULT_DURATION_MINUTES,
        description=description,
        status=AppointmentStatus.scheduled,
        booked_by=BookedBy.client,
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
                "Google Calendar create_event failed for contractor %s",
                session.contractor_id,
            )
            calendar_note = " | (No se pudo sincronizar con Google Calendar)"

    starts_str = starts_at.strftime("%-d %b %Y a las %H:%M")

    contractor_result = await db.execute(
        select(Contractor).where(Contractor.id == session.contractor_id)
    )
    contractor = contractor_result.scalar_one_or_none()
    if contractor is not None:
        client_result = await db.execute(
            select(Client).where(Client.id == session.client_id)
        )
        client = client_result.scalar_one_or_none()
        client_name = client.name if client is not None else "Un cliente"
        await _send_to_contractor(
            contractor,
            f"Nueva cita: {client_name} — {description} — {starts_str}"
            f" [id={appointment.id}]\nResponde \"No\" para rechazarla.",
        )

    return (
        f"Cita reservada. {description} | {starts_str}{calendar_note}. "
        "El profesional ha sido notificado."
    )


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
        return "Error: contractor not found."

    client_name = "Un cliente"
    if session.client_id is not None:
        client_result = await db.execute(
            select(Client).where(Client.id == session.client_id)
        )
        client = client_result.scalar_one_or_none()
        if client is not None:
            client_name = client.name

    notification = (
        f"{client_name} pregunta: \"{message}\"\n"
        "Responde aquí y se lo haré llegar."
    )
    await _send_to_contractor(contractor, notification)
    return "Mensaje enviado al profesional. Te responderá en breve."
