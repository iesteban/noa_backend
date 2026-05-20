from __future__ import annotations

import re
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.error_report import ErrorReport, Platform
from app.models.session import ConversationSession, Message, MessageRole

_ERROR_KEYWORDS = [
    "error",
    "esta mal",
    "incorrecto",
    "falla",
    "no funciona",
    "eso no es asi",
    "te has equivocado",
    "esta equivocado",
]

_COMMANDS = frozenset({"/error", "/reporte"})

_CONTEXT_LIMIT = 5

_ACK: dict[str, str] = {
    "es": "Gracias, lo hemos anotado. Seguiremos mejorando.",
    "en": "Thanks, we've noted it. We'll keep improving.",
}
_ASK: dict[str, str] = {
    "es": "¿Qué ha salido mal? Descríbelo brevemente.",
    "en": "What went wrong? Please describe it briefly.",
}


def _normalize(text: str) -> str:
    """Lowercase, strip combining accents, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", text)
    base = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", base).strip()


def detect_language(text: str) -> str:
    """Return 'es' if text appears Spanish, 'en' otherwise."""
    if any(c in "áéíóúñüàèìòù" for c in text.lower()):
        return "es"
    normalized = _normalize(text)
    if any(kw in normalized for kw in _ERROR_KEYWORDS):
        return "es"
    return "en"


def detect_error_intent(
    text: str,
) -> tuple[bool, str | None]:
    """Return (is_error_intent, description).

    description is the inline problem text if provided, or None (need to ask).
    """
    stripped = text.strip()
    stripped_lower = stripped.lower()
    normalized = _normalize(stripped)

    # Explicit commands: /error, /reporte
    if stripped_lower in _COMMANDS:
        return True, None
    for cmd in _COMMANDS:
        if stripped_lower.startswith(cmd + " "):
            rest = stripped[len(cmd):].strip()
            return True, rest or None

    # Keyword match (word-boundary, accent-insensitive).
    for kw in _ERROR_KEYWORDS:
        pattern = r"\b" + re.escape(kw) + r"\b"
        if re.search(pattern, normalized):
            return True, stripped if normalized != kw else None

    return False, None


async def get_last_assistant_message(
    db: AsyncSession, session_id: uuid.UUID
) -> str | None:
    """Return the most recent assistant message content, or None."""
    row = await db.execute(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.role == MessageRole.assistant,
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    msg = row.scalar_one_or_none()
    return msg.content if msg else None


async def save_error_report(
    db: AsyncSession,
    session: ConversationSession,
    user_message: str,
    channel: str,
) -> ErrorReport:
    """Save an ErrorReport with the last _CONTEXT_LIMIT messages as context."""
    rows = await db.execute(
        select(Message)
        .where(Message.session_id == session.id)
        .order_by(Message.created_at.desc())
        .limit(_CONTEXT_LIMIT)
    )
    context_messages = list(reversed(rows.scalars().all()))
    context_json = [
        {"role": m.role.value, "content": m.content} for m in context_messages
    ]
    report = ErrorReport(
        contractor_id=session.contractor_id,
        platform=Platform(channel),
        user_message=user_message,
        context_json=context_json,
    )
    db.add(report)
    await db.commit()
    return report


def ack_message(lang: str) -> str:
    return _ACK.get(lang, _ACK["es"])


def ask_message(lang: str) -> str:
    return _ASK.get(lang, _ASK["es"])
