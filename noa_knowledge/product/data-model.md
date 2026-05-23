# Data Model

PostgreSQL. All tables have `id` (UUID), `created_at`, `updated_at`.

---

## Entities

### Contractor
The paying user. One row per autónomo.

| Column | Type | Notes |
|--------|------|-------|
| phone_number | varchar | unique — used for routing |
| name | varchar | personal name |
| business_name | varchar | trading name shown on invoices |
| nif | varchar | tax ID |
| address | text | |
| iban | varchar | for payment messages |
| invoice_counter | int | incremented on each invoice, never reused |
| iva_rate | numeric | default 21% |
| irpf_rate | numeric | default 15% |
| channel | enum | whatsapp, telegram, both |
| last_channel | enum | whatsapp, telegram — nullable; last channel the contractor wrote on; null → default to WhatsApp for outreach |
| telegram_chat_id | varchar | nullable |
| whatsapp_chat_id | varchar | nullable |
| onboarded_at | timestamp | null until onboarding complete |
| invite_token | varchar | unique, random — used in client self-registration links |
| email | varchar | nullable — used when sending invoices by email |

---

### Client
A contractor's customer. `(contractor_id, phone_number)` is unique — the same real person can appear as a client of multiple contractors.

| Column | Type | Notes |
|--------|------|-------|
| contractor_id | uuid FK | |
| phone_number | varchar | used for routing inbound messages |
| name | varchar | |
| nif | varchar | nullable — needed for invoice |
| address | text | nullable |
| email | varchar | nullable |
| notes | text | free-form notes the contractor has added |
| last_channel | enum | whatsapp, telegram — nullable; last channel the client wrote on; null → default to WhatsApp for outreach |
| is_business | boolean | default false — business clients and autónomos have IRPF deducted; individuals do not |

**Routing logic:** look up `phone_number` across all clients. If matched to 1 contractor → route directly. If matched to N contractors → disambiguation prompt. If no match → unknown user flow.

---

### Job
A unit of work logged by the contractor. Source of truth for invoice line items.

| Column | Type | Notes |
|--------|------|-------|
| contractor_id | uuid FK | |
| client_id | uuid FK | |
| description | text | what was done |
| date | date | |
| duration_hours | numeric | nullable |
| amount | numeric | |
| status | enum | draft, invoiced |
| photos | varchar[] | array of storage URLs |
| voice_note_url | varchar | original audio if logged by voice |

---

### Invoice
A legal factura. SII-compatible.

| Column | Type | Notes |
|--------|------|-------|
| contractor_id | uuid FK | |
| client_id | uuid FK | |
| invoice_number | varchar | sequential, format: `{year}-{counter}` e.g. `2025-034` |
| date | date | issue date |
| due_date | date | |
| status | enum | draft, sent, paid, overdue |
| subtotal | numeric | before tax |
| iva_amount | numeric | |
| irpf_amount | numeric | |
| total | numeric | |
| pdf_url | varchar | generated PDF in storage |
| sent_at | timestamp | when it was sent to the client |
| paid_at | timestamp | |

### InvoiceLine

| Column | Type | Notes |
|--------|------|-------|
| invoice_id | uuid FK | |
| job_id | uuid FK | nullable — linked to source job if generated from one |
| description | text | |
| quantity | numeric | |
| unit_price | numeric | |
| iva_rate | numeric | |
| irpf_rate | numeric | |
| line_total | numeric | |

---

### Budget
A presupuesto (quote). Not legally binding.

| Column | Type | Notes |
|--------|------|-------|
| contractor_id | uuid FK | |
| client_id | uuid FK | |
| date | date | |
| valid_until | date | nullable |
| status | enum | draft, sent, accepted, rejected, invoiced |
| total | numeric | |
| pdf_url | varchar | |
| sent_at | timestamp | |

### BudgetLine
Same structure as InvoiceLine, but `budget_id` instead of `invoice_id`.

---

### Appointment

| Column | Type | Notes |
|--------|------|-------|
| contractor_id | uuid FK | |
| client_id | uuid FK | nullable — may not know the client yet |
| starts_at | timestamp | |
| duration_minutes | int | |
| description | text | |
| status | enum | scheduled, completed, cancelled, no_show |
| calendar_provider | enum | google, apple (default: google) |
| external_calendar_id | varchar | event ID returned by the provider |
| booked_by | enum | contractor, client — who initiated |

---

### CalendarToken
OAuth tokens per contractor per calendar provider.

| Column | Type | Notes |
|--------|------|-------|
| contractor_id | uuid FK | |
| provider | enum | google, apple |
| access_token | text | encrypted at rest |
| refresh_token | text | encrypted at rest |
| expires_at | timestamp | |

---

### Payment

| Column | Type | Notes |
|--------|------|-------|
| invoice_id | uuid FK | |
| amount | numeric | |
| paid_at | date | |
| method | enum | bizum, transfer, cash, card, other |
| reference | varchar | nullable — Bizum concept or transfer ref |

---

### ErrorReport
Submitted when a contractor reports a problem from chat ("está mal", "/error", replying "no" after a bot-generated document).

| Column | Type | Notes |
|--------|------|-------|
| contractor_id | uuid FK | |
| platform | enum | telegram, whatsapp |
| user_message | text | the contractor's description of the problem |
| context_json | jsonb | last N messages before the report for triage context |
| category | varchar | nullable — manual triage label |

---

### ContractorInstruction
Persistent behavioural rules the contractor has saved ("siempre añade garantía 12 meses"). Injected into Layer 3 of the system prompt. See ADR-007.

| Column | Type | Notes |
|--------|------|-------|
| contractor_id | uuid FK | |
| scope | enum | global, invoices, budgets, calendar, clients |
| text | text | the instruction text |
| is_active | boolean | soft-delete — inactive instructions are excluded from prompts |

Cap: 20 active instructions per contractor.

---

### ConversationSession
Active session context. One per (user × channel). Persists resolved entities within a session.

| Column | Type | Notes |
|--------|------|-------|
| phone_number | varchar | the sender |
| channel | enum | whatsapp, telegram |
| user_type | enum | contractor, client |
| contractor_id | uuid FK | always set — for clients, the matched contractor |
| client_id | uuid FK | nullable — set once client is identified |
| context | jsonb | resolved entities: `{"client_id": "...", "intent": "invoice"}` |
| last_active_at | timestamp | session expires after inactivity |

---

### Message
Conversation history for Claude context window. Stores the raw exchange.

| Column | Type | Notes |
|--------|------|-------|
| session_id | uuid FK | |
| role | enum | user, assistant |
| content | text | text or transcribed audio |
| media_url | varchar | nullable — photo or voice note URL |
| created_at | timestamp | |

Only the last N messages are included in the Claude API call (rolling window). Full history is stored for audit and analytics.

---

## Key relationships

```
Contractor ──< Client ──< Job ──< InvoiceLine >── Invoice
                    │                                  │
                    └──< Appointment        Payment >──┘
                    └──< BudgetLine >── Budget

Contractor ──< ConversationSession ──< Message
Client     ──┘
```

---

## Routing summary

```sql
-- Inbound message from phone_number X
SELECT contractor_id FROM clients WHERE phone_number = X
UNION
SELECT id FROM contractors WHERE phone_number = X
```

- 0 rows → unknown user
- 1 row (contractor) → contractor mode
- 1 row (client) → client mode for that contractor
- N rows (multiple contractors) → disambiguation
