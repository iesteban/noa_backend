from __future__ import annotations

import logging
import uuid
from typing import Any

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import build_contractor_context
from app.ai.dispatcher import dispatch_tool
from app.ai.prompts import CLIENT_INSTRUCTIONS, CONTRACTOR_INSTRUCTIONS
from app.ai.tools import CLIENT_TOOLS, CONTRACTOR_TOOLS
from app.config import settings
from app.models.contractor import Contractor
from app.models.session import ConversationSession, Message, UserType

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 2048
_HISTORY_LIMIT = 20
_MAX_TOOL_ROUNDS = 5
_FALLBACK = "Lo siento, ha ocurrido un error inesperado. Por favor, inténtalo de nuevo."


def _make_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def get_recent_messages(
    db: AsyncSession, session_id: uuid.UUID
) -> list[dict[str, str]]:
    """Return the last _HISTORY_LIMIT messages as Anthropic message dicts (oldest first)."""
    rows = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(_HISTORY_LIMIT)
    )
    messages = list(reversed(rows.scalars().all()))
    return [{"role": m.role.value, "content": m.content} for m in messages if m.content]


async def call_claude(
    db: AsyncSession,
    session: ConversationSession,
    current_message: str,
) -> str:
    """Assemble the 4-layer request and run the agentic tool loop.

    Layers:
      1 — Core instructions        (system[0], cached)
      2 — Tool definitions         (tools list, cached on last entry)
      3 — Contractor context       (system[1], cached)
      4 — Conversation history     (messages, not cached)

    Runs the tool loop until Claude produces a text response or
    _MAX_TOOL_ROUNDS is exhausted, then returns the final text.
    """
    contractor = await db.get(Contractor, session.contractor_id)
    if contractor is None:
        logger.error(
            "Contractor %s not found for session %s", session.contractor_id, session.id
        )
        return _FALLBACK

    is_contractor = session.user_type == UserType.contractor

    if is_contractor:
        layer1 = CONTRACTOR_INSTRUCTIONS
        layer3 = await build_contractor_context(db, contractor)
        tools: list[dict[str, Any]] = CONTRACTOR_TOOLS
    else:
        layer1 = CLIENT_INSTRUCTIONS.format(
            business_name=contractor.business_name or contractor.name
        )
        layer3 = ""
        tools = CLIENT_TOOLS

    system: list[dict[str, Any]] = [
        {"type": "text", "text": layer1, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": layer3, "cache_control": {"type": "ephemeral"}},
    ]

    history = await get_recent_messages(db, session.id)
    messages: list[Any] = [*history, {"role": "user", "content": current_message}]

    client = _make_client()

    for _ in range(_MAX_TOOL_ROUNDS):
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=system,  # type: ignore[arg-type]
            tools=tools,  # type: ignore[arg-type]
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            return next(
                (block.text for block in response.content if block.type == "text"), ""
            )

        if response.stop_reason == "tool_use":
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await dispatch_tool(block.name, block.input, db, session)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            logger.warning("Unexpected stop_reason=%r from Claude", response.stop_reason)
            break

    return _FALLBACK
