"""Integration tests for migration 0010 — working_hours table."""
from __future__ import annotations

import asyncio

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.config import settings


def _alembic_cfg() -> Config:
    return Config("alembic.ini")


async def _table_exists(table: str) -> bool:
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = :t"
            ),
            {"t": table},
        )
        exists = result.fetchone() is not None
    await engine.dispose()
    return exists


async def _index_exists(index: str) -> bool:
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_indexes WHERE indexname = :i"),
            {"i": index},
        )
        exists = result.fetchone() is not None
    await engine.dispose()
    return exists


async def _constraint_exists(constraint: str) -> bool:
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT 1 FROM information_schema.table_constraints "
                "WHERE constraint_name = :c"
            ),
            {"c": constraint},
        )
        exists = result.fetchone() is not None
    await engine.dispose()
    return exists


class TestMigration0010:
    def test_upgrade_creates_working_hours_table(self, _schema: None) -> None:
        assert asyncio.run(_table_exists("working_hours"))

    def test_upgrade_creates_contractor_index(self, _schema: None) -> None:
        assert asyncio.run(_index_exists("ix_working_hours_contractor_id"))

    def test_upgrade_creates_unique_constraint(self, _schema: None) -> None:
        assert asyncio.run(_constraint_exists("uq_working_hours_contractor_day"))

    def test_downgrade_drops_table(self, _schema: None) -> None:
        cfg = _alembic_cfg()
        command.downgrade(cfg, "0009")
        try:
            assert not asyncio.run(_table_exists("working_hours"))
            assert not asyncio.run(_index_exists("ix_working_hours_contractor_id"))
        finally:
            command.upgrade(cfg, "head")
