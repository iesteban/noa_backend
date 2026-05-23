# ADR-001: Bot-first, no native app

**Date**: 2026-04-27
**Status**: accepted

## Context

The original plan included a React Native mobile app as the primary interface, with a WhatsApp bot added in Phase 3. The question arose: do contractors need a dedicated app, or do they already have everything they need in the messaging apps they use every day?

## Decision

The product interface will be a WhatsApp and Telegram bot from day 1. There will be no native mobile app. A minimal web interface may be introduced later only for things that don't work in chat (e.g. a business dashboard), but the core UX is conversational.

## Consequences

**Easier:**
- No app install friction — contractors just start a chat
- Lower initial development cost and faster iteration
- Voice notes, photos, and file sharing are already native to both platforms
- WhatsApp is where contractors already communicate with their clients — no context switch

**Harder:**
- WhatsApp Business API requires Meta approval (4-8 weeks) — must apply on day 1
- Phone numbers used for WhatsApp Business cannot have had personal WhatsApp previously
- Some UX patterns (dashboards, complex forms) are awkward in chat and may need a web fallback later
- Telegram and WhatsApp have different capabilities — need to manage feature parity
