from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.contractor import Contractor


async def build_contractor_context(db: AsyncSession, contractor: Contractor) -> str:
    """Build Layer 3 — contractor profile + client roster for the system prompt."""
    client_rows = await db.execute(
        select(Client)
        .where(Client.contractor_id == contractor.id)
        .order_by(Client.name)
    )
    clients = client_rows.scalars().all()

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
        f"## Clientes ({len(clients)})",
    ]
    for c in clients:
        lines.append(f"- {c.name}  id={c.id}  tel={c.phone_number}")
    if not clients:
        lines.append("(sin clientes aún)")

    return "\n".join(lines)
