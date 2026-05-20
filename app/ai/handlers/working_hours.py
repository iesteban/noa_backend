from __future__ import annotations

import uuid
from datetime import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dispatcher import register
from app.models.session import ConversationSession
from app.models.working_hours import WorkingHours

_DAY_NAMES_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


async def load_working_hours(
    db: AsyncSession, contractor_id: uuid.UUID
) -> dict[int, WorkingHours]:
    """Return a map of day_of_week → WorkingHours for the contractor."""
    result = await db.execute(
        select(WorkingHours).where(WorkingHours.contractor_id == contractor_id)
    )
    return {wh.day_of_week: wh for wh in result.scalars().all()}


def format_working_hours(schedule: dict[int, WorkingHours]) -> str:
    """Return a human-readable schedule string for Layer 3 context."""
    if not schedule:
        return "No configurado"
    lines: list[str] = []
    for dow in range(7):
        name = _DAY_NAMES_ES[dow]
        wh = schedule.get(dow)
        if wh is None:
            continue
        if not wh.is_working_day:
            lines.append(f"- {name}: No disponible")
        elif wh.start_time and wh.end_time:
            lines.append(
                f"- {name}: {wh.start_time.strftime('%H:%M')}–{wh.end_time.strftime('%H:%M')}"
            )
    return "\n".join(lines) if lines else "No configurado"


def _parse_time(raw: str) -> time | None:
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            from datetime import datetime
            return datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    return None


@register("set_working_hours")
async def handle_set_working_hours(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    schedule = tool_input.get("schedule")
    if not isinstance(schedule, list) or not schedule:
        return "schedule debe ser una lista con al menos un día."

    updated: list[str] = []
    errors: list[str] = []

    for item in schedule:
        try:
            dow = int(item["day_of_week"])
        except (KeyError, TypeError, ValueError):
            errors.append("day_of_week inválido en un item.")
            continue
        if dow < 0 or dow > 6:
            errors.append(f"day_of_week {dow} fuera de rango (0–6).")
            continue

        is_working = bool(item.get("is_working_day", True))

        start_time: time | None = None
        end_time: time | None = None
        if is_working:
            raw_start = item.get("start_time")
            raw_end = item.get("end_time")
            if not raw_start or not raw_end:
                errors.append(
                    f"{_DAY_NAMES_ES[dow]}: start_time y end_time son obligatorios"
                    " cuando is_working_day=true."
                )
                continue
            start_time = _parse_time(str(raw_start))
            end_time = _parse_time(str(raw_end))
            if start_time is None:
                errors.append(f"{_DAY_NAMES_ES[dow]}: start_time inválido — usa HH:MM.")
                continue
            if end_time is None:
                errors.append(f"{_DAY_NAMES_ES[dow]}: end_time inválido — usa HH:MM.")
                continue
            if end_time <= start_time:
                errors.append(f"{_DAY_NAMES_ES[dow]}: end_time debe ser posterior a start_time.")
                continue

        # Upsert: fetch existing row or create new one.
        result = await db.execute(
            select(WorkingHours).where(
                WorkingHours.contractor_id == session.contractor_id,
                WorkingHours.day_of_week == dow,
            )
        )
        wh = result.scalar_one_or_none()
        if wh is None:
            wh = WorkingHours(
                contractor_id=session.contractor_id,
                day_of_week=dow,
            )
            db.add(wh)
        wh.is_working_day = is_working
        wh.start_time = start_time
        wh.end_time = end_time
        await db.flush()
        updated.append(_DAY_NAMES_ES[dow])

    parts: list[str] = []
    if updated:
        parts.append(f"Horario actualizado: {', '.join(updated)}.")
    if errors:
        parts.append("Errores: " + " | ".join(errors))
    return " ".join(parts) if parts else "Sin cambios."


@register("get_working_hours")
async def handle_get_working_hours(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    schedule = await load_working_hours(db, session.contractor_id)
    if not schedule:
        return (
            "No tienes horario configurado. "
            "Actualmente se usan los valores por defecto (lunes a viernes, 9h–18h)."
        )

    lines = ["Tu horario de trabajo:"]
    for dow in range(7):
        wh = schedule.get(dow)
        if wh is None:
            continue
        name = _DAY_NAMES_ES[dow]
        if not wh.is_working_day:
            lines.append(f"  {name}: No disponible")
        elif wh.start_time and wh.end_time:
            lines.append(
                f"  {name}: {wh.start_time.strftime('%H:%M')}–{wh.end_time.strftime('%H:%M')}"
            )
    return "\n".join(lines)
