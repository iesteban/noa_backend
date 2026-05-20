"""Add working_hours table

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-20

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "working_hours",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("contractor_id", sa.UUID(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("is_working_day", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["contractor_id"], ["contractors.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contractor_id", "day_of_week", name="uq_working_hours_contractor_day"),
    )
    op.create_index("ix_working_hours_contractor_id", "working_hours", ["contractor_id"])


def downgrade() -> None:
    op.drop_index("ix_working_hours_contractor_id", "working_hours")
    op.drop_table("working_hours")
