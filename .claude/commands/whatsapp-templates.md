# WhatsApp Template Skill

Help design, validate, add, and sync WhatsApp message templates for Noa.
All templates live in `app/messaging/whatsapp_templates.py` under the `TEMPLATES` list.
The sync workflow is `.github/workflows/sync-wa-templates.yml` (manual `workflow_dispatch`).

---

## When invoked

- **"Create / add a template"** → follow Steps 1–5 below
- **"Check / validate templates"** → read `app/messaging/whatsapp_templates.py`, run the rejection risk check (Step 3) on every template, report results
- **"Sync templates"** → jump to [Sync to Meta](#sync-to-meta)

---

## Step 1 — Gather requirements

Ask (or infer from context):
- What triggers this message? (appointment confirmed, invoice sent, payment reminder, etc.)
- Who receives it? (contractor or client)
- What variables are needed? (name, amount, date, etc.)
- Does it need an action button? (QUICK_REPLY, call, URL)
- What category fits? (UTILITY, MARKETING, AUTHENTICATION)

---

## Step 2 — Design the template

```python
{
    "name": "snake_case_name",           # lowercase, digits, underscores only
    "language": "es",                    # ISO 639-1 code
    "category": "UTILITY",               # UTILITY | MARKETING | AUTHENTICATION
    "components": [
        {"type": "HEADER", ...},         # optional
        {"type": "BODY", ...},           # required
        {"type": "FOOTER", ...},         # optional
        {"type": "BUTTONS", ...},        # optional
    ],
}
```

### HEADER (optional, max 1)

| Format | Limit | Notes |
|--------|-------|-------|
| TEXT | 60 chars, max 1 variable | Renders bold above body |
| IMAGE | 5 MB, JPEG/PNG, 800×418px | |
| VIDEO | 16 MB, MP4/3GP, <60s | |
| DOCUMENT | 100 MB, PDF/DOC/DOCX/XLS/XLSX/PPT/PPTX | |
| LOCATION | Static pin, coords supplied at send time | |

```python
{"type": "HEADER", "format": "TEXT", "text": "Presupuesto Generado"}
{"type": "HEADER", "format": "IMAGE", "example": {"header_url": ["https://..."]}}
```

### BODY (required, exactly 1)

- Max **1024 characters** total (across header + body + footer + buttons)
- Variables: `{{1}}`, `{{2}}`, `{{3}}` — positional, sequential, no gaps
- Do **not** start or end body text with a variable
- Do **not** place two variables adjacent to each other
- Every variable **must** have a sample value in `example.body_text`
- Markdown formatting supported: `*bold*`, `_italic_`, `~strikethrough~`

```python
{
    "type": "BODY",
    "text": "Hola {{1}}, {{2}} quiere organizar una cita de {{3}}.",
    "example": {"body_text": [["Ana", "Fontanería García", "fontanería"]]},
}
```

### FOOTER (optional, max 1)

- Max **60 characters** — plain text only, no variables, no markdown

```python
{"type": "FOOTER", "text": "Responde STOP para cancelar"}
```

### BUTTONS (optional)

| Type | Max per template | Text limit | Notes |
|------|-----------------|------------|-------|
| QUICK_REPLY | 10 | 25 chars | Sends button text back as user message |
| URL | 2 | 25 chars text, 2000 chars URL | Supports 1 variable at end of URL |
| PHONE_NUMBER | 1 | 25 chars | Opens dialer |
| OTP / COPY_CODE | 1 | fixed text | AUTHENTICATION only |

**Rules:** max 10 buttons total; same-type buttons must be grouped consecutively; OTP cannot mix with other types.

```python
{
    "type": "BUTTONS",
    "buttons": [
        {"type": "QUICK_REPLY", "text": "Confirmar disponibilidad"},
        {"type": "QUICK_REPLY", "text": "No puedo"},
    ],
}
```

---

## Step 3 — Rejection risk check

Before writing any code, evaluate every rule below. Mark ✅ PASS, ⚠️ WARN, or ❌ FAIL.

### Category
- ❌ FAIL — UTILITY template contains promotional language ("gratis", "oferta", "descuento", "promoción", urgency like "¡Último día!")
- ❌ FAIL — MARKETING template sent to users without explicit opt-in
- ⚠️ WARN — template purpose is ambiguous between UTILITY and MARKETING

### Body text
- ❌ FAIL — body > 1024 characters
- ❌ FAIL — body contains a raw URL (use a URL button instead)
- ❌ FAIL — variables are not sequential from {{1}} (e.g. {{1}}, {{3}} without {{2}})
- ❌ FAIL — any variable used without a corresponding `example` value
- ❌ FAIL — body starts or ends with `{{N}}`
- ❌ FAIL — two variables appear adjacent to each other
- ❌ FAIL — body is an open-ended question without QUICK_REPLY buttons (instant rejection)
- ⚠️ WARN — body asks user to "reply to this message" as a button workaround
- ⚠️ WARN — body contains ALL CAPS words (looks spammy)

### Header
- ❌ FAIL — header text > 60 characters
- ❌ FAIL — header has variables but no `example` provided

### Footer
- ❌ FAIL — footer > 60 characters
- ❌ FAIL — footer contains variables (not supported)

### Buttons
- ❌ FAIL — more than 10 buttons total
- ❌ FAIL — any button text > 25 characters
- ❌ FAIL — QUICK_REPLY and CTA (URL/PHONE_NUMBER) buttons mixed in the same template
- ⚠️ WARN — UTILITY template has no buttons (Meta strongly prefers interactive elements)

### Template name
- ❌ FAIL — name contains uppercase letters or spaces
- ⚠️ WARN — name is very generic (e.g. "message", "notification")

### Language
- ❌ FAIL — not a valid BCP-47 code

### Example values
- ❌ FAIL — any `{{N}}` variable lacks a corresponding example value
- ⚠️ WARN — example values look like placeholders ("test", "xxx", "ejemplo")

---

## Step 4 — Report and decide

```
## Rejection Risk: LOW / MEDIUM / HIGH

### Checks
✅ Category: UTILITY — transactional, no promotional language
✅ Body length: 53 chars (limit: 1024)
✅ Variables: sequential {{1}}, {{2}}, {{3}} with realistic examples
✅ Buttons: 1 QUICK_REPLY within limit
⚠️ WARN: ...
❌ FAIL: ...

### Verdict
[LOW/MEDIUM] Proceeding to add.
[HIGH] Fix ❌ FAIL items above. Suggest corrected design and loop back to Step 2.
```

- **LOW** (no FAILs, ≤1 WARN) → proceed automatically
- **MEDIUM** (no FAILs, 2+ WARNs) → show report, ask for confirmation
- **HIGH** (any FAIL) → do NOT add to code

---

## Step 5 — Add to codebase

1. Read `app/messaging/whatsapp_templates.py`
2. Append the new template dict to the `TEMPLATES` list
3. Show the diff — do not modify anything else in the file

---

## Sync to Meta

The sync workflow submits all `TEMPLATES` to the Meta Graph API and polls until each is APPROVED or REJECTED.

### Trigger

Always confirm the environment before triggering. Default to staging.

```bash
# Staging
gh workflow run sync-wa-templates.yml --ref main --field environment=staging

# Production
gh workflow run sync-wa-templates.yml --ref main --field environment=production
```

Poll until done:
```bash
gh run list --workflow=sync-wa-templates.yml --limit=1
gh run watch <run-id>
gh run view <run-id> --log-failed   # if it fails
```

### What the sync does

1. Lists existing templates in the Meta account
2. For each template in `TEMPLATES`:
   - **Not found** → creates it, waits for approval
   - **REJECTED** → deletes and recreates (Meta returns 400 on update of rejected templates)
   - **Body changed** → updates it, re-submits for approval
   - **Unchanged + APPROVED** → skips
   - **Unchanged + not APPROVED** → waits for approval
3. Polls every 10s up to 300s for `APPROVED`; raises on `REJECTED`

### If the sync fails with REJECTED

Check the rejection reason directly from Meta:

```bash
source .env.staging && curl -s \
  "https://graph.facebook.com/v19.0/${WHATSAPP_BUSINESS_ACCOUNT_ID}/message_templates\
?fields=id,name,status,rejected_reason,components&access_token=${WHATSAPP_ACCESS_TOKEN}" \
  | python3 -m json.tool
```

Then re-run the rejection risk check (Step 3) and fix any ❌ FAIL items.

### Environments

| Environment | Secrets |
|-------------|---------|
| staging | `STAGING_WHATSAPP_ACCESS_TOKEN`, `STAGING_WHATSAPP_BUSINESS_ACCOUNT_ID` |
| production | `PRODUCTION_WHATSAPP_ACCESS_TOKEN`, `PRODUCTION_WHATSAPP_BUSINESS_ACCOUNT_ID` |

---

## Rejection reason codes

| Code | Meaning | Fix |
|------|---------|-----|
| `INVALID_FORMAT` | Structure malformed | Check component order, variable syntax, char limits. If body solicits a response, add QUICK_REPLY buttons. |
| `TAG_CONTENT_MISMATCH` | Category doesn't match content | Move promotional content to MARKETING; strip promo language from UTILITY |
| `INVALID_PARAMETER` | Variable syntax wrong | Ensure `{{N}}` notation, sequential, no spaces inside braces |
| `DUPLICATE_TEMPLATE` | Identical body/footer already exists | Change wording or delete the duplicate first |
| `ABUSIVE_CONTENT` | Policy violation | Remove sensitive data requests, illegal or threatening content |
| `NONE` (with REJECTED) | Automated content policy catch-all | Simplify body, remove solicitations, add sample values |

**Instant rejection** (seconds) = automated check: open-ended question in UTILITY, body starts/ends with `{{N}}`, missing sample values, adjacent variables.

**Delayed rejection** (hours) = human review. Usually a content policy edge case.

---

## Quality & lifecycle

- New or low-quality templates have delivery throttled while Meta collects feedback
- Quality drops when users block or report the message — pause schedule: 3h → 6h → permanent disable
- Avoid: multiple messages to same user in quick succession, vague personalization, urgency tactics

---

## Approved template reference (staging)

| Name | Category | Status | Notes |
|------|----------|--------|-------|
| `presupuesto_generado` | — | APPROVED | Has HEADER + BODY + QUICK_REPLY — use as structural reference |
| `appointment_request` | UTILITY | REJECTED (INVALID_FORMAT) | Fixed: added sample values + QUICK_REPLY button |
