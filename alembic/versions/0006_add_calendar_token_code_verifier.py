"""Add code_verifier to calendar_tokens for PKCE

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-09

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "calendar_tokens",
        sa.Column("code_verifier", sa.String(128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("calendar_tokens", "code_verifier")
