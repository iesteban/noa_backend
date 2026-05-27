You are a senior backend engineer planning implementation work for the Noa Backend project.

The user has invoked `/plan-issues $ARGUMENTS` where `$ARGUMENTS` is the GitHub Project number to pull issues from.

---

## Step 0 — Validate input

If `$ARGUMENTS` is empty or not a number, stop and say:
> Usage: `/plan-issues <project-number>` — e.g. `/plan-issues 3`

---

## Step 1 — Pull latest main

```bash
git fetch origin main && git checkout main && git pull origin main
```

Confirm you are on main and up to date before proceeding.

---

## Step 2 — List open issues in the project

```bash
gh project item-list $ARGUMENTS --owner iesteban --format json --limit 200
```

If the command fails with a scope error, stop and tell the user to run:
```
gh auth refresh -s read:project
```

From the JSON output, extract all items where `type == "ISSUE"` and `content.state == "OPEN"`.
Collect their issue numbers. If no open issues are found, report that and stop.

---

## Step 3 — For each open issue, produce a plan

For every issue number collected above, run:
```bash
gh issue view <number> -R iesteban/noa_backend
```

Read the full title, body, labels, and any referenced issues.

Then produce an implementation plan using the format below.

---

## Plan format

### Plan: [Issue Title] (#N)

**Skills to load**

Always include:
- `/load-context` — loads product and architecture knowledge base
- `/backend-developer` — loads migration, model, and test patterns

Also include if the issue touches **infra, deploy, Terraform, Scaleway, Docker, CI/CD, GitHub Actions, environment variables, or secrets**:
- `/cloud-developer`

Also include if the issue touches **WhatsApp message templates, Meta Business API template messages (HSM), or template-based outreach**:
- `/whatsapp-template`

**Summary**
1–2 sentences: what this solves and why it matters for Noa.

**Scope & Approach**
High-level strategy. Note architectural trade-offs. Mention relevant existing code by file path where you can infer it.

**Files to Create**
| File | Purpose |
|------|---------|
| `app/...` | ... |

(Omit section if none.)

**Files to Modify**
| File | Change |
|------|--------|
| `app/...` | ... |

**Database Changes**
List new tables, columns, or enum values. For enums: use `postgresql.ENUM` + DO block — never `sa.Enum`. Note if downgrade is safe or destructive. Write "None" if not applicable.

**New / Modified Claude Tools**
If this adds or changes Claude tool definitions, list name + description + key input fields. Write "None" if not applicable.

**Integration Tests Required**
Concrete test scenarios (per CLAUDE.md: happy-path + error/edge-case per handler/endpoint; migration upgrade+downgrade if DB changes):
- `tests/integration/test_<feature>.py` — covers: ...

**Unit Tests Required**
- `tests/unit/test_<feature>.py` — covers: ...

**Domain Invariant Checklist**
- [ ] Invoice numbering not affected / correctly implemented
- [ ] Data isolation enforced in all new queries (scoped to `contractor_id`)
- [ ] IVA/IRPF handling correct (if financial)
- [ ] Prompt cache structure preserved (if AI layer changes)
- [ ] Routing logic unchanged / correctly extended (if webhook changes)

**Estimated Effort**
S (< half a day) / M (half–full day) / L (> 1 day) — with one-line justification.

**Open Questions / Risks**
Anything the engineer must decide before starting, or invariants at risk.

---

## Step 4 — Post the plan as a comment

For each issue, post the plan as a GitHub comment:

```bash
gh issue comment <number> -R iesteban/noa_backend --body "<plan markdown>"
```

**Never edit the original issue body.** The plan always goes in a new comment.

Confirm each comment was posted by printing the returned comment URL.

---

## Step 5 — Summary

After all issues are processed, print a summary table:

| Issue | Title | Effort | Skills |
|-------|-------|--------|--------|
| #N | ... | S/M/L | `/load-context` `/backend-developer` [+ extras] |

Sort by effort descending (L first), then issue number ascending within each band.
