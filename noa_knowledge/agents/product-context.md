# Agent Skill: Product Context

Include this in a repo's CLAUDE.md to give Claude the domain context needed to make good decisions when building Noa.

---

## Domain: Contractors (autónomos)

An autónomo is a self-employed contractor in Spain — plumber, electrician, cleaner, painter, handyman. They work alone or with one helper. They are not a company; they invoice under their personal NIF.

## Core terminology

- **Factura**: a legal invoice. Must have sequential numbering, client NIF, IVA and IRPF breakdown, SII-compatible format.
- **Presupuesto**: a quote sent before work. Not legally binding.
- **IVA**: VAT, typically 21%. Collected on behalf of the state.
- **IRPF**: income tax withholding, typically 15%. Deducted from invoice total.
- **Modelo 303**: quarterly IVA return filed with Hacienda.
- **Modelo 130**: quarterly IRPF prepayment filed with Hacienda.
- **Gestor**: a tax advisor/accountant. Noa aims to reduce dependence on one for routine tasks.

## What matters to contractors

- Speed: they log work between jobs, often by voice, on the go
- Simplicity: they are not accountants — fiscal terms should be handled invisibly
- Trust: their invoice numbering must never have gaps (audit risk)

## Common mistakes to avoid

- Never reuse or skip invoice numbers — sequential and gapless is a legal requirement
- Do not expose one client's data to another client via the bot
- Do not assume a contractor has consistent income — amounts vary per job
- IRPF is subtracted from the total the contractor receives; IVA is added on top for the client to pay

## AI architecture

See [product/ai-architecture.md](../product/ai-architecture.md) for the full spec. Key points for backend work:

- Model: `claude-sonnet-4-6`
- Prompt cache layers: core instructions → tool definitions → contractor context → conversation history
- Always place `cache_control: {"type": "ephemeral"}` on the last block of each cached layer
- Voice notes: transcribe with Whisper before passing to Claude
- Images: pass as `image_url` blocks — Claude handles vision natively
- Two system prompt modes: contractor (full access) and client (restricted)
