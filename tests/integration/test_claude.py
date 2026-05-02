"""Integration tests for call_claude() — real PostgreSQL, mocked Anthropic API.

These tests verify that call_claude correctly assembles DB data into the API
request. The Anthropic client is always mocked — no real API calls are made.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.claude import _FALLBACK, _HISTORY_LIMIT, call_claude
from app.ai.prompts import CLIENT_INSTRUCTIONS, CONTRACTOR_INSTRUCTIONS
from app.models.session import ConversationSession, MessageRole, UserType
from tests.integration.conftest import (
    make_client,
    make_contractor,
    make_message,
    make_session,
)

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _text_block(text: str) -> MagicMock:
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _tool_block(name: str, input_: dict, tool_id: str = "tu_abc") -> MagicMock:  # type: ignore[type-arg]
    b = MagicMock()
    b.type = "tool_use"
    b.name = name
    b.input = input_
    b.id = tool_id
    return b


def _text_response(text: str = "Respuesta de Claude.") -> MagicMock:
    r = MagicMock()
    r.stop_reason = "end_turn"
    r.content = [_text_block(text)]
    return r


def _tool_response(
    name: str = "search_client",
    input_: dict | None = None,  # type: ignore[type-arg]
    tool_id: str = "tu_abc",
) -> MagicMock:
    r = MagicMock()
    r.stop_reason = "tool_use"
    r.content = [_tool_block(name, input_ or {}, tool_id)]
    return r


def _mock_api(
    side_effect: list[MagicMock] | None = None,
    return_value: MagicMock | None = None,
) -> AsyncMock:
    api = AsyncMock()
    if side_effect is not None:
        api.messages.create = AsyncMock(side_effect=side_effect)
    else:
        api.messages.create = AsyncMock(return_value=return_value or _text_response())
    return api


# ---------------------------------------------------------------------------
# Missing contractor
# ---------------------------------------------------------------------------

class TestMissingContractor:
    async def test_returns_fallback_when_contractor_not_found(
        self, db: AsyncSession
    ) -> None:
        """session.contractor_id points to a non-existent row → fallback."""
        import uuid
        # Detached object — never inserted into the DB, so contractor_id
        # references nothing and db.get(Contractor, ...) returns None.
        conv_session = ConversationSession(
            id=uuid.uuid4(),
            phone_number="+34600000000",
            channel="telegram",
            user_type=UserType.contractor,
            contractor_id=uuid.uuid4(),
            context={},
            last_active_at=datetime.now(UTC),
        )

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            result = await call_claude(db, conv_session, "Hola")

        assert result == _FALLBACK
        api.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# System prompt — real contractor data
# ---------------------------------------------------------------------------

class TestSystemPromptContent:
    async def test_contractor_name_in_layer3(self, db: AsyncSession) -> None:
        """Real contractor name from DB appears in system[1] (Layer 3)."""
        contractor = await make_contractor(db, name="Electricista Rodríguez")
        conv_session = await make_session(db, contractor)

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            await call_claude(db, conv_session, "test")

        system = api.messages.create.call_args.kwargs["system"]
        assert "Electricista Rodríguez" in system[1]["text"]

    async def test_contractor_nif_in_layer3(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db, nif="99887766C")
        conv_session = await make_session(db, contractor)

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            await call_claude(db, conv_session, "test")

        system = api.messages.create.call_args.kwargs["system"]
        assert "99887766C" in system[1]["text"]

    async def test_client_name_in_layer3(self, db: AsyncSession) -> None:
        """Real client names from DB appear in the context (Layer 3)."""
        contractor = await make_contractor(db)
        await make_client(db, contractor, name="Fermín Castillo")
        conv_session = await make_session(db, contractor)

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            await call_claude(db, conv_session, "test")

        system = api.messages.create.call_args.kwargs["system"]
        assert "Fermín Castillo" in system[1]["text"]

    async def test_other_contractor_clients_absent_from_layer3(
        self, db: AsyncSession
    ) -> None:
        """Data isolation: only THIS contractor's clients appear in Layer 3."""
        contractor_a = await make_contractor(db)
        contractor_b = await make_contractor(db)
        await make_client(db, contractor_b, name="Cliente Ajeno")
        conv_session = await make_session(db, contractor_a)

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            await call_claude(db, conv_session, "test")

        system = api.messages.create.call_args.kwargs["system"]
        assert "Cliente Ajeno" not in system[1]["text"]

    async def test_contractor_mode_uses_contractor_instructions(
        self, db: AsyncSession
    ) -> None:
        """Contractor sessions use CONTRACTOR_INSTRUCTIONS as Layer 1."""
        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor, user_type=UserType.contractor)

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            await call_claude(db, conv_session, "test")

        system = api.messages.create.call_args.kwargs["system"]
        assert system[0]["text"] == CONTRACTOR_INSTRUCTIONS

    async def test_client_mode_uses_business_name_in_layer1(
        self, db: AsyncSession
    ) -> None:
        """Client sessions embed the contractor's business_name in Layer 1."""
        contractor = await make_contractor(db, business_name="Carpintería Ruiz")
        conv_session = await make_session(db, contractor, user_type=UserType.client)

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            await call_claude(db, conv_session, "Hola")

        system = api.messages.create.call_args.kwargs["system"]
        assert "Carpintería Ruiz" in system[0]["text"]
        expected = CLIENT_INSTRUCTIONS.format(business_name="Carpintería Ruiz")
        assert system[0]["text"] == expected

    async def test_client_mode_falls_back_to_name_when_no_business_name(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db, name="Sola Autónoma", business_name=None)
        conv_session = await make_session(db, contractor, user_type=UserType.client)

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            await call_claude(db, conv_session, "Hola")

        system = api.messages.create.call_args.kwargs["system"]
        assert "Sola Autónoma" in system[0]["text"]

    async def test_system_always_has_two_blocks(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            await call_claude(db, conv_session, "test")

        system = api.messages.create.call_args.kwargs["system"]
        assert len(system) == 2

    async def test_both_system_blocks_have_cache_control(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            await call_claude(db, conv_session, "test")

        system = api.messages.create.call_args.kwargs["system"]
        for block in system:
            assert block.get("cache_control") == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# Message history from DB
# ---------------------------------------------------------------------------

class TestMessageHistory:
    async def test_no_prior_messages_sends_only_current(
        self, db: AsyncSession
    ) -> None:
        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)
        # No messages in DB for this session

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            await call_claude(db, conv_session, "Primer mensaje")

        messages = api.messages.create.call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0] == {"role": "user", "content": "Primer mensaje"}

    async def test_prior_messages_appear_in_api_call(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)
        base = datetime(2025, 6, 1, 10, 0, 0, tzinfo=UTC)
        await make_message(db, conv_session, MessageRole.user, "Hola", created_at=base)
        await make_message(
            db, conv_session, MessageRole.assistant, "¿En qué te ayudo?",
            created_at=base + timedelta(seconds=1),
        )

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            await call_claude(db, conv_session, "Dime algo")

        messages = api.messages.create.call_args.kwargs["messages"]
        # history (2) + current (1)
        assert len(messages) == 3
        assert messages[0] == {"role": "user", "content": "Hola"}
        assert messages[1] == {"role": "assistant", "content": "¿En qué te ayudo?"}
        assert messages[2] == {"role": "user", "content": "Dime algo"}

    async def test_history_oldest_first_ordering(self, db: AsyncSession) -> None:
        """Messages are returned oldest-first, matching the Anthropic format."""
        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)
        base = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        for i in range(5):
            role = MessageRole.user if i % 2 == 0 else MessageRole.assistant
            await make_message(
                db, conv_session, role, f"msg_{i}",
                created_at=base + timedelta(seconds=i),
            )

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            await call_claude(db, conv_session, "current")

        messages = api.messages.create.call_args.kwargs["messages"]
        history = messages[:-1]  # exclude the current message
        contents = [m["content"] for m in history]
        assert contents == ["msg_0", "msg_1", "msg_2", "msg_3", "msg_4"]

    async def test_history_capped_at_limit(self, db: AsyncSession) -> None:
        """Only the most recent _HISTORY_LIMIT messages are included."""
        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)
        base = datetime(2025, 6, 1, 8, 0, 0, tzinfo=UTC)
        total = _HISTORY_LIMIT + 5  # 25 messages

        for i in range(total):
            role = MessageRole.user if i % 2 == 0 else MessageRole.assistant
            await make_message(
                db, conv_session, role, f"msg_{i}",
                created_at=base + timedelta(seconds=i),
            )

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            await call_claude(db, conv_session, "current")

        messages = api.messages.create.call_args.kwargs["messages"]
        history = messages[:-1]
        assert len(history) == _HISTORY_LIMIT
        # The 5 oldest messages are cut; the window starts at msg_5
        contents = [m["content"] for m in history]
        assert "msg_0" not in contents
        assert "msg_4" not in contents
        assert contents[0] == "msg_5"
        assert contents[-1] == f"msg_{total - 1}"

    async def test_messages_from_other_session_excluded(
        self, db: AsyncSession
    ) -> None:
        """Messages belonging to a different session do not appear in the call."""
        contractor = await make_contractor(db)
        session_a = await make_session(db, contractor)
        session_b = await make_session(db, contractor)
        base = datetime(2025, 6, 1, 9, 0, 0, tzinfo=UTC)
        await make_message(db, session_b, MessageRole.user, "otro_msg", created_at=base)

        api = _mock_api(return_value=_text_response())
        with patch("app.ai.claude._make_client", return_value=api):
            await call_claude(db, session_a, "current")

        messages = api.messages.create.call_args.kwargs["messages"]
        contents = [m["content"] for m in messages]
        assert "otro_msg" not in contents


