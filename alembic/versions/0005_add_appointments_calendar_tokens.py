"""Add appointments and calendar_tokens tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-03

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_appointment_status = PgEnum(
    "scheduled", "completed", "cancelled", "no_show",
    name="appointmentstatus", create_type=False,
)
_calendar_provider = PgEnum("google", "apple", name="calendarprovider", create_type=False)
_booked_by = PgEnum("contractor", "client", name="bookedby", create_type=False)


def upgrade() -> None:
    conn = op.get_bind()
    # Create enum types first, idempotently.
    PgEnum("scheduled", "completed", "cancelled", "no_show", name="appointmentstatus").create(
        conn, checkfirst=True
    )
    PgEnum("google", "apple", name="calendarprovider").create(conn, checkfirst=True)
    PgEnum("contractor", "client", name="bookedby").create(conn, checkfirst=True)

    op.create_table(
        "appointments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contractor_id", UUID(as_uuid=True), sa.ForeignKey("contractors.id"), nullable=False
        ),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", _appointment_status, nullable=False, server_default="scheduled"),
        sa.Column("calendar_provider", _calendar_provider, nullable=True),
        sa.Column("external_calendar_id", sa.String(500), nullable=True),
        sa.Column("booked_by", _booked_by, nullable=False, server_default="contractor"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_appointments_contractor_id", "appointments", ["contractor_id"])

    op.create_table(
        "calendar_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contractor_id", UUID(as_uuid=True), sa.ForeignKey("contractors.id"), nullable=False
        ),
        sa.Column("provider", _calendar_provider, nullable=False),
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column("access_token", sa.Text, nullable=True),
        sa.Column("refresh_token", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "contractor_id", "provider", name="uq_calendar_token_contractor_provider"
        ),
    )
    op.create_index("ix_calendar_tokens_contractor_id", "calendar_tokens", ["contractor_id"])
    op.create_index("ix_calendar_tokens_state", "calendar_tokens", ["state"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_calendar_tokens_state", "calendar_tokens")
    op.drop_index("ix_calendar_tokens_contractor_id", "calendar_tokens")
    op.drop_table("calendar_tokens")
    op.drop_index("ix_appointments_contractor_id", "appointments")
    op.drop_table("appointments")
    conn = op.get_bind()
    PgEnum(name="bookedby").drop(conn, checkfirst=True)
    PgEnum(name="calendarprovider").drop(conn, checkfirst=True)
    PgEnum(name="appointmentstatus").drop(conn, checkfirst=True)
