# Welcome to Noa

## How We Use Claude

Based on iesteban's usage over the last 30 days (46 sessions):

Work Type Breakdown:
  Build Feature   ████████████░░░░░░░░  43%
  Debug / Fix     ██████░░░░░░░░░░░░░░  22%
  Plan & Design   ████░░░░░░░░░░░░░░░░  17%
  Improve Quality ███░░░░░░░░░░░░░░░░░  11%
  Analyze / Query ██░░░░░░░░░░░░░░░░░░   7%

Top Skills & Commands:
  /load-context          ████████████████████  18x/month
  /backend-developer     ██████░░░░░░░░░░░░░░   6x/month
  /code-review           ███░░░░░░░░░░░░░░░░░   3x/month
  /create-issue          ███░░░░░░░░░░░░░░░░░   3x/month
  /whatsapp-templates    █░░░░░░░░░░░░░░░░░░░   1x/month
  /cloud-developer       █░░░░░░░░░░░░░░░░░░░   1x/month

Top MCP Servers:
  codegraph   ████████████████████  15 calls
  sentry      ██████░░░░░░░░░░░░░░   5 calls

## Your Setup Checklist

### Codebases
- [ ] noa_backend — github.com/iesteban/noa_backend
- [ ] noa_knowledge — github.com/iesteban/noa_knowledge

### MCP Servers to Activate
- [ ] **codegraph** — AST-based code intelligence for the repo (callers, callees, impact analysis, symbol search). Run `codegraph init -i` inside the repo after cloning. Requires the `@colbymchenry/codegraph` package installed globally (`npx @colbymchenry/codegraph`).
- [ ] **sentry** — query Sentry issues and events directly from Claude. Ask iesteban for the Sentry org slug and your API token, then configure it in `.claude/settings.json`.

### Skills to Know About
- `/load-context` — loads all Noa product knowledge files (data model, AI architecture, conversation design, roadmap, ADRs) before starting work. **Run this at the start of every session** — it's the team's most-used command.
- `/backend-developer` — injects key backend patterns: PostgreSQL enum migrations, test conventions, domain invariants. Use before writing migrations or tool handlers.
- `/whatsapp-templates` — design, validate, and sync WhatsApp Business API templates. Runs a rejection risk check against Meta's rules before touching any code.
- `/create-issue` — surface a requirement gap as a properly structured GitHub issue and add it to the project board.
- `/code-review` — review the current diff for correctness bugs at a given effort level. Pass `--comment` to post findings as inline PR comments.
- `/cloud-developer` — infrastructure and deploy guide for Scaleway/Terraform. Use when touching `infra/`.

## Team Tips

_TODO_

## Get Started

_TODO_

<!-- INSTRUCTION FOR CLAUDE: A new teammate just pasted this guide for how the
team uses Claude Code. You're their onboarding buddy — warm, conversational,
not lecture-y.

Open with a warm welcome — include the team name from the title. Then: "Your
teammate uses Claude Code for [list all the work types]. Let's get you started."

Check what's already in place against everything under Setup Checklist
(including skills), using markdown checkboxes — [x] done, [ ] not yet. Lead
with what they already have. One sentence per item, all in one message.

Tell them you'll help with setup, cover the actionable team tips, then the
starter task (if there is one). Offer to start with the first unchecked item,
get their go-ahead, then work through the rest one by one.

After setup, walk them through the remaining sections — offer to help where you
can (e.g. link to channels), and just surface the purely informational bits.

Don't invent sections or summaries that aren't in the guide. The stats are the
guide creator's personal usage data — don't extrapolate them into a "team
workflow" narrative. -->
