from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import ConversationSession, Message, MessageRole
from app.services.routing import RoutingResult

_SESSION_TTL_HOURS = 4


async def get_or_create_session(
    db: AsyncSession,
    session_key: str,
    channel: str,
    routing: RoutingResult,
) -> ConversationSession:
    """Return an active session for session_key+channel, or create a new one.

    session_key is str(telegram_chat_id) for Telegram, phone_number for WhatsApp.
    Sessions idle for more than SESSION_TTL_HOURS are treated as expired.
    routing.user_type and routing.contractor_id must not be None when called.
    """
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=_SESSION_TTL_HOURS)

    row = await db.execute(
        select(ConversationSession)
        .where(
            ConversationSession.phone_number == session_key,
            ConversationSession.channel == channel,
            ConversationSession.last_active_at >= cutoff,
        )
        .order_by(ConversationSession.last_active_at.desc())
        .limit(1)
    )
    session = row.scalar_one_or_none()

    if session is not None:
        session.last_active_at = now
        await db.commit()
        await db.refresh(session)
        return session

    assert routing.user_type is not None, "Cannot create a session for an unrouted user"
    assert routing.contractor_id is not None, "contractor_id is required to create a session"

    session = ConversationSession(
        phone_number=session_key,
        channel=channel,
        user_type=routing.user_type,
        contractor_id=routing.contractor_id,
        client_id=routing.client_id,
        context={},
        last_active_at=now,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def append_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    role: MessageRole,
    content: str,
    media_url: str | None = None,
    external_id: str | None = None,
) -> Message:
    message = Message(
        session_id=session_id,
        role=role,
        content=content,
        media_url=media_url,
        external_id=external_id,
    )
    db.add(message)
    await db.commit()
    return message
