"""Integration tests for get_invoice_pdf handler."""
from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.handlers.invoices import handle_get_invoice_pdf
from tests.integration.conftest import make_client, make_contractor, make_invoice, make_session

_PDF_URL = "https://noa-dev.s3.fr-par.scw.cloud/abc/invoices/test.pdf"
# The bucket is private — the handler returns a pre-signed link, not the
# canonical storage URL. presign_url is stubbed to this deterministic value.
_SIGNED_URL = "https://noa-dev.s3.fr-par.scw.cloud/abc/invoices/test.pdf?X-Amz-Signature=test"


@pytest.fixture(autouse=True)
def _stub_presign() -> Iterator[None]:
    with patch("app.ai.handlers.invoices.presign_url", return_value=_SIGNED_URL):
        yield


class TestGetInvoicePdf:
    async def test_returns_presigned_url(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        await make_invoice(db, contractor, client, invoice_number="2025-001", pdf_url=_PDF_URL)

        result = await handle_get_invoice_pdf({"invoice_number": "2025-001"}, db, session)

        # The contractor gets a working pre-signed link, not the (inaccessible)
        # canonical storage URL.
        assert result == _SIGNED_URL

    async def test_presigns_stored_canonical_url(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        await make_invoice(db, contractor, client, invoice_number="2025-001", pdf_url=_PDF_URL)

        with patch(
            "app.ai.handlers.invoices.presign_url", return_value=_SIGNED_URL
        ) as mock_presign:
            await handle_get_invoice_pdf({"invoice_number": "2025-001"}, db, session)

        mock_presign.assert_called_once_with(_PDF_URL)

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
