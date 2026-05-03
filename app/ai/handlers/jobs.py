from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dispatcher import register
from app.models.client import Client
from app.models.job import Job, JobStatus
from app.models.session import ConversationSession

logger = logging.getLogger(__name__)


@register("search_client")
async def handle_search_client(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    """Search contractor's clients by name (case-insensitive substring match)."""
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    query = str(tool_input.get("query", "")).strip()
    if not query:
        return "query is required."

    rows = await db.execute(
        select(Client)
        .where(
            Client.contractor_id == session.contractor_id,
            Client.name.ilike(f"%{query}%"),
        )
        .order_by(Client.name)
        .limit(10)
    )
    clients = rows.scalars().all()

    if not clients:
        return f'No clients found matching "{query}".'

    lines = [f'Found {len(clients)} client(s) matching "{query}":']
    for c in clients:
        lines.append(f"- {c.name}  id={c.id}  tel={c.phone_number}")
    return "\n".join(lines)


@register("log_job")
async def handle_log_job(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    """Create a Job record for the contractor. Flushes but does not commit."""
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    # --- validate client_id ---
    try:
        client_id = uuid.UUID(str(tool_input["client_id"]))
    except (KeyError, ValueError):
        return "Invalid client_id — must be a UUID returned by search_client."

    # --- validate description ---
    description = str(tool_input.get("description", "")).strip()
    if not description:
        return "description is required."

    # --- validate date ---
    try:
        job_date = date.fromisoformat(str(tool_input["date"]))
    except (KeyError, ValueError):
        return "Invalid date — use YYYY-MM-DD format."

    # --- validate amount ---
    try:
        amount = float(tool_input["amount"])
    except (KeyError, TypeError, ValueError):
        return "Invalid amount — must be a number."

    # --- optional duration ---
    duration_hours: float | None = None
    raw_duration = tool_input.get("duration_hours")
    if raw_duration is not None:
        try:
            duration_hours = float(raw_duration)
        except (TypeError, ValueError):
            return "Invalid duration_hours — must be a number."

    # --- data isolation: client must belong to this contractor ---
    client = await db.get(Client, client_id)
    if client is None or client.contractor_id != session.contractor_id:
        return f"Client {client_id} not found."

    job = Job(
        contractor_id=session.contractor_id,
        client_id=client_id,
        description=description,
        date=job_date,
        duration_hours=duration_hours,
        amount=amount,
        status=JobStatus.draft,
    )
    db.add(job)
    await db.flush()

    duration_str = f" | Duración: {duration_hours}h" if duration_hours is not None else ""
    return (
        f"Trabajo guardado."
        f" id={job.id}"
        f" | Cliente: {client.name}"
        f" | Fecha: {job_date}"
        f" | {description}"
        f"{duration_str}"
        f" | Importe: {amount:.2f}€"
    )
