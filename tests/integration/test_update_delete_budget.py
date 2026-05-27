"""Integration tests for update_budget and delete_budget handlers."""
from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.handlers.budgets import handle_delete_budget, handle_update_budget
from app.models.budget import Budget, BudgetLine, BudgetStatus
from tests.integration.conftest import make_client, make_contractor, make_session

_FAKE_PDF_URL = "https://noa-dev.s3.fr-par.scw.cloud/fake/budgets/test.pdf"
_FAKE_PDF_URL_2 = "https://noa-dev.s3.fr-par.scw.cloud/fake/budgets/test2.pdf"


async def _make_budget(
    db: AsyncSession,
    contractor_id: uuid.UUID,
    client_id: uuid.UUID,
    *,
    status: BudgetStatus = BudgetStatus.draft,
    pdf_url: str | None = _FAKE_PDF_URL,
) -> Budget:
    from app.models.budget import BudgetLine

    budget = Budget(
        contractor_id=contractor_id,
        client_id=client_id,
        date=date(2025, 6, 1),
        status=status,
        total=423.50,
        pdf_url=pdf_url,
    )
    db.add(budget)
    await db.flush()

    line = BudgetLine(
        budget_id=budget.id,
        description="Instalación termo",
        quantity=1,
        unit_price=350.0,
        iva_rate=0.21,
        line_total=350.0,
    )
    db.add(line)
    await db.flush()
    return budget


