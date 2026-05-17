"""Integration tests for migration 0008.

Verifies that upgrade adds is_business to clients and email to contractors,
and that downgrade removes both columns cleanly.

These tests temporarily step the schema down to 0007 and back up. They must
run serially (pytest default) so no other integration test sees the degraded
schema mid-run.
"""
from __future__ import annotations

import asyncio

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.config import settings


def _alembic_cfg() -> Config:
    return Config("alembic.ini")


async def _columns_present(table: str, *columns: str) -> set[str]:
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = ANY(:cols)"
            ),
            {"t": table, "cols": list(columns)},
        )
        found = {row[0] for row in result.fetchall()}
    await engine.dispose()
    return found


class TestMigration0008:
    def test_upgrade_adds_is_business_to_clients(self, _schema: None) -> None:
        found = asyncio.run(_columns_present("clients", "is_business"))
        assert "is_business" in found

    def test_upgrade_adds_email_to_contractors(self, _schema: None) -> None:
        found = asyncio.run(_columns_present("contractors", "email"))
        assert "email" in found

    def test_downgrade_removes_columns(self, _schema: None) -> None:
        cfg = _alembic_cfg()
        command.downgrade(cfg, "0007")
        try:
            assert asyncio.run(_columns_present("clients", "is_business")) == set()
            assert asyncio.run(_columns_present("contractors", "email")) == set()
        finally:
            command.upgrade(cfg, "head")

    async def test_is_business_defaults_to_false_in_db(self, db: object) -> None:
        from sqlalchemy.ext.asyncio import AsyncSession

        from tests.integration.conftest import make_client, make_contractor

        session = db  # type: ignore[assignment]
        assert isinstance(session, AsyncSession)
        contractor = await make_contractor(session)
        client = await make_client(session, contractor)
        assert client.is_business is False
