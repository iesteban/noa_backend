"""Add invoices and invoice_lines tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-03

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contractor_id", UUID(as_uuid=True), sa.ForeignKey("contractors.id"), nullable=False
        ),
        sa.Column(
            "client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False
        ),
        sa.Column("invoice_number", sa.String(20), nullable=False, unique=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("due_date", sa.Date),
        sa.Column(
            "status",
            sa.Enum("draft", "sent", "paid", "overdue", name="invoicestatus"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("iva_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("irpf_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("pdf_url", sa.String(500)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_invoices_contractor_id", "invoices", ["contractor_id"])
    op.create_index("ix_invoices_client_id", "invoices", ["client_id"])

    op.create_table(
        "invoice_lines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=False
        ),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id")),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("iva_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("irpf_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_invoice_lines_invoice_id", "invoice_lines")
    op.drop_table("invoice_lines")
    op.drop_index("ix_invoices_client_id", "invoices")
    op.drop_index("ix_invoices_contractor_id", "invoices")
    op.drop_table("invoices")
    op.execute("DROP TYPE IF EXISTS invoicestatus")
