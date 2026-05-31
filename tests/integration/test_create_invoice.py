"""Integration tests for create_invoice handler — real PostgreSQL, mocked S3."""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.handlers.invoices import handle_create_invoice
from app.models.invoice import Invoice, InvoiceLine
from app.models.job import Job, JobStatus
from tests.integration.conftest import make_client as _make_client
from tests.integration.conftest import make_contractor, make_session

_CLIENT_LEGAL = {"nif": "12345678Z", "address": "Calle Mayor 1, 28001 Madrid"}


async def make_client(db: AsyncSession, contractor, **overrides: object):  # type: ignore[no-untyped-def]
    """Wrapper that injects legal NIF/address so the invoice gate is always bypassed."""
    return await _make_client(db, contractor, **{**_CLIENT_LEGAL, **overrides})

_FAKE_PDF_URL = "https://noa-dev.s3.fr-par.scw.cloud/fake/invoices/test.pdf"
# The bucket is private, so the handler hands back a pre-signed link, not the
# canonical storage URL. presign_url is stubbed to this deterministic value.
_SIGNED_PDF_URL = "https://noa-dev.s3.fr-par.scw.cloud/fake/invoices/test.pdf?X-Amz-Signature=test"


@pytest.fixture(autouse=True)
def _stub_presign(request: pytest.FixtureRequest) -> Iterator[None]:
    # Tests that exercise the real presign wiring opt out via no_presign_stub.
    if "no_presign_stub" in request.fixturenames:
        yield
        return
    with patch("app.ai.handlers.invoices.presign_url", return_value=_SIGNED_PDF_URL):
        yield


@pytest.fixture
def no_presign_stub() -> None:
    """Marker fixture: opt out of the presign_url stub for end-to-end link checks."""
    return None


def _fake_s3() -> MagicMock:
    """A boto3 stand-in whose presigner returns a signature-bearing URL."""
    s3 = MagicMock()
    s3.generate_presigned_url.return_value = "https://signed.example/test.pdf?sig=abc"
    return s3


def _make_job_input(client_id: uuid.UUID, job_ids: list[uuid.UUID], **overrides: object) -> dict:  # type: ignore[type-arg]
    base: dict[str, object] = {
        "client_id": str(client_id),
        "job_ids": [str(j) for j in job_ids],
        "date": "2025-06-30",
    }
    base.update(overrides)
    return base


async def _insert_job(
    db: AsyncSession,
    contractor_id: uuid.UUID,
    client_id: uuid.UUID,
    *,
    description: str = "Cambio de grifo",
    amount: float = 100.0,
) -> Job:
    job = Job(
        contractor_id=contractor_id,
        client_id=client_id,
        description=description,
        date=date(2025, 6, 15),
        amount=amount,
        status=JobStatus.draft,
    )
    db.add(job)
    await db.flush()
    return job


