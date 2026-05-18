"""Integration tests for error-report service — real PostgreSQL."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.webhook import _try_handle_error_report
from app.models.error_report import ErrorReport, Platform
from app.models.session import MessageRole, UserType
from app.services.error_report import get_last_assistant_message, save_error_report
from tests.integration.conftest import make_contractor, make_message, make_session


class TestSaveErrorReport:
    async def test_saves_fields_to_db(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        await save_error_report(db, session, "la factura está mal", "telegram")

        row = await db.execute(
            select(ErrorReport).where(ErrorReport.contractor_id == contractor.id)
        )
        report = row.scalar_one()
        assert report.user_message == "la factura está mal"
        assert report.platform == Platform.telegram
        assert report.contractor_id == contractor.id
        assert report.created_at is not None

    async def test_whatsapp_platform_saved(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)

        await save_error_report(db, session, "algo falló", "whatsapp")

        row = await db.execute(
            select(ErrorReport).where(ErrorReport.contractor_id == contractor.id)
        )
        assert row.scalar_one().platform == Platform.whatsapp

    async def test_context_captures_last_5_of_7_messages(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        now = datetime.now(UTC)
        for i in range(7):
            await make_message(
                db, session, MessageRole.user, f"msg {i}",
                created_at=now + timedelta(seconds=i),
            )

        await save_error_report(db, session, "error", "telegram")

        row = await db.execute(
            select(ErrorReport).where(ErrorReport.contractor_id == contractor.id)
        )
        report = row.scalar_one()
        assert len(report.context_json) == 5
        contents = [m["content"] for m in report.context_json]
        assert "msg 6" in contents
        assert "msg 2" in contents   # 5th-newest (idx 2 of 0-6)
        assert "msg 1" not in contents  # older than the last 5
        assert "msg 0" not in contents

    async def test_context_fewer_than_5_messages(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await make_message(db, session, MessageRole.user, "hola")

        await save_error_report(db, session, "error", "telegram")

        row = await db.execute(
            select(ErrorReport).where(ErrorReport.contractor_id == contractor.id)
        )
        report = row.scalar_one()
        assert len(report.context_json) == 1

    async def test_context_json_has_role_and_content(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await make_message(db, session, MessageRole.user, "hazme una factura")
        await make_message(db, session, MessageRole.assistant, "Factura generada.")

        await save_error_report(db, session, "incorrecto", "telegram")

        row = await db.execute(
            select(ErrorReport).where(ErrorReport.contractor_id == contractor.id)
        )
        context = row.scalar_one().context_json
        roles = {m["role"] for m in context}
        assert "user" in roles
        assert "assistant" in roles

    async def test_data_isolation(self, db: AsyncSession) -> None:
        contractor_a = await make_contractor(db)
        contractor_b = await make_contractor(db)
        session_a = await make_session(db, contractor_a)

        await save_error_report(db, session_a, "error de prueba", "telegram")

        row = await db.execute(
            select(ErrorReport).where(ErrorReport.contractor_id == contractor_b.id)
        )
        assert row.scalar_one_or_none() is None


class TestGetLastAssistantMessage:
    async def test_returns_most_recent_assistant_message(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        now = datetime.now(UTC)
        await make_message(db, session, MessageRole.user, "hola", created_at=now)
        await make_message(
            db, session, MessageRole.assistant, "Factura generada.",
            created_at=now + timedelta(seconds=1),
        )
        await make_message(
            db, session, MessageRole.user, "no",
            created_at=now + timedelta(seconds=2),
        )

        result = await get_last_assistant_message(db, session.id)

        assert result == "Factura generada."

    async def test_returns_none_when_no_assistant_messages(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        await make_message(db, session, MessageRole.user, "hola")

        result = await get_last_assistant_message(db, session.id)

        assert result is None

    async def test_returns_latest_when_multiple_assistant_messages(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        now = datetime.now(UTC)
        await make_message(
            db, session, MessageRole.assistant, "primera respuesta",
            created_at=now,
        )
        await make_message(
            db, session, MessageRole.assistant, "segunda respuesta",
            created_at=now + timedelta(seconds=1),
        )

        result = await get_last_assistant_message(db, session.id)

        assert result == "segunda respuesta"


class TestTryHandleErrorReport:
    async def test_two_turn_flow_saves_report_and_clears_pending(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor, context={"pending_error_report": True})
        send = AsyncMock()

        consumed = await _try_handle_error_report(
            db, session, "el importe está mal", "telegram", None, send, "111"
        )

        assert consumed is True
        row = await db.execute(
            select(ErrorReport).where(ErrorReport.contractor_id == contractor.id)
        )
        report = row.scalar_one()
        assert report.user_message == "el importe está mal"
        assert "pending_error_report" not in session.context
        send.assert_called_once()
        assert "anotado" in send.call_args[0][1].lower()

    async def test_client_session_not_handled(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor, user_type=UserType.client)
        send = AsyncMock()

        consumed = await _try_handle_error_report(
            db, session, "está mal", "telegram", None, send, "111"
        )

        assert consumed is False
        send.assert_not_called()
        row = await db.execute(
            select(ErrorReport).where(ErrorReport.contractor_id == contractor.id)
        )
        assert row.scalar_one_or_none() is None
