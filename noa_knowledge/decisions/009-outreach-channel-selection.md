# ADR-009: Outreach channel selection based on last inbound channel

**Date**: 2026-05-23  
**Status**: accepted

## Context

Noa proactively reaches out to contractors and clients for reminders, follow-ups, and notifications (payment reminders, appointment confirmations, invoice delivery, etc.). Both Telegram and WhatsApp are supported. When initiating an outbound conversation, the system needs a rule to decide which channel to use.

## Decision

Use the channel the user last wrote to Noa on. If their last inbound message came through Telegram, outreach goes to Telegram. If it came through WhatsApp, outreach goes to WhatsApp.

**Default — no prior interaction**: WhatsApp. Applies when a user (typically a newly added client) has never written to Noa. Contractors who have never interacted also default to WhatsApp.

**Fallback on delivery error**: if the outreach fails on the preferred channel, retry automatically on the other channel. Log both attempts.

**Implementation**: on every inbound message, write the channel to a `last_channel` column on `Contractor` and `Client`. Outreach code reads this column directly without joining through `ConversationSession`.

## Consequences

- Outreach always lands on the channel the user is actively using — no friction from switching.
- Requires `last_channel` (enum: whatsapp, telegram, nullable) on both `Contractor` and `Client`, updated atomically on every inbound message handler. `null` means no prior interaction → default to WhatsApp.
- No additional query at outreach time — a single column read.
- If a user switches channels, outreach self-corrects automatically after their next inbound message.
- Outreach service must handle delivery errors and trigger the fallback; a failed fallback should be surfaced as an alert.
