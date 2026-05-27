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

## Private helpers — extract before you finish

**Before calling any function done, run this checklist:**

- [ ] Is there a validation block of 3+ lines? → `_validate_X(raw) -> T | str`
- [ ] Is the same logic copied from another function? → shared `_helper`
- [ ] Is there a distinct step (load+check, render+upload, parse+convert) that makes the caller hard to scan? → named helper
- [ ] Is there a `try/except` around a side-effect that should never raise? → `_try_do_X()`

The goal: a handler body should read as a flat sequence of named steps, not inline logic.

### Validation helpers in tool handlers

Tool handlers return strings to Claude, so validation helpers return `T | str` (value or error string) instead of raising.

```python
def _validate_lines(raw: object) -> list[dict[str, object]] | str:
    if not raw or not isinstance(raw, list):
        return "lines is required and must be a non-empty list."
    for i, ln in enumerate(raw):
        ...
    return raw

def _parse_valid_until(raw: object) -> date | str | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return "Invalid valid_until — use YYYY-MM-DD format."

# Handler reads as steps, not inline validation
@register("create_budget")
async def handle_create_budget(tool_input, db, session):
    lines_or_err = _validate_lines(tool_input.get("lines"))
    if isinstance(lines_or_err, str):
        return lines_or_err

    valid_until_or_err = _parse_valid_until(tool_input.get("valid_until"))
    if isinstance(valid_until_or_err, str):
        return valid_until_or_err

    budget = await create_budget(...)
    pdf_url = await _upload_budget_pdf(budget, contractor, db)
    ...
```

### General code structure

When a function contains a distinct logical branch that makes it hard to read at a glance, extract it into a private helper (`_name`). The caller should read like a list of steps; the helper owns the details.

```python
# Good — reads as a straight sequence of steps
if await _try_handle_error_report(db, session, text, channel, last_assistant, send, recipient_id):
    return
reply = await call_claude(db, session, text)

# Avoid — inline state machine buried in the middle of a larger function
if session.context.get("pending_error_report"):
    ...  # 10 lines
is_error, description = detect_error_intent(text, last_assistant)
if is_error:
    ...  # 10 more lines
```

### Raise, don't return sentinels (outside tool handlers)

In service functions and non-handler code, raise exceptions rather than returning `None` or error strings. Let FastAPI's exception handlers or the caller decide how to respond.

```python
# Good — service code
async def get_contractor_or_raise(db: AsyncSession, contractor_id: uuid.UUID) -> Contractor:
    contractor = await db.get(Contractor, contractor_id)
    if contractor is None:
        raise ValueError(f"Contractor {contractor_id} not found")
    return contractor

# Avoid — callers must check and can silently ignore
async def get_contractor(db, contractor_id) -> Contractor | None:
    return await db.get(Contractor, contractor_id)
```

---

## Integration test conventions

- Every integration test file that touches the DB uses the `db: AsyncSession` fixture from `conftest.py` — do not create engines inline.
- Migration downgrade tests must restore state in a `try/finally` block: `command.downgrade(cfg, "PREV")` → assert → `finally: command.upgrade(cfg, "head")`.
- Use `asyncio.run()` (sync context) for DB checks inside non-async migration tests; use `async def test_...` with the `db` fixture for ORM tests.
