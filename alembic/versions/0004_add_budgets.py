"""Add budgets and budget_lines tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-03

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budgets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contractor_id", UUID(as_uuid=True), sa.ForeignKey("contractors.id"), nullable=False
        ),
        sa.Column(
            "client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False
        ),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("valid_until", sa.Date),
        sa.Column(
            "status",
            sa.Enum("draft", "sent", "accepted", "rejected", "invoiced", name="budgetstatus"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("pdf_url", sa.String(500)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_budgets_contractor_id", "budgets", ["contractor_id"])
    op.create_index("ix_budgets_client_id", "budgets", ["client_id"])

    op.create_table(
        "budget_lines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "budget_id", UUID(as_uuid=True), sa.ForeignKey("budgets.id"), nullable=False
        ),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("iva_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_budget_lines_budget_id", "budget_lines", ["budget_id"])


def downgrade() -> None:
    op.drop_index("ix_budget_lines_budget_id", "budget_lines")
    op.drop_table("budget_lines")
    op.drop_index("ix_budgets_client_id", "budgets")
    op.drop_index("ix_budgets_contractor_id", "budgets")
    op.drop_table("budgets")
    op.execute("DROP TYPE IF EXISTS budgetstatus")
