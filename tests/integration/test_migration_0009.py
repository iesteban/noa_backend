"""Integration tests for migration 0009 — error_reports table."""
from __future__ import annotations

import asyncio

from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from app.config import settings
from app.models.error_report import ErrorReport, Platform


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


class TestMigration0009:
    def test_upgrade_creates_error_reports_table(self, _schema: None) -> None:
        assert asyncio.run(_table_exists("error_reports"))

    def test_upgrade_creates_index(self, _schema: None) -> None:
        assert asyncio.run(_index_exists("ix_error_reports_contractor_created"))

    def test_downgrade_drops_table_and_index(self, _schema: None) -> None:
        cfg = _alembic_cfg()
        command.downgrade(cfg, "0008")
        try:
            assert not asyncio.run(_table_exists("error_reports"))
            assert not asyncio.run(_index_exists("ix_error_reports_contractor_created"))
        finally:
            command.upgrade(cfg, "head")


class TestErrorReportModel:
    async def test_insert_and_retrieve(self, db: AsyncSession) -> None:
        from tests.integration.conftest import make_contractor

        contractor = await make_contractor(db)
        report = ErrorReport(
            contractor_id=contractor.id,
            platform=Platform.telegram,
            user_message="La factura salió mal",
            context_json=[
                {"role": "user", "content": "genera factura"},
                {"role": "assistant", "content": "Factura generada"},
            ],
        )
        db.add(report)
        await db.flush()

        rows = await db.execute(
            select(ErrorReport).where(ErrorReport.contractor_id == contractor.id)
        )
        saved = rows.scalars().one()
        assert saved.platform == Platform.telegram
        assert saved.user_message == "La factura salió mal"
        assert len(saved.context_json) == 2

    async def test_category_is_nullable(self, db: AsyncSession) -> None:
        from tests.integration.conftest import make_contractor

        contractor = await make_contractor(db)
        report = ErrorReport(
            contractor_id=contractor.id,
            platform=Platform.whatsapp,
            user_message="Error en el audio",
            context_json=[],
        )
        db.add(report)
        await db.flush()

        rows = await db.execute(
            select(ErrorReport).where(ErrorReport.id == report.id)
        )
        assert rows.scalars().one().category is None

    async def test_created_at_set_automatically(self, db: AsyncSession) -> None:
        from tests.integration.conftest import make_contractor

        contractor = await make_contractor(db)
        report = ErrorReport(
            contractor_id=contractor.id,
            platform=Platform.telegram,
            user_message="Test",
            context_json=[],
        )
        db.add(report)
        await db.flush()
        await db.refresh(report)

        assert report.created_at is not None

    async def test_data_isolation(self, db: AsyncSession) -> None:
        from tests.integration.conftest import make_contractor

        contractor_a = await make_contractor(db)
        contractor_b = await make_contractor(db)
        report = ErrorReport(
            contractor_id=contractor_b.id,
            platform=Platform.telegram,
            user_message="Error de B",
            context_json=[],
        )
        db.add(report)
        await db.flush()

        rows = await db.execute(
            select(ErrorReport).where(ErrorReport.contractor_id == contractor_a.id)
        )
        assert rows.scalars().all() == []
