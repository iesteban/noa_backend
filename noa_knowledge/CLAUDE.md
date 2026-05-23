# Noa Knowledge Base — Claude Context

This repo is the source of truth for company knowledge, product decisions, and Claude agent skills for Noa.

## What is Noa?

Noa is an AI assistant for independent contractors (autónomos) in Spain. It lives inside WhatsApp and Telegram — no native app. Contractors talk to Noa by voice or text to log work, generate invoices and budgets, track payments, and eventually have the bot handle their clients autonomously.

## Interface

The product is a **WhatsApp and Telegram bot**. There is no native mobile app (see [decisions/001-bot-first-no-native-app.md](decisions/001-bot-first-no-native-app.md)).

- **Telegram**: used in Phase 0 (no API approval needed, faster iteration)
- **WhatsApp Business API**: applied for on day 1, live from Phase 1

## Repos

- **noa-backend**: FastAPI (Python) + PostgreSQL, handles bot webhooks, AI orchestration, PDF generation
- **noa-app**: ~~React Native~~ — replaced by bot interface

## How this repo is used

- `product/` contains domain knowledge that should inform how Claude reasons about the product
- `agents/` contains shared skill definitions and prompts reused across repos
- `decisions/` documents key decisions so Claude can understand *why* things are built the way they are
- `ops/` documents team processes

## Key domain concepts

- **Autónomo**: a self-employed contractor in Spain — plumber, electrician, cleaner, handyman. Not a large business. Works alone or with one helper. Invoices are legally required and must be SII-compatible. Quarterly tax models: 303 (IVA) and 130 (IRPF).
- **Factura**: a legal invoice. Must have sequential numbering, client CIF/NIF, SII format compliance.
- **Presupuesto**: a quote/budget sent to a client before work begins. Not legally binding but expected professionally.
- **Gestor**: a tax advisor/accountant that many autónomos outsource their admin to. Noa aims to reduce dependence on one for routine tasks.

## Roadmap summary

See [product/roadmap.md](product/roadmap.md) for full detail.

| Phase | Timeline | Theme |
|-------|----------|-------|
| 0 | Months 1-2 | Telegram MVP — voice note → structured note |
| 1 | Months 3-5 | Documents — invoice/budget generation, calendar, WhatsApp live |
| 2 | Months 6-9 | Business cycle — payments, tax summaries, reminders |
| 3 | Months 10-14 | Client-facing bot — bot responds to contractor's clients |
| 4 | Months 15-18 | Intelligence — demand prediction, follow-ups, analytics |
