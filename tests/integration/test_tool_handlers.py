"""Integration tests for search_client and log_job handlers — real PostgreSQL."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.handlers.jobs import handle_log_job, handle_search_client
from app.models.job import Job, JobStatus
from app.models.session import UserType
from tests.integration.conftest import make_client, make_contractor, make_session

# ---------------------------------------------------------------------------
# search_client
# ---------------------------------------------------------------------------

class TestSearchClientIntegration:
    async def test_finds_client_by_exact_name(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        await make_client(db, contractor, name="Pedro Mejuto")
        session = await make_session(db, contractor)

        result = await handle_search_client({"query": "Pedro Mejuto"}, db, session)

        assert "Pedro Mejuto" in result

    async def test_finds_client_by_partial_name(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        await make_client(db, contractor, name="Pedro Mejuto")
        session = await make_session(db, contractor)

        result = await handle_search_client({"query": "Mej"}, db, session)

        assert "Pedro Mejuto" in result

    async def test_case_insensitive_match(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        await make_client(db, contractor, name="Ana López")
        session = await make_session(db, contractor)

        result = await handle_search_client({"query": "ana"}, db, session)

        assert "Ana López" in result

    async def test_returns_client_id_and_phone(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(
            db, contractor, name="Beatriz Ramos", phone_number="+34699111222"
        )
        session = await make_session(db, contractor)

        result = await handle_search_client({"query": "Beatriz"}, db, session)

        assert str(client.id) in result
        assert "+34699111222" in result

    async def test_no_match_returns_not_found(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_search_client({"query": "Nadie"}, db, session)

        assert "No clients found" in result

    async def test_multiple_matches_all_returned(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        await make_client(db, contractor, name="Pedro Alonso")
        await make_client(db, contractor, name="Pedro Ruiz")
        session = await make_session(db, contractor)

        result = await handle_search_client({"query": "Pedro"}, db, session)

        assert "Pedro Alonso" in result
        assert "Pedro Ruiz" in result

    async def test_data_isolation_excludes_other_contractor_clients(
        self, db: AsyncSession
    ) -> None:
        contractor_a = await make_contractor(db)
        contractor_b = await make_contractor(db)
        await make_client(db, contractor_b, name="Cliente Secreto")
        session = await make_session(db, contractor_a)

        result = await handle_search_client({"query": "Cliente"}, db, session)

        assert "Cliente Secreto" not in result
        assert "No clients found" in result

    async def test_results_ordered_alphabetically(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        await make_client(db, contractor, name="Zoe Vidal")
        await make_client(db, contractor, name="Alfonso Roca")
        session = await make_session(db, contractor)

        result = await handle_search_client({"query": "o"}, db, session)

        assert result.index("Alfonso") < result.index("Zoe")


# ---------------------------------------------------------------------------
# log_job
# ---------------------------------------------------------------------------

class TestLogJobIntegration:
    def _input(self, client_id: uuid.UUID, **overrides: object) -> dict:  # type: ignore[type-arg]
        base = {
            "client_id": str(client_id),
            "description": "Cambio de grifo",
            "date": "2025-06-15",
            "amount": 80.0,
        }
        base.update(overrides)
        return base

    async def test_job_persisted_in_db(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)

        await handle_log_job(self._input(client.id), db, session)

        rows = await db.execute(select(Job).where(Job.contractor_id == contractor.id))
        jobs = rows.scalars().all()
        assert len(jobs) == 1
        assert jobs[0].description == "Cambio de grifo"

    async def test_job_has_correct_fields(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor, name="María Fernández")
        session = await make_session(db, contractor)

        await handle_log_job(
            self._input(client.id, duration_hours=2.5, amount=120.0),
            db,
            session,
        )

        rows = await db.execute(select(Job).where(Job.contractor_id == contractor.id))
        job = rows.scalars().one()
        assert job.client_id == client.id
        assert job.contractor_id == contractor.id
        assert job.date == date(2025, 6, 15)
        assert float(job.amount) == 120.0
        assert float(job.duration_hours) == 2.5
        assert job.status == JobStatus.draft

    async def test_job_without_duration(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)

        await handle_log_job(self._input(client.id), db, session)

        rows = await db.execute(select(Job).where(Job.contractor_id == contractor.id))
        job = rows.scalars().one()
        assert job.duration_hours is None

    async def test_confirmation_string_contains_details(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor, name="Fermín Castillo")
        session = await make_session(db, contractor)

        result = await handle_log_job(
            self._input(client.id, amount=95.5, duration_hours=3.0),
            db,
            session,
        )

        assert "Trabajo guardado" in result
        assert "Fermín Castillo" in result
        assert "95.50€" in result
        assert "3.0h" in result
        assert "2025-06-15" in result

    async def test_data_isolation_rejects_other_contractor_client(
        self, db: AsyncSession
    ) -> None:
        contractor_a = await make_contractor(db)
        contractor_b = await make_contractor(db)
        client_b = await make_client(db, contractor_b)
        session = await make_session(db, contractor_a)

        result = await handle_log_job(self._input(client_b.id), db, session)

        assert "not found" in result.lower()
        rows = await db.execute(select(Job).where(Job.contractor_id == contractor_a.id))
        assert rows.scalars().all() == []

    async def test_nonexistent_client_id_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_log_job(self._input(uuid.uuid4()), db, session)

        assert "not found" in result.lower()

    async def test_invalid_uuid_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        inp = {**self._input(uuid.uuid4()), "client_id": "garbage"}

        result = await handle_log_job(inp, db, session)

        assert "Invalid client_id" in result

    async def test_result_contains_job_id(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)

        result = await handle_log_job(self._input(client.id), db, session)

        rows = await db.execute(select(Job).where(Job.contractor_id == contractor.id))
        job = rows.scalars().one()
        assert str(job.id) in result

    async def test_client_mode_session_uses_contractor_id(
        self, db: AsyncSession
    ) -> None:
        """Even if session is client-mode, contractor_id is used for scoping."""
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        # client-mode session still has contractor_id set
        session = await make_session(db, contractor, user_type=UserType.client)

        result = await handle_log_job(self._input(client.id), db, session)

        # log_job is only in CONTRACTOR_TOOLS so Claude won't call it for clients,
        # but the handler itself is agnostic — data isolation still works
        assert "Trabajo guardado" in result
