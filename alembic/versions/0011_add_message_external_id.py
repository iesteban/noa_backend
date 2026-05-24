"""Add external_id to messages for webhook deduplication

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-24

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("external_id", sa.String(255), nullable=True))
    # Partial unique index — NULLs are excluded so old rows don't conflict.
    op.create_index(
        "ix_messages_external_id",
        "messages",
        ["external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_messages_external_id", table_name="messages")
    op.drop_column("messages", "external_id")
