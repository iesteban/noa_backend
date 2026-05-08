"""Integration tests for build_contractor_context() — real PostgreSQL."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import build_contractor_context
from tests.integration.conftest import make_client, make_contractor, make_job


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

    async def test_multiple_clients_all_appear_when_under_limit(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        await make_client(db, contractor, name="Zoe Pérez")
        await make_client(db, contractor, name="Antonio Vega")
        result = await build_contractor_context(db, contractor)
        assert "Zoe Pérez" in result
        assert "Antonio Vega" in result

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

    # ------------------------------------------------------------------
    # Hybrid roster — ordering and limit
    # ------------------------------------------------------------------

    async def test_most_recent_client_appears_first(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        older = await make_client(db, contractor, name="Cliente Antiguo")
        newer = await make_client(db, contractor, name="Cliente Reciente")
        today = date.today()
        await make_job(db, contractor, older, job_date=today - timedelta(days=30))
        await make_job(db, contractor, newer, job_date=today)
        result = await build_contractor_context(db, contractor)
        assert result.index("Cliente Reciente") < result.index("Cliente Antiguo")

    async def test_only_10_clients_in_roster_when_over_limit(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        today = date.today()
        for i in range(11):
            c = await make_client(db, contractor, name=f"Cliente {i:02d}")
            await make_job(db, contractor, c, job_date=today - timedelta(days=i))
        result = await build_contractor_context(db, contractor)
        # "Cliente 10" is the oldest — should be excluded
        assert "Cliente 10" not in result
        assert "Cliente 00" in result

    async def test_header_shows_n_de_total_when_over_limit(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        today = date.today()
        for i in range(11):
            c = await make_client(db, contractor, name=f"X{i:02d}")
            await make_job(db, contractor, c, job_date=today - timedelta(days=i))
        result = await build_contractor_context(db, contractor)
        assert "10 de 11" in result

    async def test_search_client_hint_present_when_over_limit(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        for i in range(11):
            await make_client(db, contractor, name=f"Y{i:02d}")
        result = await build_contractor_context(db, contractor)
        assert "search_client" in result

    async def test_search_client_hint_absent_when_at_limit(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        for i in range(10):
            await make_client(db, contractor, name=f"Z{i:02d}")
        result = await build_contractor_context(db, contractor)
        assert "search_client" not in result

    async def test_new_client_without_jobs_appears_in_roster(
        self, db: AsyncSession
    ) -> None:
        """A newly added client (no jobs) must be in the top 10.

        COALESCE(last_job_date, created_at::date) ranks it by today, so it
        appears before clients whose last job was yesterday or older.
        """
        contractor = await make_contractor(db)
        yesterday = date.today() - timedelta(days=1)
        # Fill roster with 10 clients whose last job was yesterday
        for i in range(10):
            old = await make_client(db, contractor, name=f"Viejo {i:02d}")
            await make_job(db, contractor, old, job_date=yesterday)
        # Add an 11th client today with no jobs
        await make_client(db, contractor, name="Nuevo Sin Trabajo")
        result = await build_contractor_context(db, contractor)
        # The new client should displace the oldest slot and appear in the roster
        assert "Nuevo Sin Trabajo" in result
