"""Integration tests for build_contractor_context() — real PostgreSQL."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import build_contractor_context
from tests.integration.conftest import make_client, make_contractor


class TestContractorProfile:
    async def test_name_in_output(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, name="María Sánchez")
        result = await build_contractor_context(db, contractor)
        assert "María Sánchez" in result

    async def test_business_name_in_output(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, business_name="Electricidad Sánchez")
        result = await build_contractor_context(db, contractor)
        assert "Electricidad Sánchez" in result

    async def test_business_name_falls_back_to_name(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, name="Raúl Torres", business_name=None)
        result = await build_contractor_context(db, contractor)
        assert "Raúl Torres" in result

    async def test_nif_in_output_when_present(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, nif="87654321B")
        result = await build_contractor_context(db, contractor)
        assert "87654321B" in result

    async def test_nif_absent_when_none(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, nif=None)
        result = await build_contractor_context(db, contractor)
        assert "NIF" not in result

    async def test_iban_in_output_when_present(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, iban="ES12 3456 7890 1234 5678 9012")
        result = await build_contractor_context(db, contractor)
        assert "ES12" in result

    async def test_iban_absent_when_none(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, iban=None)
        result = await build_contractor_context(db, contractor)
        assert "IBAN" not in result

    async def test_iva_formatted_as_percentage(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, iva_rate=0.10)
        result = await build_contractor_context(db, contractor)
        assert "10%" in result

    async def test_irpf_formatted_as_percentage(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, irpf_rate=0.07)
        result = await build_contractor_context(db, contractor)
        assert "7%" in result


class TestClientRoster:
    async def test_empty_roster_placeholder(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        result = await build_contractor_context(db, contractor)
        assert "sin clientes" in result

    async def test_client_name_appears(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        await make_client(db, contractor, name="Beatriz Ramos")
        result = await build_contractor_context(db, contractor)
        assert "Beatriz Ramos" in result

    async def test_client_phone_appears(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        await make_client(db, contractor, phone_number="+34699000111")
        result = await build_contractor_context(db, contractor)
        assert "+34699000111" in result

    async def test_client_id_appears(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        result = await build_contractor_context(db, contractor)
        assert str(client.id) in result

    async def test_multiple_clients_all_appear(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        await make_client(db, contractor, name="Zoe Pérez")
        await make_client(db, contractor, name="Antonio Vega")
        result = await build_contractor_context(db, contractor)
        assert "Zoe Pérez" in result
        assert "Antonio Vega" in result

    async def test_clients_sorted_alphabetically(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        await make_client(db, contractor, name="Zoe Pérez")
        await make_client(db, contractor, name="Antonio Vega")
        result = await build_contractor_context(db, contractor)
        assert result.index("Antonio Vega") < result.index("Zoe Pérez")

    async def test_data_isolation_excludes_other_contractor_clients(
        self, db: AsyncSession
    ) -> None:
        contractor_a = await make_contractor(db)
        contractor_b = await make_contractor(db)
        await make_client(db, contractor_b, name="Cliente Secreto")

        result = await build_contractor_context(db, contractor_a)

        assert "Cliente Secreto" not in result

    async def test_own_clients_not_affected_by_other_contractor(
        self, db: AsyncSession
    ) -> None:
        """Contractor A's clients still appear even when contractor B also has clients."""
        contractor_a = await make_contractor(db)
        contractor_b = await make_contractor(db)
        await make_client(db, contractor_a, name="Cliente Propio")
        await make_client(db, contractor_b, name="Ajeno")

        result = await build_contractor_context(db, contractor_a)

        assert "Cliente Propio" in result
        assert "Ajeno" not in result

    async def test_client_count_in_header(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        await make_client(db, contractor, name="Alpha")
        await make_client(db, contractor, name="Beta")
        await make_client(db, contractor, name="Gamma")
        result = await build_contractor_context(db, contractor)
        assert "3" in result

    async def test_single_client_count(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        await make_client(db, contractor, name="Solo")
        result = await build_contractor_context(db, contractor)
        assert "1" in result
        assert "Solo" in result