class TestCreateInvoiceIntegration:
    async def test_invoice_created_in_db(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        job = await _insert_job(db, contractor.id, client.id)

        with patch("app.ai.handlers.invoices.upload_file", return_value=_FAKE_PDF_URL):
            result = await handle_create_invoice(
                _make_job_input(client.id, [job.id]), db, session
            )

        assert "Factura generada" in result
        rows = await db.execute(select(Invoice).where(Invoice.contractor_id == contractor.id))
        invoices = rows.scalars().all()
        assert len(invoices) == 1

    async def test_invoice_number_format(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, invoice_counter=41)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        job = await _insert_job(db, contractor.id, client.id)

        with patch("app.ai.handlers.invoices.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_invoice(
                _make_job_input(client.id, [job.id], date="2025-09-10"), db, session
            )

        rows = await db.execute(select(Invoice).where(Invoice.contractor_id == contractor.id))
        invoice = rows.scalars().one()
        assert invoice.invoice_number == "2025-042"

    async def test_counter_increments_atomically(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        job1 = await _insert_job(db, contractor.id, client.id, description="Trabajo A")
        job2 = await _insert_job(db, contractor.id, client.id, description="Trabajo B")

        with patch("app.ai.handlers.invoices.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_invoice(
                _make_job_input(client.id, [job1.id]), db, session
            )
            await handle_create_invoice(
                _make_job_input(client.id, [job2.id]), db, session
            )

        rows = await db.execute(
            select(Invoice)
            .where(Invoice.contractor_id == contractor.id)
            .order_by(Invoice.created_at)
        )
        invoices = rows.scalars().all()
        assert invoices[0].invoice_number.endswith("-001")
        assert invoices[1].invoice_number.endswith("-002")

    async def test_iva_and_irpf_calculated_correctly(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, iva_rate=0.21, irpf_rate=0.15)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        job = await _insert_job(db, contractor.id, client.id, amount=1000.0)

        with patch("app.ai.handlers.invoices.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_invoice(_make_job_input(client.id, [job.id]), db, session)

        rows = await db.execute(select(Invoice).where(Invoice.contractor_id == contractor.id))
        inv = rows.scalars().one()
        assert float(inv.subtotal) == 1000.0
        assert float(inv.iva_amount) == 210.0
        assert float(inv.irpf_amount) == 150.0
        assert float(inv.total) == 1060.0  # 1000 + 210 - 150

    async def test_multiple_jobs_summed(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, iva_rate=0.21, irpf_rate=0.15)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        job1 = await _insert_job(db, contractor.id, client.id, amount=200.0, description="A")
        job2 = await _insert_job(db, contractor.id, client.id, amount=300.0, description="B")

        with patch("app.ai.handlers.invoices.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_invoice(
                _make_job_input(client.id, [job1.id, job2.id]), db, session
            )

        rows = await db.execute(select(Invoice).where(Invoice.contractor_id == contractor.id))
        inv = rows.scalars().one()
        assert float(inv.subtotal) == 500.0
        assert float(inv.iva_amount) == 105.0
        assert float(inv.irpf_amount) == 75.0

    async def test_invoice_lines_created(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        job1 = await _insert_job(db, contractor.id, client.id, description="Trabajo A", amount=80.0)
        job2 = await _insert_job(db, contractor.id, client.id, description="Trabajo B", amount=60.0)

        with patch("app.ai.handlers.invoices.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_invoice(
                _make_job_input(client.id, [job1.id, job2.id]), db, session
            )

        inv_rows = await db.execute(select(Invoice).where(Invoice.contractor_id == contractor.id))
        inv = inv_rows.scalars().one()
        line_rows = await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id))
        lines = line_rows.scalars().all()
        assert len(lines) == 2
        descriptions = {ln.description for ln in lines}
        assert descriptions == {"Trabajo A", "Trabajo B"}

    async def test_jobs_marked_invoiced(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        job = await _insert_job(db, contractor.id, client.id)

        with patch("app.ai.handlers.invoices.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_invoice(_make_job_input(client.id, [job.id]), db, session)

        await db.refresh(job)
        assert job.status == JobStatus.invoiced

    async def test_pdf_url_stored_on_invoice(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        job = await _insert_job(db, contractor.id, client.id)

        with patch("app.ai.handlers.invoices.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_invoice(_make_job_input(client.id, [job.id]), db, session)

        rows = await db.execute(select(Invoice).where(Invoice.contractor_id == contractor.id))
        inv = rows.scalars().one()
        # The persisted reference stays the canonical storage URL.
        assert inv.pdf_url == _FAKE_PDF_URL

    async def test_result_contains_invoice_number_and_total(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor, name="Ana López")
        session = await make_session(db, contractor)
        job = await _insert_job(db, contractor.id, client.id, amount=500.0)

        with patch("app.ai.handlers.invoices.upload_file", return_value=_FAKE_PDF_URL):
            result = await handle_create_invoice(
                _make_job_input(client.id, [job.id]), db, session
            )

        assert "Ana López" in result
        assert "2025-001" in result

    async def test_result_contains_presigned_pdf_link(self, db: AsyncSession) -> None:
        """Regression: the contractor must get a working (pre-signed) PDF link."""
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        job = await _insert_job(db, contractor.id, client.id)

        with patch("app.ai.handlers.invoices.upload_file", return_value=_FAKE_PDF_URL):
            result = await handle_create_invoice(
                _make_job_input(client.id, [job.id]), db, session
            )

        assert _SIGNED_PDF_URL in result

    async def test_link_is_signed_not_canonical(
        self, db: AsyncSession, no_presign_stub: None
    ) -> None:
        """End-to-end guard: the link handed to the contractor must be the
        pre-signed URL, never the bare (private, inaccessible) canonical URL.

        This deliberately does NOT stub presign_url — only the boto3 client is
        mocked — so it fails if a future change reverts to returning the
        canonical/public URL the way commit 875bde0 did.
        """
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        job = await _insert_job(db, contractor.id, client.id)

        with (
            patch("app.ai.handlers.invoices.upload_file", return_value=_FAKE_PDF_URL),
            patch("app.storage.client._make_s3", return_value=_fake_s3()),
        ):
            result = await handle_create_invoice(
                _make_job_input(client.id, [job.id]), db, session
            )

        # The signed link carries a signature query param ...
        assert "PDF: https://signed.example/test.pdf?sig=abc" in result
        # ... and the bare canonical URL must NOT be what we hand to the user.
        assert f"PDF: {_FAKE_PDF_URL}" not in result

    async def test_data_isolation_rejects_other_contractor_client(
        self, db: AsyncSession
    ) -> None:
        contractor_a = await make_contractor(db)
        contractor_b = await make_contractor(db)
        client_b = await make_client(db, contractor_b)
        job_b = await _insert_job(db, contractor_b.id, client_b.id)
        session = await make_session(db, contractor_a)

        result = await handle_create_invoice(
            _make_job_input(client_b.id, [job_b.id]), db, session
        )

        assert "not found" in result.lower()
        rows = await db.execute(select(Invoice).where(Invoice.contractor_id == contractor_a.id))
        assert rows.scalars().all() == []

    async def test_data_isolation_rejects_job_from_other_client(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        client_a = await make_client(db, contractor, name="Ana")
        client_b = await make_client(db, contractor, name="Beatriz")
        job_b = await _insert_job(db, contractor.id, client_b.id)
        session = await make_session(db, contractor)

        result = await handle_create_invoice(
            _make_job_input(client_a.id, [job_b.id]), db, session
        )

        assert "not found" in result.lower()

    async def test_already_invoiced_job_rejected(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        job = await _insert_job(db, contractor.id, client.id)
        job.status = JobStatus.invoiced
        await db.flush()

        result = await handle_create_invoice(_make_job_input(client.id, [job.id]), db, session)

        assert "already invoiced" in result.lower()

    async def test_optional_due_date(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        job = await _insert_job(db, contractor.id, client.id)

        with patch("app.ai.handlers.invoices.upload_file", return_value=_FAKE_PDF_URL):
            await handle_create_invoice(
                _make_job_input(client.id, [job.id], due_date="2025-07-30"), db, session
            )

        rows = await db.execute(select(Invoice).where(Invoice.contractor_id == contractor.id))
        inv = rows.scalars().one()
        assert inv.due_date == date(2025, 7, 30)

    async def test_invoice_counter_not_incremented_on_validation_error(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db, invoice_counter=0)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)

        # invalid — no job_ids
        await handle_create_invoice(
            {"client_id": str(client.id), "date": "2025-06-30"}, db, session
        )

        rows = await db.execute(select(Invoice).where(Invoice.contractor_id == contractor.id))
        assert rows.scalars().all() == []
        await db.refresh(contractor)
        assert contractor.invoice_counter == 0

    async def test_pdf_bytes_generated(self, db: AsyncSession) -> None:
        """PDF generation produces non-empty bytes (no reportlab crash)."""
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        session = await make_session(db, contractor)
        job = await _insert_job(db, contractor.id, client.id, amount=200.0)

        captured: list[bytes] = []

        def fake_upload(
            contractor_id: object, entity_type: object, file_bytes: bytes, ext: object, **_: object
        ) -> str:
            captured.append(file_bytes)
            return _FAKE_PDF_URL

        with patch("app.ai.handlers.invoices.upload_file", side_effect=fake_upload):
            await handle_create_invoice(_make_job_input(client.id, [job.id]), db, session)

        assert len(captured) == 1
        assert len(captured[0]) > 1000  # a real PDF is at least 1 KB
        assert captured[0].startswith(b"%PDF")
