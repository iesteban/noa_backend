"""Integration tests for the invoice data collection flow (issue #113)."""
from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.invoice import Invoice
from app.models.job import JobStatus
from app.models.session import ConversationSession, UserType
from app.services.invoice_data_collection import process_client_data_reply
from tests.integration.conftest import (
    make_client,
    make_contractor,
    make_job,
    make_session,
)

_FAKE_PDF_URL = "https://noa-dev.s3.fr-par.scw.cloud/fake/invoices/test.pdf"
_PDF_PATCHES = (
    patch("app.services.invoice_data_collection.render_invoice_pdf", return_value=b"pdf"),
    patch("app.services.invoice_data_collection.upload_file", return_value=_FAKE_PDF_URL),
)


async def _make_client_session(
    db: AsyncSession,
    contractor_id: uuid.UUID,
    client: Client,
    pending: dict,  # type: ignore[type-arg]
) -> ConversationSession:
    session = ConversationSession(
        phone_number=client.phone_number,
        channel="whatsapp",
        user_type=UserType.client,
        contractor_id=contractor_id,
        client_id=client.id,
        context={"pending_invoice_data": pending},
    )
    db.add(session)
    await db.flush()
    return session


def _pending(job_ids: list[uuid.UUID], step: str = "awaiting_data") -> dict:  # type: ignore[type-arg]
    return {
        "job_ids": [str(j) for j in job_ids],
        "date": str(date.today()),
        "due_date": None,
        "step": step,
    }


def _pending_address(job_ids: list[uuid.UUID], emails: list[str] | None = None) -> dict:  # type: ignore[type-arg]
    return {
        **_pending(job_ids, "awaiting_address"),
        "collected_nif": "12345678Z",
        "collected_emails": emails or [],
    }


