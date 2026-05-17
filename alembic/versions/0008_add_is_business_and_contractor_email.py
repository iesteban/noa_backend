"""Add is_business to clients and email to contractors

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-17

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column(
            "is_business",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "contractors",
        sa.Column("email", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contractors", "email")
    op.drop_column("clients", "is_business")
