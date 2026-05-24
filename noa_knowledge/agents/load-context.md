# Skill: load-context

Read and internalize the Noa knowledge base before starting work on noa_backend.

## Install

Copy this file to `noa_backend/.claude/commands/load-context.md`.
The command becomes available as `/load-context` inside that repo.

## What this skill does

When invoked, Claude reads the core knowledge files from `../noa_knowledge/`, then
produces a brief context brief confirming what it has loaded and is ready to work.

## Prompt (copy verbatim into the command file)

---

Read the following files from the Noa knowledge base, then confirm you are ready to work on noa_backend with a one-paragraph brief:

- `../noa_knowledge/product/overview.md`
- `../noa_knowledge/product/ai-architecture.md`
- `../noa_knowledge/product/data-model.md`
- `../noa_knowledge/product/conversation-design.md`
- `../noa_knowledge/product/roadmap.md`
- `../noa_knowledge/product/personas.md`
- `../noa_knowledge/decisions/001-bot-first-no-native-app.md`
- `../noa_knowledge/decisions/002-prompt-caching.md`
- `../noa_knowledge/decisions/003-object-storage-scaleway.md`
- `../noa_knowledge/decisions/004-calendar-abstraction.md`

After reading, reply with:

1. **Context loaded** — one paragraph naming the product, current phase, stack, and the 2–3 domain invariants most likely to affect backend work (invoice numbering, data isolation, IVA/IRPF).
2. **Ready** — one sentence confirming you're ready and asking what to work on.

Do not summarize every file — synthesize only what's load-bearing for backend decisions.
