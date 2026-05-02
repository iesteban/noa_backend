"""Integration tests for dispatch_tool() — real PostgreSQL session passed through."""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dispatcher import _REGISTRY, dispatch_tool, register
from app.models.contractor import Contractor
from app.models.session import UserType
from tests.integration.conftest import make_contractor, make_session


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Restore the global registry after each test."""
    original = dict(_REGISTRY)
    yield  # type: ignore[misc]
    _REGISTRY.clear()
    _REGISTRY.update(original)


class TestUnknownTool:
    async def test_returns_error_string(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        result = await dispatch_tool("nonexistent_tool", {}, db, session)
        assert "nonexistent_tool" in result

    async def test_does_not_raise(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        session = await make_session(db, contractor)
        result = await dispatch_tool("ghost_tool", {}, db, session)
        assert isinstance(result, str)


class TestHandlerWithRealDb:
    async def test_handler_receives_real_async_session(self, db: AsyncSession) -> None:
        """Handler arg is a live AsyncSession, not a mock."""
        received: list[str] = []

        @register("check_type")
        async def handler(
            tool_input: dict,  # type: ignore[type-arg]
            db_arg: AsyncSession,
            session: object,
        ) -> str:
            received.append(type(db_arg).__name__)
            return "ok"

        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)
        await dispatch_tool("check_type", {}, db, conv_session)

        assert received == ["AsyncSession"]

    async def test_handler_can_query_real_data(self, db: AsyncSession) -> None:
        """Handler successfully reads a contractor inserted in the same transaction."""
        contractor = await make_contractor(db, name="Plumber Int")
        found: list[str] = []

        @register("read_contractor")
        async def handler(
            tool_input: dict,  # type: ignore[type-arg]
            db_arg: AsyncSession,
            session: object,
        ) -> str:
            row = await db_arg.execute(
                select(Contractor).where(Contractor.name == "Plumber Int")
            )
            c = row.scalar_one_or_none()
            if c:
                found.append(c.name)
            return "done"

        conv_session = await make_session(db, contractor)
        await dispatch_tool("read_contractor", {}, db, conv_session)

        assert found == ["Plumber Int"]

    async def test_handler_receives_correct_session_id(self, db: AsyncSession) -> None:
        """The ConversationSession forwarded to the handler matches the one from the DB."""
        received_ids: list[object] = []

        @register("record_session_id")
        async def handler(
            tool_input: dict,  # type: ignore[type-arg]
            db_arg: AsyncSession,
            session: object,
        ) -> str:
            received_ids.append(getattr(session, "id", None))
            return "ok"

        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)
        await dispatch_tool("record_session_id", {}, db, conv_session)

        assert received_ids[0] == conv_session.id

    async def test_handler_tool_input_passed_correctly(self, db: AsyncSession) -> None:
        received_inputs: list[dict] = []  # type: ignore[type-arg]

        @register("echo_input")
        async def handler(
            tool_input: dict,  # type: ignore[type-arg]
            db_arg: AsyncSession,
            session: object,
        ) -> str:
            received_inputs.append(dict(tool_input))
            return "echoed"

        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)
        await dispatch_tool("echo_input", {"amount": 120, "client_id": "abc"}, db, conv_session)

        assert received_inputs == [{"amount": 120, "client_id": "abc"}]

    async def test_handler_exception_returns_error_string(self, db: AsyncSession) -> None:
        @register("exploding_tool")
        async def handler(
            tool_input: dict,  # type: ignore[type-arg]
            db_arg: AsyncSession,
            session: object,
        ) -> str:
            raise RuntimeError("DB constraint violated")

        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)
        result = await dispatch_tool("exploding_tool", {}, db, conv_session)

        assert "exploding_tool" in result
        assert isinstance(result, str)

    async def test_handler_exception_does_not_raise(self, db: AsyncSession) -> None:
        @register("silent_fail")
        async def handler(
            tool_input: dict,  # type: ignore[type-arg]
            db_arg: AsyncSession,
            session: object,
        ) -> str:
            raise ValueError("unexpected state")

        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)
        # Must not propagate — always returns a string
        result = await dispatch_tool("silent_fail", {}, db, conv_session)
        assert isinstance(result, str)

    async def test_two_tools_dispatched_in_sequence(self, db: AsyncSession) -> None:
        calls: list[str] = []

        @register("first_tool")
        async def first(
            tool_input: dict,  # type: ignore[type-arg]
            db_arg: AsyncSession,
            session: object,
        ) -> str:
            calls.append("first")
            return "first_result"

        @register("second_tool")
        async def second(
            tool_input: dict,  # type: ignore[type-arg]
            db_arg: AsyncSession,
            session: object,
        ) -> str:
            calls.append("second")
            return "second_result"

        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)

        r1 = await dispatch_tool("first_tool", {}, db, conv_session)
        r2 = await dispatch_tool("second_tool", {}, db, conv_session)

        assert calls == ["first", "second"]
        assert r1 == "first_result"
        assert r2 == "second_result"

    async def test_client_mode_session_forwarded(self, db: AsyncSession) -> None:
        """Handler also works when the session is client-mode (user_type=client)."""
        received_user_types: list[str] = []

        @register("check_user_type")
        async def handler(
            tool_input: dict,  # type: ignore[type-arg]
            db_arg: AsyncSession,
            session: object,
        ) -> str:
            received_user_types.append(str(getattr(session, "user_type", "")))
            return "ok"

        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor, user_type=UserType.client)
        await dispatch_tool("check_user_type", {}, db, conv_session)

        assert "client" in received_user_types[0]
