"""Integration tests for migration 0014 — address column on contractors."""
from __future__ import annotations

import asyncio

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.config import settings


def _alembic_cfg() -> Config:
    return Config("alembic.ini")


async def _column_exists(table: str, column: str) -> bool:
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        )
        exists = result.fetchone() is not None
    await engine.dispose()
    return exists


class TestMigration0014:
    def test_upgrade_adds_address_column(self, _schema: None) -> None:
        assert asyncio.run(_column_exists("contractors", "address"))

    def test_downgrade_removes_address_column(self, _schema: None) -> None:
        cfg = _alembic_cfg()
        command.downgrade(cfg, "0013")
        try:
            assert not asyncio.run(_column_exists("contractors", "address"))
        finally:
            command.upgrade(cfg, "head")
