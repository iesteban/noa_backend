"""Add contractor_instructions table

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-10

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCOPE_ENUM = sa.Enum(
    "global",
    "invoices",
    "budgets",
    "reminders",
    "appointments",
    name="instructionscope",
)


def upgrade() -> None:
    op.create_table(
        "contractor_instructions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("contractor_id", sa.UUID(), nullable=False),
        sa.Column("scope", _SCOPE_ENUM, nullable=False),
        sa.Column("instruction", sa.String(280), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
    )
    op.create_index(
        "ix_contractor_instructions_contractor_id",
        "contractor_instructions",
        ["contractor_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_contractor_instructions_contractor_id", "contractor_instructions")
    op.drop_table("contractor_instructions")
    _SCOPE_ENUM.drop(op.get_bind(), checkfirst=True)
