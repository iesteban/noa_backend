"""Integration tests for migration 0013 — pending_client appointment status."""
from __future__ import annotations

import asyncio

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.config import settings


def _alembic_cfg() -> Config:
    return Config("alembic.ini")


async def _enum_has_value(enum_name: str, value: str) -> bool:
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT 1 FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE e.enumlabel = :v AND t.typname = :e"
            ),
            {"v": value, "e": enum_name},
        )
        exists = result.fetchone() is not None
    await engine.dispose()
    return exists


class TestMigration0013:
    def test_upgrade_adds_pending_client_value(self, _schema: None) -> None:
        assert asyncio.run(_enum_has_value("appointmentstatus", "pending_client"))

    def test_downgrade_removes_pending_client_value(self, _schema: None) -> None:
        cfg = _alembic_cfg()
        command.downgrade(cfg, "0012")
        try:
            assert not asyncio.run(_enum_has_value("appointmentstatus", "pending_client"))
        finally:
            command.upgrade(cfg, "head")
