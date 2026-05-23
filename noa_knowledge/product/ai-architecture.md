# AI Architecture

## Model

**claude-sonnet-4-6** for all conversation turns (contractor and client).
Use **claude-haiku-4-5** only for fire-and-forget classification tasks where latency and cost matter more than reasoning quality (e.g. detecting language, spam filtering inbound client messages).

---

## Pipelines

### Text message
```
Inbound text → routing → build API request → Claude → tool calls → response → send reply
```

### Voice note
```
Inbound audio URL → download → Whisper API → transcribed text → same as text pipeline
Store: voice_note_url + transcription in Message table
```

### Photo
```
Inbound image URL → pass as image_url block in Claude message → Claude vision handles it natively
No separate Vision API needed — Claude is multimodal
```

---

## Prompt cache structure

Every API call is assembled in 4 layers, ordered from most stable to most dynamic. Cache breakpoints are placed after layers 1–3.

```
┌─────────────────────────────────────────────┐
│ Layer 1 — Core instructions          CACHED │  ~1,000 tokens
│ Role, behavior, language, tone,             │
│ act-then-confirm rule, disambiguation rule  │
├─────────────────────────────────────────────┤
│ Layer 2 — Tool definitions           CACHED │  ~2,000 tokens
│ All tool schemas (see below)                │
├─────────────────────────────────────────────┤
│ Layer 3 — Contractor context         CACHED │  ~2,000 tokens
│ Profile, recent clients (last 10),          │
│ upcoming appointments, unpaid invoices      │
├─────────────────────────────────────────────┤
│ Layer 4 — Conversation history  NOT CACHED  │  last 20 messages
│ Current user message                        │
└─────────────────────────────────────────────┘
```

Cache TTL is 5 minutes. Layers 1–3 stay warm across the full session. Layer 3 is rebuilt on each new session (contractor profile may have changed).

### API call structure

```python
response = client.messages.create(
    model="claude-sonnet-4-6",
    system=[
        {
            "type": "text",
            "text": CORE_INSTRUCTIONS,
            "cache_control": {"type": "ephemeral"},   # breakpoint 1
        },
        {
            "type": "text",
            "text": build_contractor_context(contractor, clients),
            "cache_control": {"type": "ephemeral"},   # breakpoint 2
        },
    ],
    tools=[
        *TOOL_DEFINITIONS,   # cache_control on last tool definition
    ],
    messages=conversation_history + [{"role": "user", "content": current_message}],
)
```

---

## Two system prompt modes

The system prompt changes based on who is talking. Layer 1 (core instructions) differs; Layer 3 (context) differs.

### Contractor mode
- Full access to all tools
- Knows the contractor's financial data, all clients, invoice history
- Tone: efficient, direct — the contractor is busy and on the go

### Client mode
- Restricted tool set (booking, availability, own invoices, payment info)
- Does not expose contractor's financials or other clients
- Tone: friendly, professional — acts as the contractor's front desk
- Context includes: contractor's business name, FAQ answers, communication style

---

## Tool definitions

### Contractor tools

| Tool | Description |
|------|-------------|
| `search_client(query)` | Search clients by name. Returns list for disambiguation. |
| `log_job(client_id, description, date, duration_hours, amount)` | Creates a Job record. |
| `create_invoice(client_id, job_ids, date, due_date)` | Generates invoice PDF, returns pdf_url. |
| `create_budget(client_id, lines, valid_until)` | Generates budget PDF, returns pdf_url. |
| `get_client_history(client_id, date_from, date_to)` | Returns jobs, invoices, payments for a client. |
| `get_unpaid_invoices(client_id?)` | Returns unpaid invoices, optionally filtered by client. |
| `get_availability(date_from, date_to)` | Returns free slots from calendar. |
| `create_appointment(client_id, starts_at, duration_minutes, description)` | Creates appointment + calendar event. |
| `send_payment_reminder(invoice_id)` | Sends payment reminder to client via bot. |
| `get_tax_summary(quarter, year)` | Returns income/expense summary for the period. |
| `send_file_to_client(client_id, file_url, message)` | Forwards a PDF to the client's chat. |

### Client tools

| Tool | Description |
|------|-------------|
| `get_contractor_availability(date_from, date_to)` | Returns free slots. |
| `book_appointment(starts_at, description)` | Creates appointment, notifies contractor. |
| `get_my_invoices()` | Returns the client's invoices with this contractor. |
| `get_payment_info()` | Returns IBAN and Bizum number for payment. |
| `notify_contractor(message)` | Escalates to contractor — pings them in their own chat. |

---

## Escalation flow

When a client message cannot be resolved by the bot:

1. Bot calls `notify_contractor(message)` tool
2. Backend sends a message to the contractor's chat:
   ```
   "Ana Gómez te pregunta: '¿La reparación tiene garantía?'
    Respóndeme aquí y se lo hago llegar."
   ```
3. Contractor replies to Noa → backend forwards to client session
4. The contractor's reply is stored in both sessions for continuity

---

## Session assembly

Before each API call, the backend assembles the request from DB state:

