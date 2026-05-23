# Agent Skills

Shared Claude skill definitions and prompt context for Noa's development agents.

## How to use

Each file here can be referenced in a repo's `CLAUDE.md` with:

```
See noa_knowledge/agents/<skill>.md for [skill description].
```

Or copied into a repo's `.claude/` directory as a custom skill.

## Skills

| File | Purpose |
|------|---------|
| [product-context.md](product-context.md) | Domain knowledge for any agent working on Noa |
| [load-context.md](load-context.md) | `/load-context` slash command — reads all knowledge files and confirms readiness before starting work on noa_backend |
| [create-issue.md](create-issue.md) | `/create-issue` slash command — diagnoses a product gap or inconsistency and files a labelled GitHub issue into the active project board |
