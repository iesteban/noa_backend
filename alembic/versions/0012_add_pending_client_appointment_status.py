"""Add pending_client value to appointmentstatus enum

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-25

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "  ALTER TYPE appointmentstatus ADD VALUE IF NOT EXISTS 'pending_client'; "
        "END $$;"
    )


def downgrade() -> None:
    # PostgreSQL does not support DROP VALUE; rebuild the enum without the value.
    # Use CAST() instead of :: to avoid SQLAlchemy's text() parameter parser
    # misidentifying ::type as a named bindparam.
    # Drop the column default first — it references the enum type in the catalog
    # and would block DROP TYPE even after the column is changed to text.
    op.execute("UPDATE appointments SET status = 'scheduled' WHERE status = 'pending_client'")
    op.execute("ALTER TABLE appointments ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE appointments ALTER COLUMN status TYPE text "
        "USING CAST(status AS text)"
    )
    op.execute("DROP TYPE appointmentstatus")
    op.execute(
        "CREATE TYPE appointmentstatus AS ENUM "
        "('scheduled', 'completed', 'cancelled', 'no_show')"
    )
    op.execute(
        "ALTER TABLE appointments ALTER COLUMN status TYPE appointmentstatus "
        "USING CAST(status AS appointmentstatus)"
    )
    op.execute(
        "ALTER TABLE appointments ALTER COLUMN status SET DEFAULT 'scheduled'"
    )
