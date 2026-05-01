from __future__ import annotations

import dataclasses
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.contractor import Contractor
from app.models.session import UserType


@dataclasses.dataclass(frozen=True)
class RoutingResult:
    user_type: UserType | None  # None = unknown or disambiguation needed
    contractor_id: uuid.UUID | None
    client_id: uuid.UUID | None
    # Populated when the same phone_number belongs to multiple contractors' clients
    candidates: list[tuple[uuid.UUID, str]]  # (contractor_id, display_name)


async def resolve_routing(
    db: AsyncSession,
    telegram_chat_id: int,
    phone_number: str | None = None,
) -> RoutingResult:
    """Determine who is sending this message and in which mode.

    Priority:
    1. telegram_chat_id matches a Contractor → contractor mode
    2. phone_number matches a Contractor directly → contractor mode
    3. phone_number matches exactly one Client → client mode
    4. phone_number matches N Clients → disambiguation needed
    5. No match → unknown user
    """
    row = await db.execute(
        select(Contractor).where(Contractor.telegram_chat_id == str(telegram_chat_id))
    )
    contractor = row.scalar_one_or_none()
    if contractor is not None:
        return RoutingResult(
            user_type=UserType.contractor,
            contractor_id=contractor.id,
            client_id=None,
            candidates=[],
        )

    if phone_number:
        row = await db.execute(
            select(Contractor).where(Contractor.phone_number == phone_number)
        )
        contractor = row.scalar_one_or_none()
        if contractor is not None:
            return RoutingResult(
                user_type=UserType.contractor,
                contractor_id=contractor.id,
                client_id=None,
                candidates=[],
            )

        rows = await db.execute(
            select(Client).where(Client.phone_number == phone_number)
        )
        clients = rows.scalars().all()
        if len(clients) == 1:
            return RoutingResult(
                user_type=UserType.client,
                contractor_id=clients[0].contractor_id,
                client_id=clients[0].id,
                candidates=[],
            )
        if len(clients) > 1:
            contractor_ids = [c.contractor_id for c in clients]
            rows = await db.execute(
                select(Contractor).where(Contractor.id.in_(contractor_ids))
            )
            contractor_map = {c.id: c for c in rows.scalars().all()}
            candidates = [
                (
                    c.contractor_id,
                    contractor_map[c.contractor_id].business_name
                    or contractor_map[c.contractor_id].name,
                )
                for c in clients
            ]
            return RoutingResult(
                user_type=None,
                contractor_id=None,
                client_id=None,
                candidates=candidates,
            )

    return RoutingResult(
        user_type=None,
        contractor_id=None,
        client_id=None,
        candidates=[],
    )
