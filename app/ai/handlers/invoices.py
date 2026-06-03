from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.dispatcher import register
from app.messaging.whatsapp_sender import send_template_message
from app.models.client import Client
from app.models.contractor import Contractor
from app.models.invoice import Invoice, InvoiceStatus
from app.models.job import Job, JobStatus
from app.models.session import ConversationSession, UserType
from app.pdf.invoice import render_invoice_pdf
from app.services.invoice import create_invoice
from app.storage.client import presign_url, upload_file

logger = logging.getLogger(__name__)


def _missing_legal_fields(client: Client) -> list[str]:
    """Return the field labels required for a legal Spanish invoice that are missing."""
    missing = []
    if not client.nif:
        missing.append("NIF/CIF")
    if not client.address:
        missing.append("dirección")
    return missing


async def _request_client_data(
    db: AsyncSession,
    contractor_session: ConversationSession,
    client: Client,
    contractor: Contractor,
    job_ids: list[uuid.UUID],
    invoice_date: date,
    due_date: date | None,
    missing: list[str],
) -> str:
    """Store pending invoice state on the client's WhatsApp session and send the template."""
    client_session_row = await db.execute(
        select(ConversationSession).where(
            ConversationSession.phone_number == client.phone_number,
            ConversationSession.channel == "whatsapp",
            ConversationSession.user_type == UserType.client,
            ConversationSession.contractor_id == contractor_session.contractor_id,
        ).limit(1)
    )
    client_session = client_session_row.scalar_one_or_none()
    if client_session is None:
        client_session = ConversationSession(
            phone_number=client.phone_number,
            channel="whatsapp",
            user_type=UserType.client,
            contractor_id=contractor_session.contractor_id,
            client_id=client.id,
            context={},
        )
        db.add(client_session)
        await db.flush()

    client_session.context = {
        **client_session.context,
        "pending_invoice_data": {
            "job_ids": [str(j) for j in job_ids],
            "date": str(invoice_date),
            "due_date": str(due_date) if due_date else None,
            "step": "awaiting_data",
        },
    }
    await db.flush()

    await send_template_message(
        recipient_id=client.phone_number,
        template_name="solicitar_datos_factura",
        language_code="es",
        body_parameters=[client.name.split()[0], contractor.business_name or contractor.name],
    )

    missing_str = " y ".join(missing)
    return (
        f"Le he pedido a {client.name} su {missing_str} por WhatsApp. "
        f"Te aviso cuando los tenga y la factura esté lista."
    )


