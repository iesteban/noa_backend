from __future__ import annotations

from datetime import date

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import Budget, BudgetLine, BudgetStatus
from app.models.client import Client
from app.models.contractor import Contractor


async def create_budget(
    db: AsyncSession,
    contractor: Contractor,
    client: Client,
    lines_input: list[dict[str, object]],
    budget_date: date,
    valid_until: date | None,
) -> Budget:
    """Create a Budget with lines. total = subtotal + IVA (no IRPF on presupuestos)."""
    iva_rate = float(contractor.iva_rate)

    lines: list[BudgetLine] = []
    subtotal = 0.0
    for item in lines_input:
        qty = float(item["quantity"])  # type: ignore[arg-type]
        price = float(item["unit_price"])  # type: ignore[arg-type]
        line_total = round(qty * price, 2)
        lines.append(
            BudgetLine(
                description=str(item["description"]),
                quantity=qty,
                unit_price=price,
                iva_rate=iva_rate,
                line_total=line_total,
            )
        )
        subtotal += line_total

    iva_amount = round(subtotal * iva_rate, 2)
    total = round(subtotal + iva_amount, 2)

    budget = Budget(
        contractor_id=contractor.id,
        client_id=client.id,
        date=budget_date,
        valid_until=valid_until,
        status=BudgetStatus.draft,
        total=total,
    )
    db.add(budget)
    await db.flush()

    for line in lines:
        line.budget_id = budget.id
        db.add(line)

    await db.flush()
    return budget


async def update_budget(
    db: AsyncSession,
    budget: Budget,
    contractor: Contractor,
    lines_input: list[dict[str, object]] | None,
    valid_until: date | None,
) -> Budget:
    """Replace line items and/or valid_until on a draft budget. Returns the updated budget."""
    if valid_until is not None:
        budget.valid_until = valid_until

    if lines_input is not None:
        await db.execute(delete(BudgetLine).where(BudgetLine.budget_id == budget.id))

        iva_rate = float(contractor.iva_rate)
        subtotal = 0.0
        new_lines: list[BudgetLine] = []
        for item in lines_input:
            qty = float(item["quantity"])  # type: ignore[arg-type]
            price = float(item["unit_price"])  # type: ignore[arg-type]
            line_total = round(qty * price, 2)
            new_lines.append(
                BudgetLine(
                    budget_id=budget.id,
                    description=str(item["description"]),
                    quantity=qty,
                    unit_price=price,
                    iva_rate=iva_rate,
                    line_total=line_total,
                )
            )
            subtotal += line_total

        for line in new_lines:
            db.add(line)

        iva_amount = round(subtotal * iva_rate, 2)
        budget.total = round(subtotal + iva_amount, 2)

    await db.flush()
    return budget


async def delete_budget(db: AsyncSession, budget: Budget) -> str | None:
    """Delete a draft budget and its lines. Returns the pdf_url for storage cleanup."""
    pdf_url = budget.pdf_url
    await db.execute(delete(BudgetLine).where(BudgetLine.budget_id == budget.id))
    await db.delete(budget)
    await db.flush()
    return pdf_url