```python
def build_request(session: ConversationSession) -> dict:
    contractor = get_contractor(session.contractor_id)
    clients = get_recent_clients(session.contractor_id, limit=10)  # last 10 by job date, for Layer 3
    history = get_recent_messages(session.id, limit=20)   # Layer 4

    return {
        "system": [
            layer_1_instructions(session.user_type),
            layer_3_context(contractor, clients),          # Layer 2 tools added via `tools=`
        ],
        "tools": TOOL_DEFINITIONS_WITH_CACHE,
        "messages": history,
    }
```

Layer 3 includes:
- Contractor profile (name, NIF, IBAN, rates)
- Recent clients (id, name, phone) — the 10 most recent by last job date, for disambiguation without a tool call. Clients outside this set are resolved via `search_client`.
- Next 7 days of appointments
- Unpaid invoices count + total

---

## Layer 3 at runtime — the client roster

Layer 3 is a plain-text block injected into the system prompt. The client roster uses a **hybrid model**: the 10 most recently active clients are embedded directly in Layer 3; any client outside that set is resolved via a `search_client` tool call.

**Why 10**: covers the long tail of repeat work (most autónomos call the same handful of clients week after week) while keeping Layer 3 token-stable regardless of total client count — a contractor with 500 clients costs the same as one with 20.

**Cache invalidation**: Layer 3 is rebuilt at the start of each new session. A client being added or edited does not bust the cache mid-session; the updated roster appears on the next session.

Example of what Layer 3 looks like at runtime:

```
## Perfil del contratista
Nombre: Pedro García
Empresa: Fontanería García
NIF: 12345678A
IBAN: ES91 2100 0418 4502 0005 1332
IVA: 21%
IRPF: 15%

## Clientes recientes (10 de 47 — usa search_client para los demás)
- Ana López      | id: a1b2c3d4-... | +34600000001
- Juan Ruiz      | id: e5f6g7h8-... | +34600000002
- María Fernández| id: i9j0k1l2-... | +34600000003
...
```

The total client count and the instruction to use `search_client` are included in the header so Claude knows the roster is not exhaustive. For contractors with ≤10 clients the header reads *(10 de 10)* and no fallback is needed.

---

## Agentic tool loop

After the API call returns, the backend checks `stop_reason`:

- **`end_turn`** — Claude produced a text response. Extract it and send to the user. Done.
- **`tool_use`** — Claude wants to call one or more tools before responding. Run each tool, feed the results back, and call the API again. Loop.
- **anything else** — unexpected; log a warning and return the fallback message.

The loop is capped at `_MAX_TOOL_ROUNDS = 5` to prevent runaway chains.

### Step-by-step example

Contractor sends: *"Guarda 2 horas con Ana López del lunes, cobré 120€"*

**Case A — Ana López is in the recent roster (no tool call for lookup):**

```
Turn 1 → Claude  stop_reason=tool_use  → log_job(client_id="a1b2...", duration_hours=2, amount=120, ...)
Backend runs log_job → returns "Trabajo guardado. Job id: xyz"
Turn 2 → Claude  stop_reason=end_turn  → "Listo, apunté 2 horas con Ana López el lunes, 120 €."
```

**Case B — client is not in the recent roster (search_client fallback):**

```
Turn 1 → Claude  stop_reason=tool_use  → search_client(query="Ana López")
Backend runs search_client → returns "[Ana López | id: a1b2...]"
Turn 2 → Claude  stop_reason=tool_use  → log_job(client_id="a1b2...", duration_hours=2, amount=120, ...)
Backend runs log_job → returns "Trabajo guardado. Job id: xyz"
Turn 3 → Claude  stop_reason=end_turn  → "Listo, apunté 2 horas con Ana López el lunes, 120 €."
```

Each tool result is appended to the messages list as a `tool_result` block with the matching `tool_use_id`, so Claude has full context for the next turn.

---

## Tool dispatcher

Tool handlers are registered with a decorator and live in `app/ai/` modules:

```python
# app/ai/tools/jobs.py
from app.ai.dispatcher import register

@register("log_job")
async def handle_log_job(tool_input: dict, db: AsyncSession, session: ConversationSession) -> str:
    # create Job record, return confirmation string
    ...
```

The dispatcher holds a registry dict (`tool_name → handler`). When the agentic loop receives a `tool_use` block, it calls `dispatch_tool(name, input, db, session)`, which looks up the handler and runs it.

If no handler is registered for a tool name, the dispatcher returns `"Tool 'X' is not yet implemented."` — a valid string that Claude can work with gracefully. The loop never crashes on an unimplemented tool.

If a handler raises an exception, the dispatcher catches it, logs it, and returns `"Tool 'X' encountered an error. Please try again."` — same principle: the loop always continues.

This means new tools can be added one at a time by registering a handler, without touching the loop logic in `claude.py`.

---

## Cost estimate (per conversation turn)

| Tokens | Cached? | Cost (Sonnet) |
|--------|---------|---------------|
| ~5,000 system + tools | Yes (10%) | ~$0.0015 |
| ~2,000 history | No | ~$0.006 |
| ~100 user message | No | ~$0.0003 |
| ~300 response | Output | ~$0.0045 |
| **Total** | | **~$0.012 / turn** |

Without caching the system prompt, cost would be ~$0.027 / turn — caching cuts it by ~55%.
