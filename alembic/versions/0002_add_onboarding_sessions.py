"""Add onboarding_sessions table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-02

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "onboarding_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("chat_id", sa.String(50), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("step", sa.String(50), nullable=False),
        sa.Column("data", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_onboarding_sessions_chat_id",
        "onboarding_sessions",
        ["chat_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_onboarding_sessions_chat_id", table_name="onboarding_sessions")
    op.drop_table("onboarding_sessions")
