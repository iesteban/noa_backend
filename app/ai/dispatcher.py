from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import ConversationSession

logger = logging.getLogger(__name__)

# Registry: tool_name → async (tool_input, db, session) → str
_REGISTRY: dict[str, Callable[..., Coroutine[Any, Any, str]]] = {}


_Handler = Callable[..., Coroutine[Any, Any, str]]


def register(tool_name: str) -> Callable[[_Handler], _Handler]:
    """Decorator to register a function as the handler for a named tool."""
    def decorator(fn: _Handler) -> _Handler:
        _REGISTRY[tool_name] = fn
        return fn
    return decorator


async def dispatch_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    """Route a tool_use block to its handler and return a string result.

    Returns an error string (never raises) so the agentic loop can always
    pass a valid tool_result back to Claude.
    """
    handler = _REGISTRY.get(tool_name)
    if handler is None:
        logger.warning("No handler registered for tool %r", tool_name)
        return f"Tool '{tool_name}' is not yet implemented."
    try:
        return await handler(tool_input, db, session)
    except Exception:
        logger.exception("Tool %r raised an exception", tool_name)
        return f"Tool '{tool_name}' encountered an error. Please try again."
