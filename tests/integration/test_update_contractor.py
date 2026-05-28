"""Integration tests for the update_contractor tool handler."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import build_contractor_context
from app.ai.handlers.contractor import handle_update_contractor
from app.models.contractor import Contractor
from tests.integration.conftest import make_contractor, make_session


class TestUpdateContractorPersistence:
    async def test_changes_persist_to_db(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_update_contractor(
            {
                "business_name": "Pedro García SL",
                "iva_rate": 0.10,
            },
            db,
            session,
        )

        assert "actualizado" in result.lower()
        refreshed = await db.get(Contractor, contractor.id)
        assert refreshed is not None
        assert refreshed.business_name == "Pedro García SL"
        assert float(refreshed.iva_rate) == 0.10

    async def test_iban_normalised_in_db(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, iban=None)
        session = await make_session(db, contractor)

        await handle_update_contractor(
            {"iban": "es91 2100 0418 4502 0005 1332"}, db, session
        )

        refreshed = await db.get(Contractor, contractor.id)
        assert refreshed is not None
        assert refreshed.iban == "ES9121000418450200051332"

    async def test_address_persists(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        await handle_update_contractor(
            {"address": "Calle Mayor 1, 28013 Madrid"}, db, session
        )

        refreshed = await db.get(Contractor, contractor.id)
        assert refreshed is not None
        assert refreshed.address == "Calle Mayor 1, 28013 Madrid"

    async def test_address_can_be_cleared(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, address="Old address")
        session = await make_session(db, contractor)

        await handle_update_contractor({"address": ""}, db, session)

        refreshed = await db.get(Contractor, contractor.id)
        assert refreshed is not None
        assert refreshed.address is None


class TestUpdateContractorValidationDoesNotPersist:
    async def test_invalid_iban_leaves_db_unchanged(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, iban="ES9121000418450200051332")
        session = await make_session(db, contractor)

        result = await handle_update_contractor(
            {"iban": "garbage", "business_name": "Should Not Apply"}, db, session
        )

        assert "iban no válido" in result.lower()
        refreshed = await db.get(Contractor, contractor.id)
        assert refreshed is not None
        assert refreshed.iban == "ES9121000418450200051332"
        assert refreshed.business_name == "Fontanería García"

    async def test_invalid_nif_leaves_db_unchanged(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, nif="12345678A")
        session = await make_session(db, contractor)

        result = await handle_update_contractor({"nif": "bogus"}, db, session)

        assert "no válido" in result.lower()
        refreshed = await db.get(Contractor, contractor.id)
        assert refreshed is not None
        assert refreshed.nif == "12345678A"


class TestDataIsolation:
    async def test_update_only_touches_calling_contractor(
        self, db: AsyncSession
    ) -> None:
        """A second contractor's profile is untouched by the first's update."""
        contractor_a = await make_contractor(db, business_name="Original A")
        contractor_b = await make_contractor(db, business_name="Original B")
        session_a = await make_session(db, contractor_a)

        await handle_update_contractor(
            {"business_name": "Updated A"}, db, session_a
        )

        refreshed_a = await db.get(Contractor, contractor_a.id)
        refreshed_b = await db.get(Contractor, contractor_b.id)
        assert refreshed_a is not None and refreshed_b is not None
        assert refreshed_a.business_name == "Updated A"
        assert refreshed_b.business_name == "Original B"


class TestLayer3Reflection:
    async def test_updated_address_appears_in_next_layer_3(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        await handle_update_contractor(
            {"address": "Calle Nueva 5, Madrid"}, db, session
        )

        refreshed = await db.get(Contractor, contractor.id)
        assert refreshed is not None
        context = await build_contractor_context(db, refreshed)
        assert "Calle Nueva 5, Madrid" in context

    async def test_updated_iva_rate_appears_in_layer_3(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        await handle_update_contractor({"iva_rate": 10}, db, session)

        refreshed = await db.get(Contractor, contractor.id)
        assert refreshed is not None
        context = await build_contractor_context(db, refreshed)
        assert "IVA: 10%" in context
