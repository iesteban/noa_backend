from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.contractor import Contractor
from app.models.invoice import Invoice, InvoiceLine, InvoiceStatus
from app.models.job import Job, JobStatus


async def create_invoice(
    db: AsyncSession,
    contractor: Contractor,
    client: Client,
    jobs: list[Job],
    invoice_date: date,
    due_date: date | None,
) -> Invoice:
    """Create an Invoice with lines. Atomically increments invoice_counter."""
    result = await db.execute(
        text(
            "UPDATE contractors SET invoice_counter = invoice_counter + 1 "
            "WHERE id = :id RETURNING invoice_counter"
        ),
        {"id": contractor.id},
    )
    counter: int = result.scalar_one()
    invoice_number = f"{invoice_date.year}-{counter:03d}"

    iva_rate = float(contractor.iva_rate)
    irpf_rate = float(contractor.irpf_rate)

    subtotal = sum(float(job.amount or 0) for job in jobs)
    iva_amount = round(subtotal * iva_rate, 2)
    irpf_amount = round(subtotal * irpf_rate, 2)
    total = round(subtotal + iva_amount - irpf_amount, 2)

    invoice = Invoice(
        contractor_id=contractor.id,
        client_id=client.id,
        invoice_number=invoice_number,
        date=invoice_date,
        due_date=due_date,
        status=InvoiceStatus.draft,
        subtotal=subtotal,
        iva_amount=iva_amount,
        irpf_amount=irpf_amount,
        total=total,
    )
    db.add(invoice)
    await db.flush()

    for job in jobs:
        line = InvoiceLine(
            invoice_id=invoice.id,
            job_id=job.id,
            description=job.description,
            quantity=1,
            unit_price=float(job.amount or 0),
            iva_rate=iva_rate,
            irpf_rate=irpf_rate,
            line_total=float(job.amount or 0),
        )
        db.add(line)
        job.status = JobStatus.invoiced

    await db.flush()
    return invoice
