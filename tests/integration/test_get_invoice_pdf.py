"""Integration tests for get_invoice_pdf handler."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.handlers.invoices import handle_get_invoice_pdf
from tests.integration.conftest import make_client, make_contractor, make_invoice, make_session

_PDF_URL = "https://noa-dev.s3.fr-par.scw.cloud/abc/invoices/test.pdf"


class TestGetInvoicePdf:
    async def test_returns_pdf_url(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        await make_invoice(db, contractor, client, invoice_number="2025-001", pdf_url=_PDF_URL)

        result = await handle_get_invoice_pdf({"invoice_number": "2025-001"}, db, session)

        assert result == _PDF_URL

    async def test_invoice_not_found(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_get_invoice_pdf({"invoice_number": "2025-999"}, db, session)

        assert "not found" in result.lower()

    async def test_invoice_without_pdf(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        await make_invoice(db, contractor, client, invoice_number="2025-001")

        result = await handle_get_invoice_pdf({"invoice_number": "2025-001"}, db, session)

        assert "no pdf" in result.lower()

    async def test_data_isolation(self, db: AsyncSession) -> None:
        contractor_a = await make_contractor(db)
        contractor_b = await make_contractor(db)
        client_a = await make_client(db, contractor_a)
        session_b = await make_session(db, contractor_b)
        await make_invoice(db, contractor_a, client_a, invoice_number="2025-001", pdf_url=_PDF_URL)

        result = await handle_get_invoice_pdf({"invoice_number": "2025-001"}, db, session_b)

        assert "not found" in result.lower()