@register("create_invoice")
async def handle_create_invoice(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    # --- validate client_id ---
    try:
        client_id = uuid.UUID(str(tool_input["client_id"]))
    except (KeyError, ValueError):
        return "Invalid client_id — must be a UUID returned by search_client."

    # --- validate job_ids ---
    raw_job_ids = tool_input.get("job_ids")
    if not raw_job_ids or not isinstance(raw_job_ids, list):
        return "job_ids is required and must be a non-empty list of job UUIDs."
    try:
        job_ids = [uuid.UUID(str(j)) for j in raw_job_ids]
    except ValueError:
        return "Invalid job_ids — each entry must be a valid UUID."

    # --- validate date ---
    try:
        invoice_date = date.fromisoformat(str(tool_input["date"]))
    except (KeyError, ValueError):
        return "Invalid date — use YYYY-MM-DD format."

    # --- optional due_date ---
    due_date: date | None = None
    raw_due = tool_input.get("due_date")
    if raw_due:
        try:
            due_date = date.fromisoformat(str(raw_due))
        except ValueError:
            return "Invalid due_date — use YYYY-MM-DD format."

    # --- data isolation: client must belong to this contractor ---
    client = await db.get(Client, client_id)
    if client is None or client.contractor_id != session.contractor_id:
        return f"Client {client_id} not found."

    # --- load and validate jobs ---
    rows = await db.execute(
        select(Job).where(
            Job.id.in_(job_ids),
            Job.contractor_id == session.contractor_id,
            Job.client_id == client_id,
        )
    )
    jobs = list(rows.scalars().all())

    if len(jobs) != len(job_ids):
        found_ids = {job.id for job in jobs}
        missing_jobs = [j for j in job_ids if j not in found_ids]
        missing_ids = ", ".join(str(j) for j in missing_jobs)
        return f"Jobs not found or not owned by this client: {missing_ids}"

    already_invoiced = [job for job in jobs if job.status == JobStatus.invoiced]
    if already_invoiced:
        nums = ", ".join(str(j.id) for j in already_invoiced)
        return f"These jobs are already invoiced: {nums}"

    # --- load contractor (needed for rates and invoice number) ---
    contractor = await db.get(Contractor, session.contractor_id)
    if contractor is None:
        return "Session error: contractor record not found."

    # --- gate: NIF/CIF and address are legally required for a Spanish invoice ---
    missing = _missing_legal_fields(client)
    if missing:
        return await _request_client_data(
            db, session, client, contractor, job_ids, invoice_date, due_date, missing
        )

    # --- create invoice record ---
    invoice = await create_invoice(
        db=db,
        contractor=contractor,
        client=client,
        jobs=jobs,
        invoice_date=invoice_date,
        due_date=due_date,
    )

    # --- generate PDF and upload ---
    await db.refresh(invoice, ["lines"])
    pdf_bytes = render_invoice_pdf(
        invoice=invoice,
        contractor=contractor,
        client=client,
        lines=invoice.lines,
    )
    storage_url = upload_file(
        contractor_id=contractor.id,
        entity_type="invoices",
        file_bytes=pdf_bytes,
        ext="pdf",
    )
    invoice.pdf_url = storage_url
    await db.flush()

    # The bucket is private — hand the contractor a time-limited pre-signed link.
    pdf_link = presign_url(storage_url)

    return (
        f"Factura generada."
        f" Número: {invoice.invoice_number}"
        f" | Cliente: {client.name}"
        f" | Base: {float(invoice.subtotal):.2f}€"
        f" | IVA: {float(invoice.iva_amount):.2f}€"
        f" | IRPF: -{float(invoice.irpf_amount):.2f}€"
        f" | Total: {float(invoice.total):.2f}€"
        f" | PDF: {pdf_link}"
    )


@register("get_invoice_pdf")
async def handle_get_invoice_pdf(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    invoice_number = str(tool_input.get("invoice_number", "")).strip()
    if not invoice_number:
        return "invoice_number is required."

    row = await db.execute(
        select(Invoice).where(
            Invoice.invoice_number == invoice_number,
            Invoice.contractor_id == session.contractor_id,
        )
    )
    invoice = row.scalar_one_or_none()
    if invoice is None:
        return f"Invoice {invoice_number} not found."
    if not invoice.pdf_url:
        return f"Invoice {invoice_number} has no PDF on file."

    # The bucket is private — return a time-limited pre-signed link, not the
    # canonical (inaccessible) storage URL.
    return presign_url(invoice.pdf_url)


_MONTH_ES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}

_STATUS_ES: dict[InvoiceStatus, str] = {
    InvoiceStatus.draft: "Borrador",
    InvoiceStatus.sent: "Enviada",
    InvoiceStatus.paid: "Pagada",
    InvoiceStatus.overdue: "Vencida",
}

_PAGE_SIZE = 5
_MAX_LIMIT = 20


@register("list_invoices")
async def handle_list_invoices(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    # --- optional client_id filter ---
    client_id: uuid.UUID | None = None
    client_name: str | None = None
    raw_client_id = tool_input.get("client_id")
    if raw_client_id:
        try:
            client_id = uuid.UUID(str(raw_client_id))
        except ValueError:
            return "Invalid client_id — must be a UUID."
        client = await db.get(Client, client_id)
        if client is None or client.contractor_id != session.contractor_id:
            return f"Client {client_id} not found."
        client_name = client.name

    # --- optional date filters ---
    date_from: date | None = None
    date_to: date | None = None
    for key, target in (("date_from", "date_from"), ("date_to", "date_to")):
        raw = tool_input.get(key)
        if raw:
            try:
                parsed = date.fromisoformat(str(raw))
            except ValueError:
                return f"Invalid {key} — use YYYY-MM-DD format."
            if key == "date_from":
                date_from = parsed
            else:
                date_to = parsed

    # --- optional status filter ---
    status_filter: InvoiceStatus | None = None
    raw_status = tool_input.get("status")
    if raw_status:
        try:
            status_filter = InvoiceStatus(str(raw_status))
        except ValueError:
            valid = ", ".join(s.value for s in InvoiceStatus)
            return f"Invalid status — must be one of: {valid}."

    # --- pagination ---
    try:
        limit = min(int(tool_input.get("limit", _PAGE_SIZE)), _MAX_LIMIT)
        offset = max(int(tool_input.get("offset", 0)), 0)
    except (TypeError, ValueError):
        limit, offset = _PAGE_SIZE, 0

    # --- build query ---
    base = (
        select(Invoice)
        .where(Invoice.contractor_id == session.contractor_id)
        .options(selectinload(Invoice.client))
        .order_by(Invoice.date.desc(), Invoice.created_at.desc())
    )
    if client_id:
        base = base.where(Invoice.client_id == client_id)
    if date_from:
        base = base.where(Invoice.date >= date_from)
    if date_to:
        base = base.where(Invoice.date <= date_to)
    if status_filter:
        base = base.where(Invoice.status == status_filter)

    total_row = await db.execute(select(func.count()).select_from(base.subquery()))
    total: int = total_row.scalar_one()

    rows = await db.execute(base.offset(offset).limit(limit))
    invoices = list(rows.scalars().all())

    if not invoices:
        if offset > 0:
            return "No hay más facturas."
        filter_desc = f" de {client_name}" if client_name else ""
        return f"No hay facturas{filter_desc}."

    # --- build header ---
    header_parts = ["Facturas"]
    if status_filter:
        header_parts.append(_STATUS_ES.get(status_filter, status_filter.value).lower() + "s")
    if client_name:
        header_parts.append(f"— {client_name}")
    header = " ".join(header_parts)

    # --- format rows ---
    lines = [header]
    for inv in invoices:
        d = f"{inv.date.day} {_MONTH_ES[inv.date.month]}"
        status_label = _STATUS_ES.get(inv.status, inv.status.value)
        name_part = f" · {inv.client.name}" if not client_name else ""
        lines.append(
            f"· {inv.invoice_number}{name_part} · {d} · {float(inv.total):.0f}€ · {status_label}"
        )

    end = offset + len(invoices)
    if total > end:
        lines.append(f"Mostrando {offset + 1}–{end} de {total}. (Ver más)")
    elif total > _PAGE_SIZE:
        lines.append(f"Total: {total} facturas.")

    return "\n".join(lines)
