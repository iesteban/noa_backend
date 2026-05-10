"""Integration tests for contractor instruction tool handlers and Layer 3 injection."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import build_contractor_context
from app.ai.handlers.instructions import (
    handle_delete_instruction,
    handle_list_instructions,
    handle_save_instruction,
)
from app.models.instruction import ContractorInstruction
from tests.integration.conftest import make_contractor, make_session


async def _make_instruction(
    db: AsyncSession,
    contractor_id: uuid.UUID,
    *,
    scope: str = "global",
    instruction: str = "Tono informal",
) -> ContractorInstruction:
    instr = ContractorInstruction(
        contractor_id=contractor_id,
        scope=scope,
        instruction=instruction,
    )
    db.add(instr)
    await db.flush()
    return instr


class TestSaveInstruction:
    async def test_saves_instruction(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_save_instruction(
            {"scope": "invoices", "instruction": "Añadir pie: Garantía 12 meses"},
            db,
            session,
        )

        assert "guardada" in result.lower()
        row = await db.execute(
            select(ContractorInstruction).where(
                ContractorInstruction.contractor_id == contractor.id,
                ContractorInstruction.active.is_(True),
            )
        )
        assert row.scalar_one_or_none() is not None

    async def test_all_scopes_accepted(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        for scope in ("global", "invoices", "budgets", "reminders", "appointments"):
            result = await handle_save_instruction(
                {"scope": scope, "instruction": f"instrucción para {scope}"},
                db,
                session,
            )
            assert "guardada" in result.lower(), f"failed for scope={scope}"

    async def test_invalid_scope_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_save_instruction(
            {"scope": "unknown", "instruction": "algo"},
            db,
            session,
        )

        assert "no válido" in result.lower()

    async def test_instruction_too_long_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_save_instruction(
            {"scope": "global", "instruction": "x" * 281},
            db,
            session,
        )

        assert "demasiado larga" in result.lower()

    async def test_cap_at_20(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        for i in range(20):
            await _make_instruction(db, contractor.id, instruction=f"instrucción {i}")

        result = await handle_save_instruction(
            {"scope": "global", "instruction": "una más"},
            db,
            session,
        )

        assert "máximo" in result.lower()

    async def test_missing_instruction_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_save_instruction({"scope": "global"}, db, session)

        assert "required" in result.lower()


class TestListInstructions:
    async def test_returns_instructions(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await _make_instruction(db, contractor.id, scope="invoices", instruction="Pie garantía")
        await _make_instruction(db, contractor.id, scope="budgets", instruction="Incluir IVA")

        result = await handle_list_instructions({}, db, session)

        assert "garantía" in result.lower()
        assert "iva" in result.lower()

    async def test_returns_empty_message_when_none(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_list_instructions({}, db, session)

        assert "no tienes" in result.lower()

    async def test_isolated_between_contractors(self, db: AsyncSession) -> None:
        contractor_a = await make_contractor(db, phone_number="+34600000001")
        contractor_b = await make_contractor(db, phone_number="+34600000002")
        session_b = await make_session(db, contractor_b)
        await _make_instruction(db, contractor_a.id, instruction="instrucción de A")

        result = await handle_list_instructions({}, db, session_b)

        assert "instrucción de A" not in result


class TestDeleteInstruction:
    async def test_deletes_instruction(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        instr = await _make_instruction(db, contractor.id)

        result = await handle_delete_instruction(
            {"instruction_id": str(instr.id)}, db, session
        )

        assert "eliminada" in result.lower()
        row = await db.execute(
            select(ContractorInstruction).where(
                ContractorInstruction.id == instr.id,
                ContractorInstruction.active.is_(True),
            )
        )
        assert row.scalar_one_or_none() is None

    async def test_cannot_delete_other_contractors_instruction(
        self, db: AsyncSession
    ) -> None:
        contractor_a = await make_contractor(db, phone_number="+34600000001")
        contractor_b = await make_contractor(db, phone_number="+34600000002")
        session_b = await make_session(db, contractor_b)
        instr = await _make_instruction(db, contractor_a.id)

        result = await handle_delete_instruction(
            {"instruction_id": str(instr.id)}, db, session_b
        )

        assert "no encontrada" in result.lower()
        # Instruction still active for contractor_a.
        row = await db.execute(
            select(ContractorInstruction).where(
                ContractorInstruction.id == instr.id,
                ContractorInstruction.active.is_(True),
            )
        )
        assert row.scalar_one_or_none() is not None

    async def test_invalid_uuid_returns_error(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        result = await handle_delete_instruction(
            {"instruction_id": "not-a-uuid"}, db, session
        )

        assert "no válido" in result.lower()

    async def test_already_deleted_returns_not_found(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        instr = await _make_instruction(db, contractor.id)
        instr.active = False
        await db.flush()

        result = await handle_delete_instruction(
            {"instruction_id": str(instr.id)}, db, session
        )

        assert "no encontrada" in result.lower()


class TestContextInjection:
    async def test_instructions_appear_in_layer3(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        await _make_instruction(
            db, contractor.id, scope="invoices", instruction="Pie garantía 12 meses"
        )
        await _make_instruction(
            db, contractor.id, scope="budgets", instruction="Materiales incluidos"
        )

        context = await build_contractor_context(db, contractor)

        assert "Instrucciones personales" in context
        assert "Pie garantía 12 meses" in context
        assert "Materiales incluidos" in context
        assert "[facturas]" in context
        assert "[presupuestos]" in context

    async def test_inactive_instructions_excluded(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        instr = await _make_instruction(
            db, contractor.id, instruction="instrucción inactiva"
        )
        instr.active = False
        await db.flush()

        context = await build_contractor_context(db, contractor)

        assert "instrucción inactiva" not in context

    async def test_no_instructions_section_when_empty(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)

        context = await build_contractor_context(db, contractor)

        assert "Instrucciones personales" not in context
