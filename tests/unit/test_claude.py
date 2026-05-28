"""Unit tests for app.ai.claude — call_claude()."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.session import ConversationSession, UserType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _contractor(
    contractor_id: uuid.UUID | None = None,
    iva_rate: float = 0.21,
    irpf_rate: float = 0.15,
) -> MagicMock:
    c = MagicMock()
    c.id = contractor_id or uuid.uuid4()
    c.name = "Pedro García"
    c.business_name = "Fontanería García"
    c.nif = "12345678A"
    c.iban = None
    c.iva_rate = iva_rate
    c.irpf_rate = irpf_rate
    return c


def _session(
    user_type: UserType = UserType.contractor,
    contractor_id: uuid.UUID | None = None,
) -> MagicMock:
    s = MagicMock(spec=ConversationSession)
    s.id = uuid.uuid4()
    s.contractor_id = contractor_id or uuid.uuid4()
    s.user_type = user_type
    return s


def _text_block(text: str) -> MagicMock:
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _tool_use_block(name: str, input_: dict, tool_id: str = "tu_abc") -> MagicMock:  # type: ignore[type-arg]
    b = MagicMock()
    b.type = "tool_use"
    b.name = name
    b.input = input_
    b.id = tool_id
    return b


def _text_response(text: str) -> MagicMock:
    r = MagicMock()
    r.stop_reason = "end_turn"
    r.content = [_text_block(text)]
    return r


def _tool_response(name: str, input_: dict, tool_id: str = "tu_abc") -> MagicMock:  # type: ignore[type-arg]
    r = MagicMock()
    r.stop_reason = "tool_use"
    r.content = [_tool_use_block(name, input_, tool_id)]
    return r


def _empty_result() -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = []
    return r


def _db(contractor: MagicMock) -> AsyncMock:
    db = AsyncMock()
    db.get = AsyncMock(return_value=contractor)
    # build_contractor_context: scalar() = total client count,
    # execute() x3 = clients + working_hours + instructions
    # get_recent_messages: execute() = messages
    db.scalar.return_value = 0
    db.execute.side_effect = [
        _empty_result(),
        _empty_result(),
        _empty_result(),
        _empty_result(),
    ]
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTextResponse:
    @pytest.mark.asyncio
    async def test_returns_text_from_claude(self) -> None:
        cont = _contractor()
        db = _db(cont)
        session = _session(contractor_id=cont.id)

        mock_api = AsyncMock()
        reply = _text_response("Hola, ¿en qué puedo ayudarte?")
        mock_api.messages.create = AsyncMock(return_value=reply)

        with patch("app.ai.claude._make_client", return_value=mock_api):
            from app.ai.claude import call_claude
            result = await call_claude(db, session, "Hola")

        assert result == "Hola, ¿en qué puedo ayudarte?"

    @pytest.mark.asyncio
    async def test_calls_claude_with_user_message(self) -> None:
        cont = _contractor()
        db = _db(cont)
        session = _session(contractor_id=cont.id)

        mock_api = AsyncMock()
        mock_api.messages.create = AsyncMock(return_value=_text_response("ok"))

        with patch("app.ai.claude._make_client", return_value=mock_api):
            from app.ai.claude import call_claude
            await call_claude(db, session, "Mi mensaje")

        call_kwargs = mock_api.messages.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
        # The last message should be the user's current message
        last = messages[-1]
        assert last["role"] == "user"
        assert last["content"] == "Mi mensaje"


class TestMissingContractor:
    @pytest.mark.asyncio
    async def test_returns_fallback(self) -> None:
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        session = _session()

        from app.ai.claude import _FALLBACK, call_claude
        result = await call_claude(db, session, "test")

        assert result == _FALLBACK


class TestToolLoop:
    @pytest.mark.asyncio
    async def test_tool_call_then_text_returns_final_text(self) -> None:
        cont = _contractor()
        db = AsyncMock()
        db.get = AsyncMock(return_value=cont)
        db.scalar.return_value = 0
        db.execute.side_effect = [
            _empty_result(), _empty_result(), _empty_result(), _empty_result()
        ]

        session = _session(contractor_id=cont.id)

        tool_resp = _tool_response("search_client", {"query": "Pedro"})
        text_resp = _text_response("Encontré a Pedro Mejuto.")

        mock_api = AsyncMock()
        mock_api.messages.create = AsyncMock(side_effect=[tool_resp, text_resp])

        with (
            patch("app.ai.claude._make_client", return_value=mock_api),
            patch("app.ai.claude.dispatch_tool", new=AsyncMock(return_value="[Pedro Mejuto]")),
        ):
            from app.ai.claude import call_claude
            result = await call_claude(db, session, "Busca a Pedro")

        assert result == "Encontré a Pedro Mejuto."

    @pytest.mark.asyncio
    async def test_dispatch_tool_called_with_correct_args(self) -> None:
        cont = _contractor()
        db = AsyncMock()
        db.get = AsyncMock(return_value=cont)
        db.scalar.return_value = 0
        db.execute.side_effect = [
            _empty_result(), _empty_result(), _empty_result(), _empty_result()
        ]

        session = _session(contractor_id=cont.id)

        tool_resp = _tool_response("log_job", {"client_id": "abc", "amount": 80}, "tu_123")
        text_resp = _text_response("Trabajo guardado.")

        mock_api = AsyncMock()
        mock_api.messages.create = AsyncMock(side_effect=[tool_resp, text_resp])
        mock_dispatch = AsyncMock(return_value="ok")

        with (
            patch("app.ai.claude._make_client", return_value=mock_api),
            patch("app.ai.claude.dispatch_tool", new=mock_dispatch),
        ):
            from app.ai.claude import call_claude
            await call_claude(db, session, "Guarda el trabajo")

        mock_dispatch.assert_awaited_once_with(
            "log_job", {"client_id": "abc", "amount": 80}, db, session
        )

    @pytest.mark.asyncio
    async def test_max_rounds_returns_fallback(self) -> None:
        cont = _contractor()
        db = AsyncMock()
        db.get = AsyncMock(return_value=cont)
        db.scalar.return_value = 0
        db.execute.side_effect = [
            _empty_result(), _empty_result(), _empty_result(), _empty_result()
        ]

        session = _session(contractor_id=cont.id)

        # Always returns tool_use — never resolves
        mock_api = AsyncMock()
        mock_api.messages.create = AsyncMock(
            return_value=_tool_response("loop_tool", {})
        )

        with (
            patch("app.ai.claude._make_client", return_value=mock_api),
            patch("app.ai.claude.dispatch_tool", new=AsyncMock(return_value="ok")),
            patch("app.ai.claude._MAX_TOOL_ROUNDS", 2),
        ):
            from app.ai.claude import _FALLBACK, call_claude
            result = await call_claude(db, session, "test")

        assert result == _FALLBACK


class TestCacheStructure:
    @pytest.mark.asyncio
    async def test_system_has_two_blocks(self) -> None:
        cont = _contractor()
        db = _db(cont)
        session = _session(contractor_id=cont.id)

        mock_api = AsyncMock()
        mock_api.messages.create = AsyncMock(return_value=_text_response("ok"))

        with patch("app.ai.claude._make_client", return_value=mock_api):
            from app.ai.claude import call_claude
            await call_claude(db, session, "test")

        kwargs = mock_api.messages.create.call_args.kwargs
        system = kwargs["system"]
        assert len(system) == 2

    @pytest.mark.asyncio
    async def test_both_system_blocks_have_cache_control(self) -> None:
        cont = _contractor()
        db = _db(cont)
        session = _session(contractor_id=cont.id)

        mock_api = AsyncMock()
        mock_api.messages.create = AsyncMock(return_value=_text_response("ok"))

        with patch("app.ai.claude._make_client", return_value=mock_api):
            from app.ai.claude import call_claude
            await call_claude(db, session, "test")

        kwargs = mock_api.messages.create.call_args.kwargs
        for block in kwargs["system"]:
            assert block.get("cache_control") == {"type": "ephemeral"}

    @pytest.mark.asyncio
    async def test_model_comes_from_settings(self) -> None:
        cont = _contractor()
        db = _db(cont)
        session = _session(contractor_id=cont.id)

        mock_api = AsyncMock()
        mock_api.messages.create = AsyncMock(return_value=_text_response("ok"))

        with (
            patch("app.ai.claude._make_client", return_value=mock_api),
            patch("app.ai.claude.settings.claude_model", "claude-test-model-123"),
        ):
            from app.ai.claude import call_claude
            await call_claude(db, session, "test")

        kwargs = mock_api.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-test-model-123"

    @pytest.mark.asyncio
    async def test_default_model_is_haiku(self) -> None:
        from app.config import settings
        assert settings.claude_model == "claude-haiku-4-5-20251001"