class TestUpdateBudget:
    async def test_replaces_lines_and_recalculates_total(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, iva_rate=0.21)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        budget = await _make_budget(db, contractor.id, client.id)

        new_lines = [
            {"description": "Mano de obra", "quantity": 2, "unit_price": 100.0},
        ]

        with (
            patch("app.ai.handlers.budgets.upload_file", return_value=_FAKE_PDF_URL_2),
            patch("app.ai.handlers.budgets.delete_file"),
        ):
            result = await handle_update_budget(
                {"budget_id": str(budget.id), "lines": new_lines}, db, session
            )

        assert "actualizado" in result

        rows = await db.execute(select(Budget).where(Budget.id == budget.id))
        updated = rows.scalars().one()
        # subtotal=200, IVA=42, total=242
        assert float(updated.total) == 242.0

        line_rows = await db.execute(
            select(BudgetLine).where(BudgetLine.budget_id == budget.id)
        )
        db_lines = line_rows.scalars().all()
        assert len(db_lines) == 1
        assert db_lines[0].description == "Mano de obra"

    async def test_updates_valid_until_only(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        budget = await _make_budget(db, contractor.id, client.id)

        with patch("app.ai.handlers.budgets.upload_file", return_value=_FAKE_PDF_URL_2):
            result = await handle_update_budget(
                {"budget_id": str(budget.id), "valid_until": "2025-09-30"}, db, session
            )

        assert "actualizado" in result

        rows = await db.execute(select(Budget).where(Budget.id == budget.id))
        updated = rows.scalars().one()
        assert updated.valid_until == date(2025, 9, 30)

    async def test_blocked_when_status_sent(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        budget = await _make_budget(db, contractor.id, client.id, status=BudgetStatus.sent)

        line = {"description": "X", "quantity": 1, "unit_price": 10}
        result = await handle_update_budget(
            {"budget_id": str(budget.id), "lines": [line]},
            db,
            session,
        )

        assert "sent" in result or "cannot" in result.lower()

    async def test_blocked_when_status_accepted(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        budget = await _make_budget(db, contractor.id, client.id, status=BudgetStatus.accepted)

        result = await handle_update_budget(
            {"budget_id": str(budget.id), "valid_until": "2025-12-01"}, db, session
        )

        assert "accepted" in result or "cannot" in result.lower()

    async def test_data_isolation_rejects_other_contractor(self, db: AsyncSession) -> None:
        contractor_a = await make_contractor(db)
        contractor_b = await make_contractor(db)
        client_b = await make_client(db, contractor_b)
        session = await make_session(db, contractor_a)
        budget = await _make_budget(db, contractor_b.id, client_b.id)

        result = await handle_update_budget(
            {"budget_id": str(budget.id), "valid_until": "2025-12-01"}, db, session
        )

        assert "not found" in result.lower()

    async def test_no_fields_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        budget = await _make_budget(db, contractor.id, client.id)

        result = await handle_update_budget({"budget_id": str(budget.id)}, db, session)

        assert "lines" in result.lower() or "valid_until" in result.lower()

    async def test_old_pdf_deleted_on_line_update(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        budget = await _make_budget(db, contractor.id, client.id, pdf_url=_FAKE_PDF_URL)

        deleted: list[str] = []

        with (
            patch("app.ai.handlers.budgets.upload_file", return_value=_FAKE_PDF_URL_2),
            patch("app.ai.handlers.budgets.delete_file", side_effect=deleted.append),
        ):
            line = {"description": "X", "quantity": 1, "unit_price": 50}
            await handle_update_budget(
                {"budget_id": str(budget.id), "lines": [line]},
                db,
                session,
            )

        assert _FAKE_PDF_URL in deleted

    async def test_pdf_regenerated_with_new_url(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        budget = await _make_budget(db, contractor.id, client.id)

        line = {"description": "X", "quantity": 1, "unit_price": 50}
        with (
            patch("app.ai.handlers.budgets.upload_file", return_value=_FAKE_PDF_URL_2),
            patch("app.ai.handlers.budgets.delete_file"),
        ):
            await handle_update_budget(
                {"budget_id": str(budget.id), "lines": [line]},
                db,
                session,
            )

        rows = await db.execute(select(Budget).where(Budget.id == budget.id))
        assert rows.scalars().one().pdf_url == _FAKE_PDF_URL_2


class TestDeleteBudget:
    async def test_removes_budget_and_lines(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        budget = await _make_budget(db, contractor.id, client.id)
        budget_id = budget.id

        with patch("app.ai.handlers.budgets.delete_file"):
            result = await handle_delete_budget({"budget_id": str(budget_id)}, db, session)

        assert "eliminado" in result

        budget_rows = await db.execute(select(Budget).where(Budget.id == budget_id))
        assert budget_rows.scalars().first() is None

        line_rows = await db.execute(
            select(BudgetLine).where(BudgetLine.budget_id == budget_id)
        )
        assert line_rows.scalars().all() == []

    async def test_deletes_pdf_from_storage(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        budget = await _make_budget(db, contractor.id, client.id, pdf_url=_FAKE_PDF_URL)

        deleted: list[str] = []

        with patch("app.ai.handlers.budgets.delete_file", side_effect=deleted.append):
            await handle_delete_budget({"budget_id": str(budget.id)}, db, session)

        assert _FAKE_PDF_URL in deleted

    async def test_blocked_when_status_sent(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        budget = await _make_budget(db, contractor.id, client.id, status=BudgetStatus.sent)

        result = await handle_delete_budget({"budget_id": str(budget.id)}, db, session)

        assert "sent" in result or "cannot" in result.lower()

        rows = await db.execute(select(Budget).where(Budget.id == budget.id))
        assert rows.scalars().first() is not None

    async def test_blocked_when_status_invoiced(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        budget = await _make_budget(db, contractor.id, client.id, status=BudgetStatus.invoiced)

        result = await handle_delete_budget({"budget_id": str(budget.id)}, db, session)

        assert "invoiced" in result or "cannot" in result.lower()

    async def test_data_isolation_rejects_other_contractor(self, db: AsyncSession) -> None:
        contractor_a = await make_contractor(db)
        contractor_b = await make_contractor(db)
        client_b = await make_client(db, contractor_b)
        session = await make_session(db, contractor_a)
        budget = await _make_budget(db, contractor_b.id, client_b.id)

        result = await handle_delete_budget({"budget_id": str(budget.id)}, db, session)

        assert "not found" in result.lower()

        rows = await db.execute(select(Budget).where(Budget.id == budget.id))
        assert rows.scalars().first() is not None

    async def test_no_storage_call_when_no_pdf(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        budget = await _make_budget(db, contractor.id, client.id, pdf_url=None)

        deleted: list[str] = []

        with patch("app.ai.handlers.budgets.delete_file", side_effect=deleted.append):
            await handle_delete_budget({"budget_id": str(budget.id)}, db, session)

        assert deleted == []
