"""add address and email to clients

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-26
"""
import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("clients", sa.Column("email", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "email")
    op.drop_column("clients", "address")
