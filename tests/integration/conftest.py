"""Integration test fixtures and helpers — uses a real PostgreSQL database.

Each test gets a fresh async engine bound to its own event loop (the only way
to reliably avoid "Future attached to a different loop" errors with asyncpg).
Schema is built once per session via alembic upgrade head, then torn down via
downgrade base so the test DB is always left clean.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from app.config import settings
from app.database import Base

# Import all models so Base.metadata is fully populated for the db fixture.
from app.models.client import Client
from app.models.contractor import Channel, Contractor
from app.models.job import Job  # noqa: F401 — registers table with Base.metadata
from app.models.session import ConversationSession, Message, MessageRole, UserType


def _make_engine():  # type: ignore[return]
    return create_async_engine(settings.database_url, echo=False)


def _alembic_cfg() -> Config:
    cfg = Config("alembic.ini")
    # alembic/env.py reads settings.database_url at runtime, so no override needed.
    return cfg


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    """Guarantee a clean schema before the session; tear it down after.

    1. stamp base  — syncs alembic_version with whatever is actually in the DB
    2. drop_all    — removes any leftover tables from a previous run
    3. upgrade head — builds the schema via real migrations
    4. downgrade base — tears it all down so the test DB is left empty

    Intentionally sync: alembic's command layer and asyncio.run() each create
    their own isolated event loop so they don't interfere with test loops.
    """
    async def _drop_all() -> None:
        engine = _make_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    command.stamp(_alembic_cfg(), "base")
    asyncio.run(_drop_all())
    command.upgrade(_alembic_cfg(), "head")
    yield  # type: ignore[misc]
    command.downgrade(_alembic_cfg(), "base")


@pytest.fixture
async def db(_schema: None) -> AsyncSession:  # type: ignore[misc]
    """Function-scoped async session, engine created fresh per test.

    Each test gets its own asyncpg connection bound to its own event loop.
    All inserts (flushed, not committed) are rolled back after the test,
    providing full isolation without touching the schema between tests.
    """
    engine = _make_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


# ---------------------------------------------------------------------------
# Object helpers — insert objects via flush() so they're visible within the
# session's transaction but automatically rolled back after the test.
# ---------------------------------------------------------------------------

async def make_contractor(db: AsyncSession, **overrides: object) -> Contractor:
    """Insert a Contractor and flush. Override any field via kwargs."""
    import uuid as _uuid
    defaults: dict[str, object] = {
        "phone_number": f"+346{_uuid.uuid4().hex[:8]}",
        "name": "Pedro García",
        "business_name": "Fontanería García",
        "nif": "12345678A",
        "iban": "ES91 2100 0418 4502 0005 1332",
        "iva_rate": 0.21,
        "irpf_rate": 0.15,
        "channel": Channel.telegram,
    }
    defaults.update(overrides)
    contractor = Contractor(**defaults)  # type: ignore[arg-type]
    db.add(contractor)
    await db.flush()
    return contractor


async def make_client(
    db: AsyncSession, contractor: Contractor, **overrides: object
) -> Client:
    """Insert a Client belonging to contractor and flush."""
    import uuid as _uuid
    defaults: dict[str, object] = {
        "contractor_id": contractor.id,
        "phone_number": f"+346{_uuid.uuid4().hex[:8]}",
        "name": "Ana López",
    }
    defaults.update(overrides)
    client = Client(**defaults)  # type: ignore[arg-type]
    db.add(client)
    await db.flush()
    return client


async def make_session(
    db: AsyncSession,
    contractor: Contractor,
    *,
    user_type: UserType = UserType.contractor,
    **overrides: object,
) -> ConversationSession:
    """Insert a ConversationSession and flush."""
    defaults: dict[str, object] = {
        "phone_number": contractor.phone_number,
        "channel": "telegram",
        "user_type": user_type,
        "contractor_id": contractor.id,
        "context": {},
        "last_active_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    session = ConversationSession(**defaults)  # type: ignore[arg-type]
    db.add(session)
    await db.flush()
    return session


async def make_message(
    db: AsyncSession,
    session: ConversationSession,
    role: MessageRole,
    content: str,
    *,
    created_at: datetime | None = None,
) -> Message:
    """Insert a Message and flush.

    Pass created_at explicitly when ordering matters — PostgreSQL's now()
    returns the transaction start time so all inserts in the same transaction
    would otherwise share the same timestamp.
    """
    msg = Message(session_id=session.id, role=role, content=content)
    if created_at is not None:
        msg.created_at = created_at
    db.add(msg)
    await db.flush()
    return msg
