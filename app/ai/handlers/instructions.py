from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dispatcher import register
from app.models.instruction import ContractorInstruction, InstructionScope
from app.models.session import ConversationSession

_MAX_INSTRUCTIONS = 20

_VALID_SCOPES = {m.value for m in InstructionScope}

_SCOPE_LABELS: dict[str, str] = {
    "global": "global",
    "invoices": "facturas",
    "budgets": "presupuestos",
    "reminders": "recordatorios",
    "appointments": "citas",
}


@register("list_instructions")
async def handle_list_instructions(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    result = await db.execute(
        select(ContractorInstruction)
        .where(
            ContractorInstruction.contractor_id == session.contractor_id,
            ContractorInstruction.active.is_(True),
        )
        .order_by(ContractorInstruction.created_at)
    )
    instructions = list(result.scalars().all())

    if not instructions:
        return "No tienes instrucciones guardadas."

    lines = [f"Tienes {len(instructions)} instrucción(es) guardada(s):"]
    for instr in instructions:
        label = _SCOPE_LABELS.get(instr.scope, instr.scope)
        lines.append(f"- [{label}] {instr.instruction}  id={instr.id}")
    return "\n".join(lines)


@register("save_instruction")
async def handle_save_instruction(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    scope = str(tool_input.get("scope", "")).strip()
    if scope not in _VALID_SCOPES:
        return (
            f"Ámbito '{scope}' no válido. "
            f"Usa uno de: {', '.join(sorted(_VALID_SCOPES))}."
        )

    instruction = str(tool_input.get("instruction", "")).strip()
    if not instruction:
        return "instruction is required."
    if len(instruction) > 280:
        return f"La instrucción es demasiado larga ({len(instruction)} caracteres, máximo 280)."

    count: int = (
        await db.scalar(
            select(func.count())
            .select_from(ContractorInstruction)
            .where(
                ContractorInstruction.contractor_id == session.contractor_id,
                ContractorInstruction.active.is_(True),
            )
        )
    ) or 0

    if count >= _MAX_INSTRUCTIONS:
        return (
            f"Ya tienes {_MAX_INSTRUCTIONS} instrucciones guardadas (máximo). "
            "Elimina alguna antes de añadir una nueva."
        )

    instr = ContractorInstruction(
        contractor_id=session.contractor_id,
        scope=scope,
        instruction=instruction,
    )
    db.add(instr)
    await db.flush()

    label = _SCOPE_LABELS.get(scope, scope)
    return f"Instrucción guardada.\n  Ámbito: {label}\n  Texto: {instruction}\n  id={instr.id}"


@register("delete_instruction")
async def handle_delete_instruction(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    raw_id = str(tool_input.get("instruction_id", "")).strip()
    try:
        instr_id = uuid.UUID(raw_id)
    except ValueError:
        return f"ID de instrucción no válido: '{raw_id}'."

    result = await db.execute(
        select(ContractorInstruction).where(
            ContractorInstruction.id == instr_id,
            ContractorInstruction.contractor_id == session.contractor_id,
            ContractorInstruction.active.is_(True),
        )
    )
    instr = result.scalar_one_or_none()
    if instr is None:
        return "Instrucción no encontrada."

    instr.active = False
    await db.flush()
    return "Instrucción eliminada."
