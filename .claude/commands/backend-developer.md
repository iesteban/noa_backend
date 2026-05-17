# Noa Backend — Developer Patterns

Key patterns and gotchas to apply when writing migrations, models, and tests for this project.

---

## PostgreSQL Enum types in Alembic migrations

**Always use `postgresql.ENUM` with `create_type=False` in `op.create_table()`, and create the type manually with a DO block.**

SQLAlchemy's `sa.Enum` uses a global name registry. If the ORM model with the same enum name is imported anywhere (e.g. in conftest), `sa.Enum` reuses that object — which has `create_type=True` — and fires an auto-CREATE even after you set `create_type=False`. `postgresql.ENUM` has an independent registry and does not have this problem.

```python
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

def upgrade() -> None:
    # Create the type idempotently — safe if the type already exists.
    op.execute(
        "DO $$ BEGIN "
        "  CREATE TYPE myenum AS ENUM ('a', 'b'); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    )
    op.create_table(
        "my_table",
        ...
        sa.Column(
            "status",
            PgEnum("a", "b", name="myenum", create_type=False),
            nullable=False,
        ),
        ...
    )

def downgrade() -> None:
    op.drop_table("my_table")
    op.execute("DROP TYPE IF EXISTS myenum;")
```

---

## Migration file conventions

- Revision IDs are sequential: `0001`, `0002`, … Check the latest in `alembic/versions/` and increment by 1.
- `down_revision` must point to the highest existing revision on `main` — not a revision that's still in an open PR.
- Every migration needs a corresponding integration test in `tests/integration/test_migration_<rev>.py` covering upgrade (table/columns exist) and downgrade (table/columns gone), using the pattern in existing migration tests.

---

## ORM model conventions

- All models use `PrimaryKeyMixin` (UUID primary key) and `TimestampMixin` (created_at + updated_at) unless it's an append-only log (e.g. `ErrorReport`) — then just define `created_at` manually.
- Register every new model in `tests/integration/conftest.py` with a `from app.models.X import Y  # noqa: F401` import so `Base.metadata` is fully populated for `drop_all()`.
- FK columns: `UUID(as_uuid=True)`, `ForeignKey("table.id")`, `nullable=False`, `index=True`.

---

## Integration test conventions

- Every integration test file that touches the DB uses the `db: AsyncSession` fixture from `conftest.py` — do not create engines inline.
- Migration downgrade tests must restore state in a `try/finally` block: `command.downgrade(cfg, "PREV")` → assert → `finally: command.upgrade(cfg, "head")`.
- Use `asyncio.run()` (sync context) for DB checks inside non-async migration tests; use `async def test_...` with the `db` fixture for ORM tests.