class TestButtonReply:
    async def test_button_click_transitions_to_awaiting_nif(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        job = await make_job(db, contractor, client)
        session = await _make_client_session(
            db, contractor.id, client, _pending([job.id])
        )

        reply, notification = await process_client_data_reply(db, session, "Enviar mis datos")

        assert "NIF" in reply
        assert notification is None
        assert session.context["pending_invoice_data"]["step"] == "awaiting_nif"


class TestNifStep:
    async def test_invalid_nif_asks_again(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        job = await make_job(db, contractor, client)
        session = await _make_client_session(
            db, contractor.id, client, _pending([job.id], "awaiting_nif")
        )

        reply, notification = await process_client_data_reply(db, session, "mi nif es INVALIDO")

        assert "válido" in reply
        assert notification is None
        assert session.context["pending_invoice_data"]["step"] == "awaiting_nif"

    async def test_valid_nif_without_address_asks_for_address(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        job = await make_job(db, contractor, client)
        session = await _make_client_session(
            db, contractor.id, client, _pending([job.id], "awaiting_nif")
        )

        reply, notification = await process_client_data_reply(db, session, "Mi NIF: 12345678Z")

        assert "dirección" in reply.lower()
        assert notification is None
        assert session.context["pending_invoice_data"]["step"] == "awaiting_address"
        assert session.context["pending_invoice_data"]["collected_nif"] == "12345678Z"

    async def test_nif_with_address_in_same_message_creates_invoice(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        job = await make_job(db, contractor, client)
        session = await _make_client_session(
            db, contractor.id, client, _pending([job.id], "awaiting_nif")
        )

        with _PDF_PATCHES[0], _PDF_PATCHES[1]:
            reply, notification = await process_client_data_reply(
                db, session, "12345678Z Calle Mayor 15, 28013 Madrid"
            )

        assert "gracias" in reply.lower()
        assert notification is not None
        assert "Factura" in notification
        rows = await db.execute(select(Invoice).where(Invoice.contractor_id == contractor.id))
        assert rows.scalar_one_or_none() is not None

    async def test_client_nif_saved_to_profile(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        job = await make_job(db, contractor, client)
        session = await _make_client_session(
            db, contractor.id, client, _pending([job.id], "awaiting_nif")
        )

        with _PDF_PATCHES[0], _PDF_PATCHES[1]:
            await process_client_data_reply(
                db, session, "12345678Z Calle Mayor 15, 28013 Madrid"
            )

        await db.refresh(client)
        assert client.nif == "12345678Z"
        assert client.address is not None
        assert "Mayor" in client.address


class TestAddressStep:
    async def test_short_address_asks_again(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        job = await make_job(db, contractor, client)
        session = await _make_client_session(
            db, contractor.id, client, _pending_address([job.id])
        )

        reply, notification = await process_client_data_reply(db, session, "Madrid")

        assert "completa" in reply.lower()
        assert notification is None

    async def test_valid_address_creates_invoice(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        job = await make_job(db, contractor, client)
        session = await _make_client_session(
            db, contractor.id, client, _pending_address([job.id])
        )

        with _PDF_PATCHES[0], _PDF_PATCHES[1]:
            reply, notification = await process_client_data_reply(
                db, session, "Calle Gran Vía 44, 28013 Madrid"
            )

        assert notification is not None
        assert "pending_invoice_data" not in session.context
        rows = await db.execute(select(Invoice).where(Invoice.contractor_id == contractor.id))
        invoice = rows.scalar_one_or_none()
        assert invoice is not None
        assert invoice.invoice_number.endswith("001")

    async def test_job_marked_invoiced_after_collection(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        job = await make_job(db, contractor, client)
        session = await _make_client_session(
            db, contractor.id, client, _pending_address([job.id])
        )

        with _PDF_PATCHES[0], _PDF_PATCHES[1]:
            await process_client_data_reply(db, session, "Calle Gran Vía 44, 28013 Madrid")

        await db.refresh(job)
        assert job.status == JobStatus.invoiced

    async def test_email_saved_when_included(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        job = await make_job(db, contractor, client)
        session = await _make_client_session(
            db, contractor.id, client, _pending_address([job.id], ["pedro@example.com"])
        )

        with _PDF_PATCHES[0], _PDF_PATCHES[1]:
            await process_client_data_reply(db, session, "Calle Gran Vía 44, 28013 Madrid")

        await db.refresh(client)
        assert client.email == "pedro@example.com"

    async def test_email_not_required_invoice_still_created(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        job = await make_job(db, contractor, client)
        session = await _make_client_session(
            db, contractor.id, client, _pending_address([job.id])
        )

        with _PDF_PATCHES[0], _PDF_PATCHES[1]:
            reply, notification = await process_client_data_reply(
                db, session, "Calle Gran Vía 44, 28013 Madrid"
            )

        assert notification is not None
        rows = await db.execute(select(Invoice).where(Invoice.contractor_id == contractor.id))
        assert rows.scalar_one_or_none() is not None


class TestInvoiceHandlerGate:
    async def test_skips_template_when_data_present(self, db: AsyncSession) -> None:
        from app.ai.handlers.invoices import handle_create_invoice

        contractor = await make_contractor(db)
        client = await make_client(
            db, contractor, nif="12345678Z", address="Calle Mayor 1, 28001 Madrid"
        )
        job = await make_job(db, contractor, client)
        session = await make_session(db, contractor)

        with (
            patch("app.ai.handlers.invoices.send_template_message") as mock_tpl,
            patch("app.ai.handlers.invoices.render_invoice_pdf", return_value=b"pdf"),
            patch("app.ai.handlers.invoices.upload_file", return_value=_FAKE_PDF_URL),
        ):
            result = await handle_create_invoice(
                {"client_id": str(client.id), "job_ids": [str(job.id)], "date": "2025-06-30"},
                db,
                session,
            )
            mock_tpl.assert_not_called()

        assert "Factura" in result

    async def test_sends_template_when_nif_missing(self, db: AsyncSession) -> None:
        from app.ai.handlers.invoices import handle_create_invoice

        contractor = await make_contractor(db)
        client = await make_client(db, contractor, address="Calle Mayor 1, 28001 Madrid")
        job = await make_job(db, contractor, client)
        session = await make_session(db, contractor)

        with patch(
            "app.ai.handlers.invoices.send_template_message", new_callable=AsyncMock
        ) as mock_tpl:
            result = await handle_create_invoice(
                {"client_id": str(client.id), "job_ids": [str(job.id)], "date": "2025-06-30"},
                db,
                session,
            )
            mock_tpl.assert_called_once()

        assert "NIF/CIF" in result
        assert "pedido" in result

    async def test_sends_template_when_address_missing(self, db: AsyncSession) -> None:
        from app.ai.handlers.invoices import handle_create_invoice

        contractor = await make_contractor(db)
        client = await make_client(db, contractor, nif="12345678Z")
        job = await make_job(db, contractor, client)
        session = await make_session(db, contractor)

        with patch(
            "app.ai.handlers.invoices.send_template_message", new_callable=AsyncMock
        ) as mock_tpl:
            result = await handle_create_invoice(
                {"client_id": str(client.id), "job_ids": [str(job.id)], "date": "2025-06-30"},
                db,
                session,
            )
            mock_tpl.assert_called_once()

        assert "dirección" in result

    async def test_creates_client_session_with_pending_context(self, db: AsyncSession) -> None:
        from app.ai.handlers.invoices import handle_create_invoice

        contractor = await make_contractor(db)
        client = await make_client(db, contractor)
        job = await make_job(db, contractor, client)
        session = await make_session(db, contractor)

        with patch(
            "app.ai.handlers.invoices.send_template_message", new_callable=AsyncMock
        ):
            await handle_create_invoice(
                {"client_id": str(client.id), "job_ids": [str(job.id)], "date": "2025-06-30"},
                db,
                session,
            )

        rows = await db.execute(
            select(ConversationSession).where(
                ConversationSession.phone_number == client.phone_number,
                ConversationSession.user_type == UserType.client,
            )
        )
        client_session = rows.scalar_one_or_none()
        assert client_session is not None
        assert "pending_invoice_data" in client_session.context
        pending = client_session.context["pending_invoice_data"]
        assert str(job.id) in pending["job_ids"]
        assert pending["step"] == "awaiting_data"
