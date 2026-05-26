from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.dispatcher import register
from app.models.budget import Budget, BudgetStatus
from app.models.client import Client
from app.models.contractor import Contractor
from app.models.session import ConversationSession
from app.pdf.budget import render_budget_pdf
from app.services.budget import create_budget, delete_budget, update_budget
from app.storage.client import delete_file, upload_file

logger = logging.getLogger(__name__)


@register("create_budget")
async def handle_create_budget(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    # --- validate client_id ---
    import uuid
    try:
        client_id = uuid.UUID(str(tool_input["client_id"]))
    except (KeyError, ValueError):
        return "Invalid client_id — must be a UUID returned by search_client."

    # --- validate lines ---
    raw_lines = tool_input.get("lines")
    if not raw_lines or not isinstance(raw_lines, list):
        return "lines is required and must be a non-empty list."
    for i, ln in enumerate(raw_lines):
        if not isinstance(ln, dict):
            return f"Line {i}: must be an object with description, quantity, unit_price."
        for field in ("description", "quantity", "unit_price"):
            if field not in ln:
                return f"Line {i}: missing required field '{field}'."
        try:
            float(ln["quantity"])
            float(ln["unit_price"])
        except (TypeError, ValueError):
            return f"Line {i}: quantity and unit_price must be numbers."

    # --- optional valid_until ---
    valid_until: date | None = None
    raw_valid = tool_input.get("valid_until")
    if raw_valid:
        try:
            valid_until = date.fromisoformat(str(raw_valid))
        except ValueError:
            return "Invalid valid_until — use YYYY-MM-DD format."

    # --- data isolation: client must belong to this contractor ---
    client = await db.get(Client, client_id)
    if client is None or client.contractor_id != session.contractor_id:
        return f"Client {client_id} not found."

    contractor = await db.get(Contractor, session.contractor_id)
    if contractor is None:
        return "Session error: contractor record not found."

    # --- create budget record ---
    budget = await create_budget(
        db=db,
        contractor=contractor,
        client=client,
        lines_input=raw_lines,
        budget_date=date.today(),
        valid_until=valid_until,
    )

    # --- generate PDF and upload ---
    await db.refresh(budget, ["lines"])
    pdf_bytes = render_budget_pdf(
        budget=budget,
        contractor=contractor,
        client=client,
        lines=budget.lines,
    )
    pdf_url = upload_file(
        contractor_id=contractor.id,
        entity_type="budgets",
        file_bytes=pdf_bytes,
        ext="pdf",
        public=True,
    )
    budget.pdf_url = pdf_url
    await db.flush()

    line_count = len(budget.lines)
    return (
        f"Presupuesto generado."
        f" {line_count} línea{'s' if line_count != 1 else ''}."
        f" | Cliente: {client.name}"
        f" | Total: {float(budget.total):.2f}€"
        f" | PDF: {pdf_url}"
    )


_MONTH_ES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}

_STATUS_ES: dict[BudgetStatus, str] = {
    BudgetStatus.draft: "Borrador",
    BudgetStatus.sent: "Enviado",
    BudgetStatus.accepted: "Aceptado",
    BudgetStatus.rejected: "Rechazado",
    BudgetStatus.invoiced: "Facturado",
}

_PAGE_SIZE = 5
_MAX_LIMIT = 20


