from __future__ import annotations

import uuid

from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date as SADate

from app.models.client import Client
from app.models.contractor import Contractor
from app.models.job import Job

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
    """Build Layer 3 — contractor profile + hybrid client roster for the system prompt."""
    clients, total = await get_recent_clients(db, contractor.id)

    lines: list[str] = [
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

    return "\n".join(lines)
