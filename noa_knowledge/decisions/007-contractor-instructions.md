# ADR-007: Contractor behavioral instructions

**Date**: 2026-05-08  
**Status**: accepted

## Context

Contractors have recurring preferences that differ from the defaults — a clause they always add to invoices, a tone they prefer for payment reminders, a note they include in every budget. Without a way to persist these preferences, they repeat the same corrections on every interaction.

The challenge is exposing this capability in a way that fits the bot-first interface: no settings panel, no "prompt editor", no concept a plumber needs to understand. It has to feel like Noa learning, not the contractor configuring.

## Decision

Introduce **contractor instructions**: short, persistent, scoped directives that Claude applies automatically when generating documents or sending messages. They live in Layer 3 of the prompt cache alongside the contractor's profile.

Instructions are created in two ways:

**1. Implicit learning** — when the same correction is made twice within a rolling 7-day window, Noa proposes saving it:
```
[After third time adding "Garantía 12 meses" footer to invoices]
Noa: "Veo que siempre añades la cláusula de garantía. 
     ¿La pongo por defecto en todas las facturas?"
```

**2. Explicit instruction** — contractor states a rule directly:
```
Contractor: "De ahora en adelante, todos mis presupuestos 
            llevan una nota: materiales y mano de obra incluidos"
Noa: "Entendido, lo aplico en todos los presupuestos desde ahora."
```

In both cases, Noa confirms what it understood before saving, and reminds the contractor they can change it at any time.

### Data model

```sql
ContractorInstruction
  id              uuid PK
  contractor_id   uuid FK
  scope           enum  -- global | invoices | budgets | reminders | appointments
  instruction     text  -- plain language, max 280 chars
  active          bool  -- default true
  created_at      timestamp
  updated_at      timestamp
```

### Prompt cache integration

Instructions are injected at the end of Layer 3, after the contractor profile and client roster:

```
## Instrucciones personales
- [facturas] Añadir al pie: "Garantía de mano de obra 12 meses."
- [presupuestos] Incluir nota: "Precio con materiales y mano de obra incluidos."
- [recordatorios] Tono informal — estos clientes me conocen.
```

Scope acts as a filter: Claude only applies invoice instructions when generating invoices, etc. Global instructions apply everywhere.

### Management via chat

```
Contractor: "¿Qué instrucciones tienes guardadas?"
Noa: "Tengo estas:
     1. Facturas — pie con garantía 12 meses
     2. Presupuestos — nota de materiales incluidos
     ¿Cambio o elimino alguna?"

Contractor: "Borra la 2"
Noa: "Eliminada. Ya no la añado a los presupuestos."
```

## Consequences

**Easier:**
- Contractors stop repeating themselves — corrections stick
- Personalization emerges from use, not from a configuration screen
- Layer 3 already exists and is cached — instructions add ~200 tokens at most
- New tool needed: `get_instructions`, `save_instruction`, `delete_instruction` — low complexity

**Harder:**
- Implicit learning requires tracking correction patterns across messages — needs a lightweight heuristics layer before reaching Claude (detect repeated tool call + same field modified = candidate instruction)
- Instructions can conflict (a global rule vs. a scoped rule) — Claude resolves by preferring the narrower scope; document this in core instructions
- Instructions are in plain language — Claude must interpret them, not execute them literally. Edge cases (ambiguous instructions) should fall back to asking the contractor to clarify
- Max instruction count per contractor should be capped (suggested: 20) to keep Layer 3 predictable

## Rollout

- **Phase 1**: explicit instructions only — contractor states a rule, Noa saves it. Simple `ContractorInstruction` CRUD + Layer 3 injection.
- **Phase 2**: implicit learning — pattern detection on corrections, proactive proposal. Ship after explicit instructions have been validated in production.
