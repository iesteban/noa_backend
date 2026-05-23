# Product Overview

## What is Noa?

Noa is an AI assistant for independent contractors (autónomos) in Spain. It lives entirely inside WhatsApp and Telegram — no app to install. Contractors talk to Noa the same way they talk to clients: by voice or text. Noa handles the admin work that nobody has time for.

## Target user

- **Who**: Independent contractors (autónomos) — plumbers, electricians, cleaners, painters, handymen
- **Pain points**:
  - Forgetting to write down what they did and what to charge
  - Invoicing is slow, confusing, or done by a gestor they have to wait for
  - Chasing unpaid invoices manually
  - Losing client history and pricing across jobs
- **Jobs to be done**:
  - Log work quickly, right after a job or call
  - Generate a legal invoice or budget without paperwork
  - Know what clients owe them and follow up automatically
  - Not miss appointments or calls from new clients

## Core interface

The product is a **WhatsApp and Telegram bot** on a single shared Noa number. There is no native app.

Two user types share the same number, routed by phone number lookup:
- **Contractor**: manages their business through Noa (full access)
- **Client**: books appointments, requests quotes, pays invoices, views history (limited access, on behalf of their contractor)

See [conversation-design.md](conversation-design.md) for the full interaction spec.

## Core workflows

1. Voice note → structured note (client, date, work, amount)
2. "Genera factura para Pedro" → PDF delivered in chat
3. Payment tracking + automatic reminders to clients
4. Calendar management via conversation
5. Client-facing bot: responds to the contractor's clients autonomously

## Stack

- Backend: FastAPI (Python)
- Database: PostgreSQL
- AI: Whisper API (voice), Claude API (reasoning), Vision API (photos)
- Messaging: Telegram Bot API (Phase 0), WhatsApp Business API (Phase 1+)
- Documents: PDF generation (SII-compatible invoices, modelo 303/130)

## Non-goals

- A native mobile app (the bot IS the interface)
- Serving large businesses or teams
- Replacing a full gestor for complex fiscal situations
