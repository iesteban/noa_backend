"""Add error_reports table

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-17

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0009"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "  CREATE TYPE platform AS ENUM ('telegram', 'whatsapp'); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    )
    op.create_table(
        "error_reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("contractor_id", sa.UUID(), nullable=False),
        sa.Column(
            "platform",
            PgEnum("telegram", "whatsapp", name="platform", create_type=False),
            nullable=False,
        ),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("context_json", JSONB(), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["contractor_id"], ["contractors.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_error_reports_contractor_created",
        "error_reports",
        ["contractor_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_error_reports_contractor_created", "error_reports")
    op.drop_table("error_reports")
    op.execute("DROP TYPE IF EXISTS platform;")
