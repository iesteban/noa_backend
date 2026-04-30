"""Initial schema — Contractor, Client, Job, ConversationSession, Message

Revision ID: 0001
Revises:
Create Date: 2026-04-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contractors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("business_name", sa.String(255)),
        sa.Column("nif", sa.String(20)),
        sa.Column("iban", sa.String(34)),
        sa.Column("invoice_counter", sa.Integer, nullable=False, server_default="0"),
        sa.Column("iva_rate", sa.Numeric(5, 4), nullable=False, server_default="0.2100"),
        sa.Column("irpf_rate", sa.Numeric(5, 4), nullable=False, server_default="0.1500"),
        sa.Column(
            "channel",
            sa.Enum("telegram", "whatsapp", name="channel"),
            nullable=False,
            server_default="telegram",
        ),
        sa.Column("telegram_chat_id", sa.String(50)),
        sa.Column("onboarded_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_contractors_phone_number", "contractors", ["phone_number"], unique=True)

    op.create_table(
        "clients",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contractor_id", UUID(as_uuid=True), sa.ForeignKey("contractors.id"), nullable=False
        ),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("nif", sa.String(20)),
        sa.Column("notes", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("contractor_id", "phone_number", name="uq_client_contractor_phone"),
    )
    op.create_index("ix_clients_contractor_id", "clients", ["contractor_id"])
    op.create_index("ix_clients_phone_number", "clients", ["phone_number"])

    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contractor_id", UUID(as_uuid=True), sa.ForeignKey("contractors.id"), nullable=False
        ),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id")),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("date", sa.Date),
        sa.Column("duration_hours", sa.Numeric(6, 2)),
        sa.Column("amount", sa.Numeric(12, 2)),
        sa.Column(
            "status",
            sa.Enum("draft", "invoiced", name="jobstatus"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("voice_note_url", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_contractor_id", "jobs", ["contractor_id"])
    op.create_index("ix_jobs_client_id", "jobs", ["client_id"])

    op.create_table(
        "conversation_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column(
            "user_type",
            sa.Enum("contractor", "client", name="usertype"),
            nullable=False,
        ),
        sa.Column("contractor_id", UUID(as_uuid=True), sa.ForeignKey("contractors.id")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id")),
        sa.Column("context", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_conversation_sessions_phone_number", "conversation_sessions", ["phone_number"]
    )
    op.create_index(
        "ix_conversation_sessions_contractor_id", "conversation_sessions", ["contractor_id"]
    )
    op.create_index(
        "ix_conversation_sessions_client_id", "conversation_sessions", ["client_id"]
    )

    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversation_sessions.id"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", name="messagerole"),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("media_url", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_index("ix_conversation_sessions_client_id", "conversation_sessions")
    op.drop_index("ix_conversation_sessions_contractor_id", "conversation_sessions")
    op.drop_index("ix_conversation_sessions_phone_number", "conversation_sessions")
    op.drop_table("conversation_sessions")
    op.drop_index("ix_jobs_client_id", "jobs")
    op.drop_index("ix_jobs_contractor_id", "jobs")
    op.drop_table("jobs")
    op.drop_index("ix_clients_phone_number", "clients")
    op.drop_index("ix_clients_contractor_id", "clients")
    op.drop_table("clients")
    op.drop_index("ix_contractors_phone_number", "contractors")
    op.drop_table("contractors")
    op.execute("DROP TYPE IF EXISTS messagerole")
    op.execute("DROP TYPE IF EXISTS usertype")
    op.execute("DROP TYPE IF EXISTS jobstatus")
    op.execute("DROP TYPE IF EXISTS channel")
