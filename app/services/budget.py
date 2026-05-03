from __future__ import annotations

from datetime import date

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
