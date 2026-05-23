# ADR-002: Prompt caching strategy

**Date**: 2026-04-27
**Status**: accepted

## Context

Every message a contractor sends to Noa will include a large, repeated system prompt containing:
- The contractor's profile (name, rates, tax data, invoice format preferences)
- Their client list and recent history
- Tool definitions (invoice generation, calendar, PDF export, etc.)
- Conversation instructions and tone

Without caching, this context is re-processed on every turn, making the product expensive at scale.

## Decision

Use Claude's prompt caching (`cache_control: {"type": "ephemeral"}`) on the static portions of every request. Structure messages so cacheable content comes first and dynamic content (the new user message) comes last.

Cache the following in order:
1. System prompt (contractor profile + instructions) — changes rarely
2. Tool definitions — static per session
3. Conversation history (rolling cache) — updated each turn

## Cache TTL

Claude's prompt cache TTL is 5 minutes. For a conversational product this is fine — contractors send multiple messages in quick succession during active sessions.

For the contractor profile specifically, if the session is long-lived (e.g. a background agent), use extended cache via `cache_control` on the system message.

## Expected savings

Cached tokens cost ~10% of normal input token price. The system prompt + tool definitions will typically be 2,000-8,000 tokens per request. At scale this reduces AI inference cost by 70-90% per conversation turn.

## Consequences

- Message structure must be disciplined: static content first, dynamic content last
- Profile updates (e.g. contractor changes a rate) must invalidate the cached system prompt — handled by rebuilding the system message on the next request
- Do not cache the final user message — it changes every turn