@register("list_budgets")
async def handle_list_budgets(
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
    for key in ("date_from", "date_to"):
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
    status_filter: BudgetStatus | None = None
    raw_status = tool_input.get("status")
    if raw_status:
        try:
            status_filter = BudgetStatus(str(raw_status))
        except ValueError:
            valid = ", ".join(s.value for s in BudgetStatus)
            return f"Invalid status — must be one of: {valid}."

    # --- pagination ---
    try:
        limit = min(int(tool_input.get("limit", _PAGE_SIZE)), _MAX_LIMIT)
        offset = max(int(tool_input.get("offset", 0)), 0)
    except (TypeError, ValueError):
        limit, offset = _PAGE_SIZE, 0

    # --- build query ---
    base = (
        select(Budget)
        .where(Budget.contractor_id == session.contractor_id)
        .options(selectinload(Budget.client))
        .order_by(Budget.date.desc(), Budget.created_at.desc())
    )
    if client_id:
        base = base.where(Budget.client_id == client_id)
    if date_from:
        base = base.where(Budget.date >= date_from)
    if date_to:
        base = base.where(Budget.date <= date_to)
    if status_filter:
        base = base.where(Budget.status == status_filter)

    total_row = await db.execute(select(func.count()).select_from(base.subquery()))
    total: int = total_row.scalar_one()

    rows = await db.execute(base.offset(offset).limit(limit))
    budgets = list(rows.scalars().all())

    if not budgets:
        if offset > 0:
            return "No hay más presupuestos."
        filter_desc = f" de {client_name}" if client_name else ""
        return f"No hay presupuestos{filter_desc}."

    # --- header ---
    header_parts = ["Presupuestos"]
    if status_filter:
        header_parts.append(_STATUS_ES.get(status_filter, status_filter.value).lower() + "s")
    if client_name:
        header_parts.append(f"— {client_name}")
    header = " ".join(header_parts)

    # --- format rows ---
    lines = [header]
    for b in budgets:
        d = f"{b.date.day} {_MONTH_ES[b.date.month]}"
        status_label = _STATUS_ES.get(b.status, b.status.value)
        name_part = f" · {b.client.name}" if not client_name else ""
        lines.append(f"· {d}{name_part} · {float(b.total):.0f}€ · {status_label}")

    end = offset + len(budgets)
    if total > end:
        lines.append(f"Mostrando {offset + 1}–{end} de {total}. (Ver más)")
    elif total > _PAGE_SIZE:
        lines.append(f"Total: {total} presupuestos.")

    return "\n".join(lines)


def _parse_budget_id(tool_input: dict[str, Any]) -> uuid.UUID | str:
    """Return parsed UUID or an error string."""
    try:
        return uuid.UUID(str(tool_input["budget_id"]))
    except (KeyError, ValueError):
        return "Invalid budget_id — must be a UUID."


async def _load_draft_budget(
    db: AsyncSession,
    budget_id: uuid.UUID,
    contractor_id: uuid.UUID,
) -> Budget | str:
    """Return the Budget or an error string if not found, wrong contractor, or non-draft."""
    budget = await db.get(Budget, budget_id)
    if budget is None or budget.contractor_id != contractor_id:
        return f"Budget {budget_id} not found."
    if budget.status != BudgetStatus.draft:
        return (
            f"Budget {budget_id} cannot be modified — "
            f"status is '{budget.status.value}' (only draft budgets can be edited or deleted)."
        )
    return budget


@register("update_budget")
async def handle_update_budget(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    budget_id = _parse_budget_id(tool_input)
    if isinstance(budget_id, str):
        return budget_id

    result = await _load_draft_budget(db, budget_id, session.contractor_id)
    if isinstance(result, str):
        return result
    budget = result

    # --- validate optional lines ---
    raw_lines: list[dict[str, object]] | None = None
    raw_lines_input = tool_input.get("lines")
    if raw_lines_input is not None:
        if not isinstance(raw_lines_input, list) or len(raw_lines_input) == 0:
            return "lines must be a non-empty list."
        for i, ln in enumerate(raw_lines_input):
            if not isinstance(ln, dict):
                return f"Line {i}: must be an object with description, quantity, unit_price."
            for field in ("description", "quantity", "unit_price"):
                if field not in ln:
                    return f"Line {i}: missing required field '{field}'."
            try:
                float(ln["quantity"])
                float(ln["unit_price"])
            except (TypeError, ValueError):
                return f"Line {i}: quantity and unit_price must be numbers."
        raw_lines = raw_lines_input

    # --- validate optional valid_until ---
    valid_until: date | None = None
    raw_valid = tool_input.get("valid_until")
    if raw_valid is not None:
        try:
            valid_until = date.fromisoformat(str(raw_valid))
        except ValueError:
            return "Invalid valid_until — use YYYY-MM-DD format."

    if raw_lines is None and raw_valid is None:
        return "Provide at least one of: lines, valid_until."

    contractor = await db.get(Contractor, session.contractor_id)
    if contractor is None:
        return "Session error: contractor record not found."

    old_pdf_url = budget.pdf_url

    budget = await update_budget(
        db=db,
        budget=budget,
        contractor=contractor,
        lines_input=raw_lines,
        valid_until=valid_until,
    )

    if raw_lines is not None:
        # Re-generate PDF with updated lines.
        await db.refresh(budget, ["lines", "client"])
        pdf_bytes = render_budget_pdf(
            budget=budget,
            contractor=contractor,
            client=budget.client,
            lines=budget.lines,
        )
        new_pdf_url = upload_file(
            contractor_id=contractor.id,
            entity_type="budgets",
            file_bytes=pdf_bytes,
            ext="pdf",
            public=True,
        )
        budget.pdf_url = new_pdf_url
        await db.flush()

        if old_pdf_url:
            try:
                delete_file(old_pdf_url)
            except Exception:
                logger.warning("Could not delete old PDF %s", old_pdf_url)

    line_count = len(budget.lines) if raw_lines is not None else None
    parts = [f"Presupuesto {budget_id} actualizado."]
    if line_count is not None:
        parts.append(f"{line_count} línea{'s' if line_count != 1 else ''}.")
    parts.append(f"Total: {float(budget.total):.2f}€")
    if budget.pdf_url:
        parts.append(f"PDF: {budget.pdf_url}")
    return " | ".join(parts)


@register("delete_budget")
async def handle_delete_budget(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    budget_id = _parse_budget_id(tool_input)
    if isinstance(budget_id, str):
        return budget_id

    result = await _load_draft_budget(db, budget_id, session.contractor_id)
    if isinstance(result, str):
        return result
    budget = result

    pdf_url = await delete_budget(db=db, budget=budget)

    if pdf_url:
        try:
            delete_file(pdf_url)
        except Exception:
            logger.warning("Could not delete PDF %s for budget %s", pdf_url, budget_id)

    return f"Presupuesto {budget_id} eliminado."
