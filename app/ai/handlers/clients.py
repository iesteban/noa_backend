from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dispatcher import register
from app.models.client import Client
from app.models.session import ConversationSession

logger = logging.getLogger(__name__)


@register("register_client")
async def handle_register_client(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    name = str(tool_input.get("name", "")).strip()
    if not name:
        return "name is required."

    phone_number = str(tool_input.get("phone_number", "")).strip()
    if not phone_number:
        return "phone_number is required."

    force = bool(tool_input.get("force", False))

    # Warn on duplicate name (unless contractor confirmed with force=true).
    if not force:
        existing_name = await db.execute(
            select(Client).where(
                Client.contractor_id == session.contractor_id,
                Client.name.ilike(name),
            )
        )
        if existing_name.scalar_one_or_none() is not None:
            return (
                f"Ya existe un cliente llamado '{name}'. "
                "¿Quieres añadirlo de todas formas? Si es así, llama de nuevo con force=true."
            )

    # Block on duplicate phone — unique constraint per contractor.
    existing_phone = await db.execute(
        select(Client).where(
            Client.contractor_id == session.contractor_id,
            Client.phone_number == phone_number,
        )
    )
    if existing_phone.scalar_one_or_none() is not None:
        return (
            f"Ya existe un cliente con el teléfono {phone_number}. "
            "Comprueba el número e inténtalo de nuevo."
        )

    nif = str(tool_input.get("nif", "")).strip() or None
    notes = str(tool_input.get("notes", "")).strip() or None

    client = Client(
        contractor_id=session.contractor_id,
        name=name,
        phone_number=phone_number,
        nif=nif,
        notes=notes,
    )
    db.add(client)
    await db.flush()

    return (
        f"Cliente guardado.\n"
        f"  Nombre: {client.name}\n"
        f"  Teléfono: {client.phone_number}"
        + (f"\n  NIF: {nif}" if nif else "")
        + f"\n  id={client.id}"
    )
