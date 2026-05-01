"""Unit tests for app.services.session."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.session import ConversationSession, MessageRole, UserType
from app.services.routing import RoutingResult
from app.services.session import append_message, get_or_create_session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _routing(
    user_type: UserType = UserType.contractor,
    contractor_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
) -> RoutingResult:
    return RoutingResult(
        user_type=user_type,
        contractor_id=contractor_id or uuid.uuid4(),
        client_id=client_id,
        candidates=[],
    )


def _db() -> MagicMock:
    """A mock AsyncSession with sync add() and async execute/commit/refresh."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _active_session(session_key: str = "111", channel: str = "telegram") -> ConversationSession:
    s = MagicMock(spec=ConversationSession)
    s.id = uuid.uuid4()
    s.phone_number = session_key
    s.channel = channel
    s.last_active_at = datetime.now(UTC) - timedelta(minutes=10)
    return s


def _scalar_result(value: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


# ---------------------------------------------------------------------------
# get_or_create_session — existing active session
# ---------------------------------------------------------------------------

class TestResumeExistingSession:
    @pytest.mark.asyncio
    async def test_returns_existing_session(self) -> None:
        db = _db()
        existing = _active_session()
        db.execute.return_value = _scalar_result(existing)

        result = await get_or_create_session(db, "111", "telegram", _routing())

        assert result is existing

    @pytest.mark.asyncio
    async def test_updates_last_active_at(self) -> None:
        db = _db()
        existing = _active_session()
        before = existing.last_active_at
        db.execute.return_value = _scalar_result(existing)

        await get_or_create_session(db, "111", "telegram", _routing())

        assert existing.last_active_at > before

    @pytest.mark.asyncio
    async def test_commits_on_resume(self) -> None:
        db = _db()
        db.execute.return_value = _scalar_result(_active_session())

        await get_or_create_session(db, "111", "telegram", _routing())

        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_add_new_row_on_resume(self) -> None:
        db = _db()
        db.execute.return_value = _scalar_result(_active_session())

        await get_or_create_session(db, "111", "telegram", _routing())

        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# get_or_create_session — no active session → create new
# ---------------------------------------------------------------------------

class TestCreateNewSession:
    @pytest.mark.asyncio
    async def test_creates_session_when_none_found(self) -> None:
        db = _db()
        db.execute.return_value = _scalar_result(None)

        await get_or_create_session(db, "222", "telegram", _routing())

        db.add.assert_called_once()
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_new_session_has_correct_channel(self) -> None:
        db = _db()
        db.execute.return_value = _scalar_result(None)
        routing = _routing()

        await get_or_create_session(db, "222", "telegram", routing)

        added = db.add.call_args[0][0]
        assert added.channel == "telegram"

    @pytest.mark.asyncio
    async def test_new_session_has_correct_user_type(self) -> None:
        db = _db()
        db.execute.return_value = _scalar_result(None)
        routing = _routing(user_type=UserType.client)

        await get_or_create_session(db, "222", "telegram", routing)

        added = db.add.call_args[0][0]
        assert added.user_type == UserType.client

    @pytest.mark.asyncio
    async def test_new_session_has_correct_contractor_id(self) -> None:
        db = _db()
        db.execute.return_value = _scalar_result(None)
        cid = uuid.uuid4()
        routing = _routing(contractor_id=cid)

        await get_or_create_session(db, "222", "telegram", routing)

        added = db.add.call_args[0][0]
        assert added.contractor_id == cid

    @pytest.mark.asyncio
    async def test_new_session_has_correct_session_key(self) -> None:
        db = _db()
        db.execute.return_value = _scalar_result(None)

        await get_or_create_session(db, "333", "telegram", _routing())

        added = db.add.call_args[0][0]
        assert added.phone_number == "333"

    @pytest.mark.asyncio
    async def test_new_session_sets_client_id_for_client_routing(self) -> None:
        db = _db()
        db.execute.return_value = _scalar_result(None)
        client_id = uuid.uuid4()
        routing = _routing(user_type=UserType.client, client_id=client_id)

        await get_or_create_session(db, "222", "telegram", routing)

        added = db.add.call_args[0][0]
        assert added.client_id == client_id


# ---------------------------------------------------------------------------
# append_message
# ---------------------------------------------------------------------------

class TestAppendMessage:
    @pytest.mark.asyncio
    async def test_adds_message_to_db(self) -> None:
        db = _db()
        session_id = uuid.uuid4()

        await append_message(db, session_id, MessageRole.user, "Hola Noa")

        db.add.assert_called_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_message_has_correct_role(self) -> None:
        db = _db()

        await append_message(db, uuid.uuid4(), MessageRole.assistant, "Hola!")

        added = db.add.call_args[0][0]
        assert added.role == MessageRole.assistant

    @pytest.mark.asyncio
    async def test_message_has_correct_content(self) -> None:
        db = _db()

        await append_message(db, uuid.uuid4(), MessageRole.user, "Estuve 2 horas en casa de Pedro")

        added = db.add.call_args[0][0]
        assert added.content == "Estuve 2 horas en casa de Pedro"

    @pytest.mark.asyncio
    async def test_message_has_correct_session_id(self) -> None:
        db = _db()
        sid = uuid.uuid4()

        await append_message(db, sid, MessageRole.user, "hi")

        added = db.add.call_args[0][0]
        assert added.session_id == sid

    @pytest.mark.asyncio
    async def test_message_media_url_optional(self) -> None:
        db = _db()

        await append_message(db, uuid.uuid4(), MessageRole.user, "hi")

        added = db.add.call_args[0][0]
        assert added.media_url is None

    @pytest.mark.asyncio
    async def test_message_media_url_stored(self) -> None:
        db = _db()

        await append_message(
            db, uuid.uuid4(), MessageRole.user, "nota de voz", media_url="https://cdn/voice.ogg"
        )

        added = db.add.call_args[0][0]
        assert added.media_url == "https://cdn/voice.ogg"
