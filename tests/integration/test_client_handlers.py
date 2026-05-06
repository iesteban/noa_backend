"""Integration tests for client tool handlers."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.handlers.clients import handle_register_client
from app.models.client import Client
from tests.integration.conftest import make_client, make_contractor, make_session


class TestRegisterClient:
    async def test_saves_new_client(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_register_client(
            {"name": "Ana García", "phone_number": "600123456"}, db, session
        )

        assert "Ana García" in result
        assert "600123456" in result
        row = await db.execute(
            select(Client).where(
                Client.contractor_id == contractor.id,
                Client.name == "Ana García",
            )
        )
        assert row.scalar_one_or_none() is not None

    async def test_saves_optional_fields(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        await handle_register_client(
            {
                "name": "Luis Martín",
                "phone_number": "611000001",
                "nif": "12345678Z",
                "notes": "Cliente preferente",
            },
            db,
            session,
        )

        row = await db.execute(
            select(Client).where(
                Client.contractor_id == contractor.id, Client.name == "Luis Martín"
            )
        )
        client = row.scalar_one()
        assert client.nif == "12345678Z"
        assert client.notes == "Cliente preferente"

    async def test_warns_on_duplicate_name(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await make_client(db, contractor, name="Ana García", phone_number="600000001")

        result = await handle_register_client(
            {"name": "Ana García", "phone_number": "600000002"}, db, session
        )

        assert "Ya existe" in result
        assert "force" in result
        # Should not have saved a second client.
        rows = await db.execute(
            select(Client).where(
                Client.contractor_id == contractor.id,
                Client.name.ilike("Ana García"),
            )
        )
        assert len(rows.scalars().all()) == 1

    async def test_force_saves_duplicate_name(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await make_client(db, contractor, name="Ana García", phone_number="600000001")

        result = await handle_register_client(
            {"name": "Ana García", "phone_number": "600000002", "force": True}, db, session
        )

        assert "guardado" in result.lower()
        rows = await db.execute(
            select(Client).where(
                Client.contractor_id == contractor.id,
                Client.name.ilike("Ana García"),
            )
        )
        assert len(rows.scalars().all()) == 2

    async def test_blocks_duplicate_phone(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await make_client(db, contractor, name="Ana García", phone_number="600123456")

        result = await handle_register_client(
            {"name": "Otra Persona", "phone_number": "600123456"}, db, session
        )

        assert "teléfono" in result.lower()
        rows = await db.execute(
            select(Client).where(Client.contractor_id == contractor.id)
        )
        assert len(rows.scalars().all()) == 1

    async def test_isolated_between_contractors(self, db: AsyncSession) -> None:
        contractor_a = await make_contractor(db, phone_number="+34600000001")
        contractor_b = await make_contractor(db, phone_number="+34600000002")
        session_b = await make_session(db, contractor_b)
        # Contractor A already has a client with this name.
        await make_client(db, contractor_a, name="Ana García", phone_number="600000099")

        # Contractor B adding same name should not trigger the duplicate warning.
        result = await handle_register_client(
            {"name": "Ana García", "phone_number": "600111111"}, db, session_b
        )

        assert "guardado" in result.lower()

    async def test_missing_name_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_register_client({"phone_number": "600000000"}, db, session)

        assert "name" in result.lower()

    async def test_missing_phone_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_register_client({"name": "Juan"}, db, session)

        assert "phone" in result.lower()
