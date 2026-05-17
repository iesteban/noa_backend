from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dispatcher import register
from app.models.client import Client
from app.models.contractor import Contractor
from app.models.session import ConversationSession
from app.pdf.budget import render_budget_pdf
from app.services.budget import create_budget
from app.storage.client import upload_file

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