# ---------------------------------------------------------------------------
# Agentic tool loop
# ---------------------------------------------------------------------------

class TestToolLoop:
    async def test_tool_then_text_returns_final_text(self, db: AsyncSession) -> None:
        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)

        api = _mock_api(side_effect=[
            _tool_response("search_client", {"query": "Ana"}),
            _text_response("Encontré a Ana López."),
        ])

        with (
            patch("app.ai.claude._make_client", return_value=api),
            patch("app.ai.claude.dispatch_tool", new=AsyncMock(return_value="[Ana López]")),
        ):
            result = await call_claude(db, conv_session, "Busca a Ana")

        assert result == "Encontré a Ana López."

    async def test_dispatch_tool_called_with_real_db_and_session(
        self, db: AsyncSession
    ) -> None:
        """dispatch_tool receives the real db session and ConversationSession."""
        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)

        api = _mock_api(side_effect=[
            _tool_response("log_job", {"amount": 80}, "tu_xyz"),
            _text_response("Guardado."),
        ])
        mock_dispatch = AsyncMock(return_value="ok")

        with (
            patch("app.ai.claude._make_client", return_value=api),
            patch("app.ai.claude.dispatch_tool", new=mock_dispatch),
        ):
            await call_claude(db, conv_session, "Guarda")

        mock_dispatch.assert_awaited_once_with("log_job", {"amount": 80}, db, conv_session)

    async def test_tool_result_fed_back_to_next_api_call(
        self, db: AsyncSession
    ) -> None:
        """After a tool call, the tool_result block is appended to messages."""
        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)

        api = _mock_api(side_effect=[
            _tool_response("search_client", {"query": "Pedro"}, "tu_001"),
            _text_response("Listo."),
        ])

        with (
            patch("app.ai.claude._make_client", return_value=api),
            patch("app.ai.claude.dispatch_tool", new=AsyncMock(return_value="[Pedro Ruiz]")),
        ):
            await call_claude(db, conv_session, "Busca a Pedro")

        # Second call receives the tool_result in the messages list
        second_call_messages = api.messages.create.call_args_list[1].kwargs["messages"]
        # The second-to-last entry is the assistant turn with tool_use
        # The last entry is the user turn with tool_result
        last_user_msg = second_call_messages[-1]
        assert last_user_msg["role"] == "user"
        tool_results = last_user_msg["content"]
        assert any(
            r.get("type") == "tool_result" and r.get("tool_use_id") == "tu_001"
            for r in tool_results
        )

    async def test_max_rounds_returns_fallback(self, db: AsyncSession) -> None:
        """Infinite tool loop is capped at _MAX_TOOL_ROUNDS and returns fallback."""
        contractor = await make_contractor(db)
        conv_session = await make_session(db, contractor)

        api = _mock_api(return_value=_tool_response("loop_forever", {}))

        with (
            patch("app.ai.claude._make_client", return_value=api),
            patch("app.ai.claude.dispatch_tool", new=AsyncMock(return_value="ok")),
            patch("app.ai.claude._MAX_TOOL_ROUNDS", 3),
        ):
            result = await call_claude(db, conv_session, "test")

        assert result == _FALLBACK
        assert api.messages.create.call_count == 3
