"""State machine for collecting missing client NIF/address to complete a pending invoice."""
from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.contractor import Contractor
from app.models.invoice import Invoice
from app.models.job import Job, JobStatus
from app.models.session import ConversationSession
from app.pdf.invoice import render_invoice_pdf
from app.services.invoice import create_invoice
from app.services.nif_validation import extract_address, extract_emails, validate_nif
from app.storage.client import upload_file

logger = logging.getLogger(__name__)

_BUTTON_REPLY = "Enviar mis datos"


async def process_client_data_reply(
    db: AsyncSession,
    session: ConversationSession,
    text: str,
) -> tuple[str, str | None]:
    """Process one turn of the invoice-data collection conversation.

    Returns (reply_to_client, contractor_notification).
    contractor_notification is non-None when the invoice has been created.
    """
    pending: dict[str, Any] = session.context["pending_invoice_data"]
    step: str = pending.get("step", "awaiting_data")

    if step == "awaiting_data" and text.strip() == _BUTTON_REPLY:
        _set_step(session, pending, "awaiting_nif")
        return "Escríbeme tu NIF o CIF:", None

    if step in ("awaiting_data", "awaiting_nif"):
        return await _handle_nif_step(db, session, pending, text)

    if step == "awaiting_address":
        return await _handle_address_step(db, session, pending, text)

    return "Gracias, procesando tu información.", None


# ---------------------------------------------------------------------------
# Step handlers
# ---------------------------------------------------------------------------

async def _handle_nif_step(
    db: AsyncSession,
    session: ConversationSession,
    pending: dict[str, Any],
    text: str,
) -> tuple[str, str | None]:
    nif = validate_nif(text)
    if not nif:
        _set_step(session, pending, "awaiting_nif")
        return (
            "No he encontrado un NIF o CIF válido en tu mensaje. "
            "Escríbemelo de nuevo (ejemplo: 12345678A):",
            None,
        )

    emails = extract_emails(text)
    address = extract_address(text)
    if address:
        return await _finalize(db, session, pending, nif, address, emails)

    session.context = {
        **session.context,
        "pending_invoice_data": {
            **pending,
            "step": "awaiting_address",
            "collected_nif": nif,
            "collected_emails": emails,
        },
    }
    return (
        "Gracias. Ahora escríbeme tu dirección completa "
        "(calle, número, código postal y ciudad):",
        None,
    )


async def _handle_address_step(
    db: AsyncSession,
    session: ConversationSession,
    pending: dict[str, Any],
    text: str,
) -> tuple[str, str | None]:
    address = text.strip()
    if len(address) < 10:
        return (
            "La dirección no parece completa. "
            "Escríbela incluyendo calle, número, código postal y ciudad:",
            None,
        )
    nif = str(pending.get("collected_nif", ""))
    emails = list(pending.get("collected_emails") or [])
    return await _finalize(db, session, pending, nif, address, emails)


# ---------------------------------------------------------------------------
# Finalization
# ---------------------------------------------------------------------------

async def _finalize(
    db: AsyncSession,
    session: ConversationSession,
    pending: dict[str, Any],
    nif: str,
    address: str,
    emails: list[str],
) -> tuple[str, str | None]:
    client = await _load_client(db, session)
    if client is None:
        _clear_pending(session)
        return "No he podido procesar tu información. Contacta con tu profesional.", None

    contractor = await db.get(Contractor, session.contractor_id)
    if contractor is None:
        _clear_pending(session)
        return "No he podido procesar tu información. Contacta con tu profesional.", None

    _save_client_profile(client, nif, address, emails)
    await db.flush()

    jobs = await _load_valid_jobs(db, session, client, pending)
    if jobs is None:
        _clear_pending(session)
        return (
            "Ha habido un problema al generar la factura. Tu profesional te contactará pronto.",
            f"Problema al facturar a {client.name}: verifica el estado de los trabajos.",
        )

    invoice_date = date.fromisoformat(pending["date"])
    due_date = date.fromisoformat(pending["due_date"]) if pending.get("due_date") else None
    invoice = await create_invoice(
        db=db,
        contractor=contractor,
        client=client,
        jobs=jobs,
        invoice_date=invoice_date,
        due_date=due_date,
    )
    await db.refresh(invoice, ["lines"])
    await _upload_invoice_pdf(db, invoice, contractor, client)

    _clear_pending(session)
    return _build_replies(client, invoice)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _load_client(db: AsyncSession, session: ConversationSession) -> Client | None:
    if session.client_id is None:
        return None
    return await db.get(Client, session.client_id)


def _save_client_profile(client: Client, nif: str, address: str, emails: list[str]) -> None:
    client.nif = nif
    client.address = address
    if emails:
        client.email = emails[0]


async def _load_valid_jobs(
    db: AsyncSession,
    session: ConversationSession,
    client: Client,
    pending: dict[str, Any],
) -> list[Job] | None:
    job_ids = [uuid.UUID(j) for j in pending["job_ids"]]
    rows = await db.execute(
        select(Job).where(
            Job.id.in_(job_ids),
            Job.contractor_id == session.contractor_id,
            Job.client_id == client.id,
        )
    )
    jobs = list(rows.scalars().all())
    if len(jobs) != len(job_ids) or any(j.status == JobStatus.invoiced for j in jobs):
        return None
    return jobs


async def _upload_invoice_pdf(
    db: AsyncSession,
    invoice: Invoice,
    contractor: Contractor,
    client: Client,
) -> None:
    try:
        pdf_bytes = render_invoice_pdf(
            invoice=invoice,
            contractor=contractor,
            client=client,
            lines=invoice.lines,
        )
        invoice.pdf_url = upload_file(
            contractor_id=contractor.id,
            entity_type="invoices",
            file_bytes=pdf_bytes,
            ext="pdf",
            public=True,
        )
        await db.flush()
    except Exception:
        logger.exception("PDF generation failed for invoice %s", invoice.invoice_number)


def _build_replies(client: Client, invoice: Invoice) -> tuple[str, str]:
    contractor_msg = (
        f"Factura lista para {client.name}."
        f" Número: {invoice.invoice_number}"
        f" | Total: {float(invoice.total):.2f}€."
        f" ¿Se la envío?"
    )
    return (
        "¡Gracias! He registrado tus datos. Tu profesional te enviará la factura en breve.",
        contractor_msg,
    )


def _set_step(session: ConversationSession, pending: dict[str, Any], step: str) -> None:
    session.context = {**session.context, "pending_invoice_data": {**pending, "step": step}}


def _clear_pending(session: ConversationSession) -> None:
    session.context = {k: v for k, v in session.context.items() if k != "pending_invoice_data"}
