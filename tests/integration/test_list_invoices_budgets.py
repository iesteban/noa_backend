"""Integration tests for list_invoices and list_budgets tool handlers."""
from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.handlers.budgets import handle_list_budgets
from app.ai.handlers.invoices import handle_list_invoices
from app.models.budget import BudgetStatus
from app.models.invoice import InvoiceStatus
from tests.integration.conftest import (
    make_budget,
    make_client,
    make_contractor,
    make_invoice,
    make_session,
)

# ---------------------------------------------------------------------------
# list_invoices
# ---------------------------------------------------------------------------

class TestListInvoices:
    async def test_returns_all_invoices_no_filter(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        await make_invoice(db, contractor, client, invoice_number="2025-001")
        await make_invoice(db, contractor, client, invoice_number="2025-002")

        result = await handle_list_invoices({}, db, session)

        assert "2025-001" in result
        assert "2025-002" in result

    async def test_includes_client_name_when_unfiltered(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor, name="Ana García")
        session = await make_session(db, contractor)
        await make_invoice(db, contractor, client, invoice_number="2025-001")

        result = await handle_list_invoices({}, db, session)

        assert "Ana García" in result

    async def test_filter_by_client_id(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client_a = await make_client(db, contractor, name="Ana García", phone_number="+34600000001")
        client_b = await make_client(db, contractor, name="Pedro Ruiz", phone_number="+34600000002")
        session = await make_session(db, contractor)
        await make_invoice(db, contractor, client_a, invoice_number="2025-001")
        await make_invoice(db, contractor, client_b, invoice_number="2025-002")

        result = await handle_list_invoices({"client_id": str(client_a.id)}, db, session)

        assert "2025-001" in result
        assert "2025-002" not in result

    async def test_header_shows_client_name_when_filtered(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor, name="Ana García")
        session = await make_session(db, contractor)
        await make_invoice(db, contractor, client)

        result = await handle_list_invoices({"client_id": str(client.id)}, db, session)

        assert "Ana García" in result.splitlines()[0]

    async def test_filter_by_status(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        await make_invoice(
            db, contractor, client, invoice_number="2025-001", status=InvoiceStatus.paid
        )
        await make_invoice(
            db, contractor, client, invoice_number="2025-002", status=InvoiceStatus.sent
        )

        result = await handle_list_invoices({"status": "paid"}, db, session)

        assert "2025-001" in result
        assert "2025-002" not in result

    async def test_filter_by_date_range(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        await make_invoice(
            db, contractor, client, invoice_number="2025-001",
            invoice_date=date(2025, 3, 1),
        )
        await make_invoice(
            db, contractor, client, invoice_number="2025-002",
            invoice_date=date(2025, 6, 1),
        )

        result = await handle_list_invoices(
            {"date_from": "2025-05-01", "date_to": "2025-12-31"}, db, session
        )

        assert "2025-002" in result
        assert "2025-001" not in result

    async def test_empty_result_returns_friendly_message(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_list_invoices({}, db, session)

        assert "No hay facturas" in result

    async def test_empty_with_client_filter_mentions_client(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor, name="Pedro Ruiz")
        session = await make_session(db, contractor)

        result = await handle_list_invoices({"client_id": str(client.id)}, db, session)

        assert "Pedro Ruiz" in result

    async def test_pagination_shows_ver_mas(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        for i in range(7):
            await make_invoice(db, contractor, client, invoice_number=f"2025-{i:03d}")

        result = await handle_list_invoices({"limit": 5, "offset": 0}, db, session)

        assert "Ver más" in result
        assert "7" in result

    async def test_pagination_next_page(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        for i in range(7):
            await make_invoice(
                db, contractor, client,
                invoice_number=f"2025-{i:03d}",
                invoice_date=date(2025, 1, i + 1),
            )

        result = await handle_list_invoices({"limit": 5, "offset": 5}, db, session)

        assert "No hay más facturas" not in result
        # Should return the remaining 2
        lines = [ln for ln in result.splitlines() if ln.startswith("·")]
        assert len(lines) == 2

    async def test_data_isolated_between_contractors(self, db: AsyncSession) -> None:
        contractor_a = await make_contractor(db, phone_number="+34600000010")
        contractor_b = await make_contractor(db, phone_number="+34600000011")
        client_a = await make_client(db, contractor_a)
        session_b = await make_session(db, contractor_b)
        await make_invoice(db, contractor_a, client_a, invoice_number="2025-999")

        result = await handle_list_invoices({}, db, session_b)

        assert "2025-999" not in result

    async def test_invalid_status_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_list_invoices({"status": "invalid"}, db, session)

        assert "Invalid status" in result

    async def test_invalid_date_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_list_invoices({"date_from": "not-a-date"}, db, session)

        assert "Invalid date_from" in result

    async def test_result_shows_status_in_spanish(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        await make_invoice(db, contractor, client, status=InvoiceStatus.paid)

        result = await handle_list_invoices({}, db, session)

        assert "Pagada" in result

    async def test_ordered_most_recent_first(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        await make_invoice(
            db, contractor, client,
            invoice_number="2025-001", invoice_date=date(2025, 1, 1),
        )
        await make_invoice(
            db, contractor, client,
            invoice_number="2025-012", invoice_date=date(2025, 12, 1),
        )

        result = await handle_list_invoices({}, db, session)
        lines = result.splitlines()
        idx_001 = next(i for i, ln in enumerate(lines) if "2025-001" in ln)
        idx_012 = next(i for i, ln in enumerate(lines) if "2025-012" in ln)
        assert idx_012 < idx_001  # newer first


# ---------------------------------------------------------------------------
# list_budgets
# ---------------------------------------------------------------------------

class TestListBudgets:
    async def test_returns_all_budgets_no_filter(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        await make_budget(db, contractor, client, total=300.0)
        await make_budget(db, contractor, client, total=150.0)

        result = await handle_list_budgets({}, db, session)

        assert "300€" in result or "300" in result
        assert "150€" in result or "150" in result

    async def test_filter_by_client_id(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client_a = await make_client(db, contractor, name="Ana García", phone_number="+34600000001")
        client_b = await make_client(db, contractor, name="Pedro Ruiz", phone_number="+34600000002")
        session = await make_session(db, contractor)
        await make_budget(db, contractor, client_a, total=100.0)
        await make_budget(db, contractor, client_b, total=200.0)

        result = await handle_list_budgets({"client_id": str(client_a.id)}, db, session)

        assert "Ana García" in result
        assert "Pedro Ruiz" not in result

    async def test_filter_by_status(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        await make_budget(db, contractor, client, total=100.0, status=BudgetStatus.accepted)
        await make_budget(db, contractor, client, total=200.0, status=BudgetStatus.draft)

        result = await handle_list_budgets({"status": "accepted"}, db, session)

        assert "100€" in result or "100" in result
        assert "200€" not in result and "200" not in result

    async def test_empty_result_returns_friendly_message(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_list_budgets({}, db, session)

        assert "No hay presupuestos" in result

    async def test_pagination_shows_ver_mas(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        for _ in range(7):
            await make_budget(db, contractor, client)

        result = await handle_list_budgets({"limit": 5, "offset": 0}, db, session)

        assert "Ver más" in result

    async def test_data_isolated_between_contractors(self, db: AsyncSession) -> None:
        contractor_a = await make_contractor(db, phone_number="+34600000020")
        contractor_b = await make_contractor(db, phone_number="+34600000021")
        client_a = await make_client(db, contractor_a)
        session_b = await make_session(db, contractor_b)
        await make_budget(db, contractor_a, client_a, total=999.0)

        result = await handle_list_budgets({}, db, session_b)

        assert "999" not in result

    async def test_status_shown_in_spanish(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        await make_budget(db, contractor, client, status=BudgetStatus.accepted)

        result = await handle_list_budgets({}, db, session)

        assert "Aceptado" in result
