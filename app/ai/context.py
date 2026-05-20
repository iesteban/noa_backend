from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date as SADate

from app.ai.handlers.working_hours import format_working_hours, load_working_hours
from app.config import settings
from app.models.client import Client
from app.models.contractor import Contractor
from app.models.instruction import ContractorInstruction
from app.models.job import Job

_SCOPE_LABELS: dict[str, str] = {
    "global": "global",
    "invoices": "facturas",
    "budgets": "presupuestos",
    "reminders": "recordatorios",
    "appointments": "citas",
}

_ROSTER_LIMIT = 10


async def get_recent_clients(
    db: AsyncSession,
    contractor_id: uuid.UUID,
    limit: int = _ROSTER_LIMIT,
) -> tuple[list[Client], int]:
    """Return (recent_clients, total_count).

    Ordering: COALESCE(last job date, client creation date) DESC — so a newly
    added client with no jobs ranks by today and stays in the roster.
    """
    total: int = (
        await db.scalar(
            select(func.count()).select_from(Client).where(Client.contractor_id == contractor_id)
        )
    ) or 0

    result = await db.execute(
        select(Client)
        .outerjoin(
            Job,
            (Job.client_id == Client.id) & (Job.contractor_id == contractor_id),
        )
        .where(Client.contractor_id == contractor_id)
        .group_by(Client.id)
        .order_by(
            func.coalesce(
                func.max(Job.date),
                cast(Client.created_at, SADate),
            ).desc()
        )
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def build_contractor_context(db: AsyncSession, contractor: Contractor) -> str:
    """Build Layer 3 — contractor profile + client roster for the system prompt."""
    today = datetime.now(UTC).date()
    lines: list[str] = [
        f"Hoy: {today.isoformat()}",
        "",
        "## Tu perfil",
        f"Nombre: {contractor.name}",
        f"Negocio: {contractor.business_name or contractor.name}",
    ]
    if contractor.nif:
        lines.append(f"NIF: {contractor.nif}")
    if contractor.iban:
        lines.append(f"IBAN: {contractor.iban}")
    lines += [
        f"IVA: {float(contractor.iva_rate) * 100:.0f}%",
        f"IRPF: {float(contractor.irpf_rate) * 100:.0f}%",
        "",
    ]

    if settings.feature_hybrid_client_roster:
        clients, total = await get_recent_clients(db, contractor.id)
        if total == 0:
            lines += ["## Clientes (0)", "(sin clientes aún)"]
        elif total <= _ROSTER_LIMIT:
            lines.append(f"## Clientes ({total})")
            for c in clients:
                lines.append(f"- {c.name}  id={c.id}  tel={c.phone_number}")
        else:
            lines.append(
                f"## Clientes recientes ({len(clients)} de {total}"
                f" — usa search_client para los demás)"
            )
            for c in clients:
                lines.append(f"- {c.name}  id={c.id}  tel={c.phone_number}")
    else:
        result = await db.execute(
            select(Client)
            .where(Client.contractor_id == contractor.id)
            .order_by(Client.name)
        )
        clients_all = list(result.scalars().all())
        lines.append(f"## Clientes ({len(clients_all)})")
        for c in clients_all:
            lines.append(f"- {c.name}  id={c.id}  tel={c.phone_number}")
        if not clients_all:
            lines.append("(sin clientes aún)")

    working_hours = await load_working_hours(db, contractor.id)
    lines += ["", "## Horario de trabajo"]
    lines.append(format_working_hours(working_hours))

    instr_result = await db.execute(
        select(ContractorInstruction)
        .where(
            ContractorInstruction.contractor_id == contractor.id,
            ContractorInstruction.active.is_(True),
        )
        .order_by(ContractorInstruction.created_at)
    )
    instructions = list(instr_result.scalars().all())
    if instructions:
        lines += ["", "## Instrucciones personales"]
        for instr in instructions:
            label = _SCOPE_LABELS.get(instr.scope, instr.scope)
            lines.append(f"- [{label}] {instr.instruction}  id={instr.id}")

    return "\n".join(lines)
