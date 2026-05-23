# Product Roadmap

18 months · 5 phases · conversation-first strategy

## Strategic principle

The entire UX lives in messaging. No app to install, no new habit to form — the contractor already lives in WhatsApp. The bot is both their management tool and eventually their client-facing interface.

**Critical constraint:** WhatsApp Business API approval takes 4-8 weeks. Apply on day 1. Start on Telegram while you wait — no approval needed, faster iteration.

---

## Phase 0 — Months 1-2: "El asistente escucha"

**Goal:** validate that contractors actually use a bot to log their work. Ship on Telegram only.

| Feature | Description | Effort | Status |
|---------|-------------|--------|--------|
| Voice note → structured note | Contractor speaks; bot extracts client, date, work, amount. Suggests saving. | Low | ✓ Done |
| Basic client registry | Each note enriches the client profile. Search by name. | Low | ✓ Done |
| Client registration — by message | Contractor tells the bot a new client by text or voice ("Añade a Ana García, teléfono 600123456"). Bot extracts name and phone, confirms, and saves. | Low | ✓ Done |
| Client registration — by contact share | Contractor shares a contact card (Telegram/WhatsApp vCard). Bot parses name and phone from the vCard and registers the client. | Low | ✓ Done |
| Import existing invoices | Upload PDFs or photos of past invoices. AI learns formats, rates, and regular clients. | Medium | Planned |
| Call recording (speakerphone) | Listens to ambient audio during a call; on hang-up, suggests an automatic note. | Medium | Planned |

**Stack:** FastAPI · PostgreSQL · Whisper API · Claude API · Telegram Bot API

---

## Phase 1 — Months 3-5: "El asistente genera"

**Goal:** the bot replaces the contractor's notepad and invoicing tool. WhatsApp channel goes live.

> **WhatsApp is live.** Meta Business API integrated (PR #99, 2026-05-12) — Twilio removed. Webhook verified, voice notes and PDF delivery working.

| Feature | Description | Effort | Status |
|---------|-------------|--------|--------|
| Budget generation | Generate a budget by voice or photo. Learns the contractor's usual prices. | Medium | Planned |
| Invoice generation | Legal PDF invoice (SII-compatible), auto sequential numbering, delivered in chat. | Medium | In Progress |
| Calendar sync | "Mañana a las 10 con Pedro" → creates event in Google/Apple Calendar. | Medium | ✓ Done |
| Task management | "Mañana tengo que llamar al almacén" → all-day reminder in Calendar. Floating tasks ("comprar material") live as a pending list in Noa. Daily summary merges appointments and tasks. | Low | Planned |
| Smart scheduling | When a client asks for availability, proposes slots based on calendar + travel time. | Medium | In Progress |
| Client history queries | "¿Cuánto le cobré a Pedro el año pasado?" List invoices and budgets with filters (client, date, status) and pagination. | Low | ✓ Done |
| Time and travel tracking | Detects start/end of work. Calculates hours per client and suggests amount. | Low | Planned |
| Job photos linked to client | Photo → auto-linked to active job. Before/after in history. | Low | In Progress |
| Client self-registration | Contractor shares a personal invite link. Client messages the bot, confirms their name, and is registered as pending. Client can immediately request a quote or book an appointment (pending contractor approval). | Medium | In Progress |
| Contractor task inbox | Bot surfaces pending actions to the contractor: new client approvals and appointment requests. Reminder shown at session start: "Tienes X tareas pendientes" + newest 3. Contractor accepts or rejects by chat. | Medium | Planned |
| Contractor instructions (explicit) | Contractor states a persistent rule ("siempre añade garantía 12 meses"). Noa saves it and applies it automatically. Managed via chat. See ADR-007. | Low | ✓ Done |
| User error reporting | Contractor reports problems directly from chat ("está mal", "/error"). Bot captures context, saves an ErrorReport, and acknowledges. Admin endpoint exports reports for triage. | Low | ✓ Done |
| Contractor working hours | Contractor sets when they work ("lunes a viernes de 8 a 18h"). Availability checks and booking flows respect these hours; out-of-hours bookings trigger a warning. | Low | Planned |
| Rate limiting | Per-contractor caps on bot messages (hourly/daily), AI calls (Whisper/Claude, daily), and document generation (invoices/budgets, monthly). HTTP-level limits on webhook endpoints. Backed by Scaleway Managed Redis. See ADR-008. | Low | Planned |

---

## Phase 2 — Months 6-9: "El ciclo se cierra"

**Goal:** close the full economic loop. Contractor can track what they're owed and communicate professionally with clients.

| Feature | Description | Effort |
|---------|-------------|--------|
| Payment tracking | Detects unpaid invoices. Sends configurable automatic reminders to clients. | Medium |
| Bizum / bank transfer payment link | Generates the payment message or link from a voice note. | Medium |
| Quarterly tax summary | Excel with income/expenses for modelo 303 and 130. Deadline alerts. | Medium |
| Appointment reminders | WhatsApp to client 24h and 1h before. Handles confirmations and cancellations. | Medium |
| Personalised communication templates | Learns the contractor's tone. Messages sound like them, not a bot. | Low |
| Automatic review requests | After collecting payment, sends a message asking for a Google Maps review. | Low |
| Contractor instructions (implicit learning) | Noa detects when the same correction is made twice in 7 days and proposes saving it as a rule. Builds on Phase 1 explicit instructions. See ADR-007. | Medium |

---

## Phase 3 — Months 10-14: "El bot trabaja solo"

**Goal:** the bot faces the contractor's clients, not just the contractor. Incoming work is managed without touching the phone.

| Feature | Description | Effort |
|---------|-------------|--------|
| WhatsApp bot — client replies | Answers FAQs, gives availability, manages the conversation autonomously. | High |
| WhatsApp bot — appointment scheduling | Client says "can you come Thursday?" — bot checks calendar, proposes time, confirms. | High |
| Photo → AI quote | Contractor photographs the damage. AI identifies the job type and generates an estimate. | High |
| Virtual assistant for calls | VoIP number. When the contractor can't answer, the assistant takes the call and logs or schedules. | High |

**Requires:** WhatsApp Business API active · VoIP number (Twilio/Vonage) · Vision API

---

## Phase 4 — Months 15-18: "El negocio aprende"

**Goal:** with enough accumulated data, the assistant starts anticipating — when to call a client, seasonal demand peaks, pricing optimisation.

| Feature | Description | Effort |
|---------|-------------|--------|
| Route optimisation | Orders the day's jobs to minimise travel. Google Maps integration. | Medium |
| Demand prediction | Detects the contractor's seasonal patterns. "In June you always get AC calls." | High |
| Client follow-up suggestions | "18 months since you installed María García's boiler — good time to offer a service." | Medium |
| Business dashboard | Revenue, active clients, average ticket, collection rate. | Medium |

**Requires:** 6+ months of production data.
