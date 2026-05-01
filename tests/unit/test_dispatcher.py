"""Unit tests for app.ai.dispatcher — dispatch_tool()."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.dispatcher import _REGISTRY, dispatch_tool, register


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Isolate each test from side-effects on the global registry."""
    original = dict(_REGISTRY)
    yield
    _REGISTRY.clear()
    _REGISTRY.update(original)


def _session() -> MagicMock:
    s = MagicMock()
    s.id = uuid.uuid4()
    return s


class TestUnknownTool:
    @pytest.mark.asyncio
    async def test_returns_error_string(self) -> None:
        db = AsyncMock()
        result = await dispatch_tool("nonexistent_tool", {}, db, _session())
        assert "nonexistent_tool" in result

    @pytest.mark.asyncio
    async def test_does_not_raise(self) -> None:
        db = AsyncMock()
        # Must not raise — always returns a string
        result = await dispatch_tool("nonexistent_tool", {}, db, _session())
        assert isinstance(result, str)


class TestRegisteredTool:
    @pytest.mark.asyncio
    async def test_calls_handler(self) -> None:
        handler = AsyncMock(return_value="ok")
        _REGISTRY["test_tool"] = handler
        db = AsyncMock()
        session = _session()

        await dispatch_tool("test_tool", {"key": "val"}, db, session)

        handler.assert_awaited_once_with({"key": "val"}, db, session)

    @pytest.mark.asyncio
    async def test_returns_handler_result(self) -> None:
        _REGISTRY["test_tool"] = AsyncMock(return_value="handler result")
        result = await dispatch_tool("test_tool", {}, AsyncMock(), _session())
        assert result == "handler result"

    @pytest.mark.asyncio
    async def test_handler_exception_returns_error_string(self) -> None:
        async def _failing(*_: object, **__: object) -> str:
            raise RuntimeError("boom")

        _REGISTRY["boom_tool"] = _failing
        result = await dispatch_tool("boom_tool", {}, AsyncMock(), _session())
        assert "boom_tool" in result
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_raise(self) -> None:
        async def _failing(*_: object, **__: object) -> str:
            raise ValueError("unexpected")

        _REGISTRY["err_tool"] = _failing
        # Must not propagate — always returns a string
        result = await dispatch_tool("err_tool", {}, AsyncMock(), _session())
        assert isinstance(result, str)


class TestRegisterDecorator:
    def test_decorator_adds_to_registry(self) -> None:
        @register("my_tool")
        async def handler(tool_input: dict, db: object, session: object) -> str:  # type: ignore[type-arg]
            return "done"

        assert "my_tool" in _REGISTRY
        assert _REGISTRY["my_tool"] is handler

    def test_decorator_returns_original_function(self) -> None:
        @register("my_other_tool")
        async def handler(tool_input: dict, db: object, session: object) -> str:  # type: ignore[type-arg]
            return "done"

        assert callable(handler)
