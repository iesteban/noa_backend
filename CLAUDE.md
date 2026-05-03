# Noa Backend

AI assistant for Spanish independent contractors (autónomos). Lives entirely in WhatsApp and Telegram — no app. Contractors talk to Noa by voice or text; Noa handles invoicing, scheduling, and client comms.

## Stack

- **Framework**: FastAPI (Python)
- **Database**: PostgreSQL via SQLAlchemy (async) + Alembic migrations
- **AI**: Claude API (`claude-sonnet-4-6`), Whisper API (voice transcription)
- **Messaging**: Telegram Bot API (Phase 0), WhatsApp Business API (Phase 1+)
- **Storage**: Scaleway Object Storage (S3-compatible, `boto3`)
- **Calendar**: Google Calendar API (OAuth2 per contractor)
- **PDF**: SII-compatible invoice and budget generation

## Project structure

```
app/
  api/          # FastAPI routers (webhooks, admin)
  services/     # Business logic (invoice, job, calendar, session)
  ai/           # Claude integration (session assembly, tool handlers)
  models/       # SQLAlchemy ORM models
  schemas/      # Pydantic schemas
  storage/      # Scaleway S3 client
  calendar/     # CalendarProvider protocol + GoogleCalendarProvider
  pdf/          # Invoice and budget PDF generation
alembic/        # Database migrations
tests/
```

## Running locally

```bash
cp .env.example .env        # fill in secrets
docker compose up -d        # PostgreSQL
alembic upgrade head        # run migrations
uvicorn app.main:app --reload
```

## Git workflow

Always work on a branch — never commit directly to main.

```bash
git checkout -b feat/<short-description>   # or fix/, chore/
# make changes
git add <specific files>
git commit -m "..."
git push origin feat/<short-description>
gh pr create --base main
```

One branch per issue. Reference the issue in the PR body (`Closes #N`).

Do not add `Co-Authored-By` trailers to commit messages.

## Integration tests

Every feature or tool handler must have a corresponding integration test in `tests/integration/`. Integration tests hit a real PostgreSQL instance (via `docker compose up -d`) — do not mock the database.

Minimum coverage per piece of work:
- **New service or tool handler**: at least one happy-path test and one error/edge-case test
- **New API endpoint**: test the full request→response cycle including DB state
- **New migration**: test that `alembic upgrade head` + `alembic downgrade -1` both succeed cleanly

Run integration tests before opening a PR:

```bash
docker compose up -d
alembic upgrade head
.venv/bin/pytest tests/integration/
```

## Before opening a PR

Run these checks in order and fix any issues before pushing:

```bash
.venv/bin/ruff check --fix app/ tests/   # auto-fix lint issues
.venv/bin/mypy app                        # type-check; fix any errors manually
.venv/bin/pytest tests/unit/             # all unit tests must pass
.venv/bin/pytest tests/integration/      # integration tests must pass
```

Do not open a PR if any of these fail.

## After opening a PR

Poll CI until it finishes, then report the result:

```bash
until gh pr checks <PR> 2>&1 | grep -qv pending; do sleep 8; done && gh pr checks <PR>
```

If CI fails, read the logs (`gh run view <run-id> --log-failed`), fix the issue, commit, push, and poll again.

## Running tests

```bash
pytest                      # all tests
pytest tests/services/      # unit tests only
pytest tests/integration/   # requires DB
```

---

## Domain invariants — never violate these

**Invoice numbering**: `invoice_counter` on `Contractor` is incremented atomically and never reused. Format: `{year}-{counter:03d}` (e.g. `2025-034`). Gaps in numbering are an audit risk under Spanish tax law.

**Data isolation**: A client's data is scoped to their contractor. Never return one contractor's clients, jobs, invoices, or financial data to another contractor or their clients. The routing logic enforces this — verify it in every query.

**IVA and IRPF**: IVA (21% default) is added on top — the client pays it. IRPF (15% default) is deducted from the contractor's net — they receive less. Never swap these.

---

## Routing logic

Every inbound message is routed by `phone_number`:

```
phone matches Contractor.phone_number  → contractor mode
phone matches Client.phone_number (1 contractor) → client mode
phone matches Client.phone_number (N contractors) → disambiguation prompt
no match → unknown user / onboarding
```

Two system prompt modes use different Layer 1 instructions and Layer 3 context. Never expose contractor financials or other clients in client mode.

---

## Claude API — prompt cache structure

Assemble every API call in this order. Cache breakpoints go after layers 1–3.

```
Layer 1 — Core instructions        CACHED   ~1,000 tokens
Layer 2 — Tool definitions         CACHED   ~2,000 tokens
Layer 3 — Contractor context       CACHED   ~2,000 tokens
Layer 4 — Conversation history     NOT CACHED  (last 20 messages)
```

```python
response = client.messages.create(
    model="claude-sonnet-4-6",
    system=[
        {"type": "text", "text": CORE_INSTRUCTIONS,
         "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": build_contractor_context(contractor, clients),
         "cache_control": {"type": "ephemeral"}},
    ],
    tools=TOOL_DEFINITIONS_WITH_CACHE,
    messages=history + [{"role": "user", "content": current_message}],
)
```

Use `claude-haiku-4-5` only for fire-and-forget classification (language detection, spam filtering) where reasoning quality doesn't matter.

---

## Storage paths

```
/{contractor_id}/invoices/{uuid}.pdf
/{contractor_id}/budgets/{uuid}.pdf
/{contractor_id}/voice/{uuid}.ogg
/{contractor_id}/photos/{uuid}.jpg
```

Use pre-signed URLs when sending files to clients via the bot.

---

## Calendar

All calendar operations go through the `CalendarProvider` protocol (`app/calendar/base.py`). Never call the Google Calendar SDK directly from business logic — always use the provider interface. This allows adding Apple Calendar later without touching services.

---

## Key references

`noa_knowledge` must be checked out as a sibling directory (`../noa_knowledge`).
All paths below are relative to that repo root.

- Product overview: `../noa_knowledge/product/overview.md`
- Full AI architecture: `../noa_knowledge/product/ai-architecture.md`
- Data model: `../noa_knowledge/product/data-model.md`
- Conversation design: `../noa_knowledge/product/conversation-design.md`
- Architecture decisions: `../noa_knowledge/decisions/`
