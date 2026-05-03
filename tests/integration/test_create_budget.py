"""Integration tests for create_budget handler — real PostgreSQL, mocked S3."""
from __future__ import annotations

import uuid
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.handlers.budgets import handle_create_budget
from app.models.budget import Budget, BudgetLine
from tests.integration.conftest import make_client, make_contractor, make_session

_FAKE_PDF_URL = "https://noa-dev.s3.fr-par.scw.cloud/fake/budgets/test.pdf"


def _input(client_id: uuid.UUID, **overrides: object) -> dict:  # type: ignore[type-arg]
    base: dict[str, object] = {
        "client_id": str(client_id),
        "lines": [
            {"description": "Instalación termo 80L", "quantity": 1, "unit_price": 350.0},
        ],
    }
    base.update(overrides)
    return base


class TestCreateBudgetIntegration:
    async def test_budget_created_in_db(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)

        with patch("app.ai.handlers.budgets.upload_file", return_value=_FAKE_PDF_URL):
            result = await handle_create_budget(_input(client.id), db, session)

        assert "Presupuesto generado" in result
        rows = await db.execute(select(Budget).where(Budget.contractor_id == contractor.id))
        assert len(rows.scalars().all()) == 1

    async def test_total_is_subtotal_plus_iva_no_irpf(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, iva_rate=0.21, irpf_rate=0.15)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        lines = [{"description": "Trabajo", "quantity": 1, "unit_price": 1000.0}]

        with patch("app.ai.handlers.budgets.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_budget(_input(client.id, lines=lines), db, session)

        rows = await db.execute(select(Budget).where(Budget.contractor_id == contractor.id))
        budget = rows.scalars().one()
        assert float(budget.total) == 1210.0  # 1000 + 21% IVA, no IRPF deduction

    async def test_multiple_lines_summed(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, iva_rate=0.21)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        lines = [
            {"description": "Material", "quantity": 2, "unit_price": 100.0},
            {"description": "Mano de obra", "quantity": 3, "unit_price": 50.0},
        ]

        with patch("app.ai.handlers.budgets.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_budget(_input(client.id, lines=lines), db, session)

        rows = await db.execute(select(Budget).where(Budget.contractor_id == contractor.id))
        budget = rows.scalars().one()
        # subtotal = 200 + 150 = 350; IVA = 73.50; total = 423.50
        assert float(budget.total) == 423.50

    async def test_quantity_times_unit_price(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, iva_rate=0.21)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        lines = [{"description": "Horas", "quantity": 4, "unit_price": 25.0}]

        with patch("app.ai.handlers.budgets.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_budget(_input(client.id, lines=lines), db, session)

        line_rows = await db.execute(select(BudgetLine))
        line = line_rows.scalars().one()
        assert float(line.line_total) == 100.0  # 4 * 25

    async def test_budget_lines_created(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        lines = [
            {"description": "Partida A", "quantity": 1, "unit_price": 200.0},
            {"description": "Partida B", "quantity": 2, "unit_price": 75.0},
        ]

        with patch("app.ai.handlers.budgets.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_budget(_input(client.id, lines=lines), db, session)

        budget_rows = await db.execute(select(Budget).where(Budget.contractor_id == contractor.id))
        budget = budget_rows.scalars().one()
        line_rows = await db.execute(
            select(BudgetLine).where(BudgetLine.budget_id == budget.id)
        )
        db_lines = line_rows.scalars().all()
        assert len(db_lines) == 2
        descriptions = {ln.description for ln in db_lines}
        assert descriptions == {"Partida A", "Partida B"}

    async def test_pdf_url_stored(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)

        with patch("app.ai.handlers.budgets.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_budget(_input(client.id), db, session)

        rows = await db.execute(select(Budget).where(Budget.contractor_id == contractor.id))
        assert rows.scalars().one().pdf_url == _FAKE_PDF_URL

    async def test_optional_valid_until(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)

        with patch("app.ai.handlers.budgets.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_budget(
                _input(client.id, valid_until="2025-08-01"), db, session
            )

        from datetime import date
        rows = await db.execute(select(Budget).where(Budget.contractor_id == contractor.id))
        assert rows.scalars().one().valid_until == date(2025, 8, 1)

    async def test_no_valid_until(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)

        with patch("app.ai.handlers.budgets.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_budget(_input(client.id), db, session)

        rows = await db.execute(select(Budget).where(Budget.contractor_id == contractor.id))
        assert rows.scalars().one().valid_until is None

    async def test_result_contains_client_name_and_total(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, iva_rate=0.21)
        client = await make_client(db, contractor, name="María Fernández")
        session = await make_session(db, contractor)
        lines = [{"description": "Termo", "quantity": 1, "unit_price": 350.0}]

        with patch("app.ai.handlers.budgets.upload_file", return_value=_FAKE_PDF_URL):
            result = await handle_create_budget(_input(client.id, lines=lines), db, session)

        assert "María Fernández" in result
        assert "423.50" in result

    async def test_data_isolation_rejects_other_contractor_client(
        self, db: AsyncSession
    ) -> None:
        contractor_a = await make_contractor(db)
        contractor_b = await make_contractor(db)
        client_b = await make_client(db, contractor_b)
        session = await make_session(db, contractor_a)

        result = await handle_create_budget(_input(client_b.id), db, session)

        assert "not found" in result.lower()
        rows = await db.execute(select(Budget).where(Budget.contractor_id == contractor_a.id))
        assert rows.scalars().all() == []

    async def test_missing_lines_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)

        result = await handle_create_budget(
            {"client_id": str(client.id)}, db, session
        )

        assert "lines" in result.lower()

    async def test_line_missing_field_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        lines = [{"description": "Sin precio", "quantity": 1}]  # missing unit_price

        result = await handle_create_budget(_input(client.id, lines=lines), db, session)

        assert "unit_price" in result

    async def test_pdf_bytes_generated(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)

        captured: list[bytes] = []

        def fake_upload(
            contractor_id: object, entity_type: object, file_bytes: bytes, ext: object
        ) -> str:
            captured.append(file_bytes)
            return _FAKE_PDF_URL

        with patch("app.ai.handlers.budgets.upload_file", side_effect=fake_upload):
            await handle_create_budget(_input(client.id), db, session)

        assert len(captured) == 1
        assert captured[0].startswith(b"%PDF")
        assert len(captured[0]) > 1000
