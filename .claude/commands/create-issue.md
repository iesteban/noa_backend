# Skill: create-issue

Surface a product requirement gap or inconsistency as a GitHub issue, assign it to the active project board, and tag it correctly.

## Install

Copy this file to `noa_backend/.claude/commands/create-issue.md`.
The command becomes available as `/create-issue` inside that repo.

## What this skill does

When invoked with a description of a requirement gap, ambiguity, or inconsistency, Claude:

1. Resolves the open project board (fails fast if auth scope is missing).
2. Loads the relevant product knowledge files to understand context.
3. Diagnoses the gap — what the requirement says, what the implementation implies, and what's missing or contradictory.
4. Drafts a well-structured GitHub issue with title, body, and labels.
5. Creates the issue and adds it to the project board.

## Token requirements

The GitHub CLI token must have the `project` scope to add issues to a project board.
If `gh project list` fails with a scope error, ask the user to run:

```
gh auth refresh -s project
```

## Prompt (copy verbatim into the command file)

---

You are helping me file a well-structured GitHub issue for the `iesteban/noa_backend` repo.

**Step 0 — Resolve the project board.**

Before doing anything else, run:

```bash
gh project list --owner iesteban --format json
```

Filter to open projects only (`closed: false`).

- If exactly one open project exists, record its number silently and proceed.
- If more than one, list them and ask the user which to use before continuing.
- If the command fails with a scope error, stop and tell the user to run `gh auth refresh -s project`, then retry.
- If none exist, stop and tell the user — do not create the issue without a project.

**Step 1 — Load context.**

Read these files to understand the product:

- `../noa_knowledge/product/overview.md`
- `../noa_knowledge/product/data-model.md`
- `../noa_knowledge/product/ai-architecture.md`
- `../noa_knowledge/product/conversation-design.md`
- `../noa_knowledge/product/roadmap.md`

**Step 2 — Diagnose the gap.**

Using the context you just loaded and the description the user provided (or the current conversation), identify:

- What the product spec or roadmap says (or doesn't say) about this area.
- What the existing implementation implies.
- The specific inconsistency, missing requirement, or ambiguity that needs resolving.

If the user's description is vague, ask one clarifying question before proceeding.

**Step 3 — Draft the issue.**

Format:

```
Title: [Type] Short imperative description

Type is one of: Bug | Feature | Improvement | Question | Decision

Body:

## Context
One paragraph: what area of the product this touches and why it matters.

## Problem / Gap
What is unclear, missing, or inconsistent. Quote the spec or roadmap if relevant.

## Impact
What goes wrong or stays unresolved if this is not addressed (user-facing, legal, or technical consequence).

## Proposed resolution  (omit if it's a pure Question)
What the fix or decision should look like. Keep it directive, not exhaustive.

## References
- Relevant knowledge file(s): e.g. `product/roadmap.md`, `decisions/004-calendar-abstraction.md`
- Related issues: (if any — check with `gh issue list --repo iesteban/noa_backend --search "<keywords>"`)
```

Choose the most appropriate labels from:

| Label | Use when |
|-------|----------|
| `bug` | Existing behaviour is wrong |
| `enhancement` | New feature or improvement |
| `question` | A decision needs to be made |
| `ai` | Claude API, prompts, tool definitions |
| `messaging` | Telegram / WhatsApp routing |
| `invoicing` | Invoices, budgets, PDF |
| `calendar` | Calendar sync, appointments |
| `payments` | Payment tracking, reminders |
| `storage` | Scaleway S3, files |
| `database` | Schema, migrations |
| `infra` | Deployment, CI/CD |
| `client-bot` | Client-facing bot (Phase 3) |
| `testing` | Test coverage |

Show the user the draft title, body, and proposed labels. Wait for their approval or edits before creating anything.

**Step 4 — Create the issue and add it to the project.**

```bash
gh issue create \
  --repo iesteban/noa_backend \
  --title "<title>" \
  --body "<body>" \
  --label "<label1>,<label2>"
```

Capture the returned issue URL. Then add it to the project:

```bash
gh project item-add <project-number> \
  --owner iesteban \
  --url <issue-url>
```

Report the issue URL and confirm it was added to the project board.
