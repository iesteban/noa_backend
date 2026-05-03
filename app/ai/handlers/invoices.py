from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dispatcher import register
from app.models.client import Client
from app.models.job import Job, JobStatus
from app.models.session import ConversationSession
from app.pdf.invoice import render_invoice_pdf
from app.services.invoice import create_invoice
from app.storage.client import upload_file

logger = logging.getLogger(__name__)


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
        missing = [j for j in job_ids if j not in found_ids]
        return f"Jobs not found or not owned by this client: {', '.join(str(j) for j in missing)}"

    already_invoiced = [job for job in jobs if job.status == JobStatus.invoiced]
    if already_invoiced:
        nums = ", ".join(str(j.id) for j in already_invoiced)
        return f"These jobs are already invoiced: {nums}"

    # --- load contractor (needed for rates and invoice number) ---
    from app.models.contractor import Contractor  # local to avoid circular at module level
    contractor = await db.get(Contractor, session.contractor_id)
    if contractor is None:
        return "Session error: contractor record not found."

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
    pdf_url = upload_file(
        contractor_id=contractor.id,
        entity_type="invoices",
        file_bytes=pdf_bytes,
        ext="pdf",
    )
    invoice.pdf_url = pdf_url
    await db.flush()

    return (
        f"Factura generada."
        f" Número: {invoice.invoice_number}"
        f" | Cliente: {client.name}"
        f" | Base: {float(invoice.subtotal):.2f}€"
        f" | IVA: {float(invoice.iva_amount):.2f}€"
        f" | IRPF: -{float(invoice.irpf_amount):.2f}€"
        f" | Total: {float(invoice.total):.2f}€"
        f" | PDF: {pdf_url}"
    )
