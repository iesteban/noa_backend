# WhatsApp Template Skill

Help design, validate, add, and sync WhatsApp message templates for Noa.

---

You are helping manage WhatsApp Business API message templates for the Noa backend.

Your job is to:
1. Understand what the template needs to do
2. Design the template components
3. Run a **rejection risk check** against Meta's known rules before writing any code
4. Add the template to `app/messaging/whatsapp_templates.py` only if risk is LOW or MEDIUM with the user's approval
5. Optionally sync templates to staging or production via CI

If the user asks to **sync** templates (rather than create one), jump directly to [Step 6 — Sync to Meta](#step-6--sync-to-meta).

---

## Step 1 — Gather requirements

Ask the user (or infer from context) what the template is for:
- What triggers this message? (appointment confirmed, invoice sent, payment reminder, etc.)
- Who receives it? (contractor or client)
- What variables are needed? (name, amount, date, etc.)
- Does it need an action button? (QUICK_REPLY, call, URL)
- What category fits? (UTILITY, MARKETING, AUTHENTICATION)

If the user already described the template, skip directly to designing it.

---

## Step 2 — Design the template

Design the template following this structure:

```python
{
    "name": "<snake_case_name>",          # lowercase, underscores only
    "language": "es",                      # BCP-47 code
    "category": "<UTILITY|MARKETING|AUTHENTICATION>",
    "components": [
        # HEADER (optional)
        {
            "type": "HEADER",
            "format": "TEXT",              # or IMAGE, DOCUMENT, VIDEO
            "text": "...",                 # max 60 chars; variables allowed: {{1}}
            "example": {"header_text": ["example value"]},  # required if variables used
        },
        # BODY (required)
        {
            "type": "BODY",
            "text": "...",                 # max 1024 chars; variables: {{1}}, {{2}}, ...
            "example": {"body_text": [["val1", "val2"]]},  # REQUIRED if any {{N}} used
        },
        # FOOTER (optional)
        {
            "type": "FOOTER",
            "text": "...",                 # max 60 chars; NO variables
        },
        # BUTTONS (optional, but strongly recommended for UTILITY templates)
        {
            "type": "BUTTONS",
            "buttons": [
                # QUICK_REPLY: max 3 buttons, text max 25 chars
                {"type": "QUICK_REPLY", "text": "Confirmar"},
                # CALL_TO_ACTION — phone
                {"type": "PHONE_NUMBER", "text": "Llamar", "phone_number": "+34..."},
                # CALL_TO_ACTION — URL (max 2 CTAs total)
                {"type": "URL", "text": "Ver factura", "url": "https://..."},
            ],
        },
    ],
}
```

---

## Step 3 — Rejection risk check

Before writing any code, evaluate the template against every rule below. For each rule, mark ✅ PASS, ⚠️ WARN, or ❌ FAIL.

### Category rules
- ❌ FAIL if UTILITY template contains promotional language (discounts, offers, "gratis", "oferta", "descuento", "promoción", urgency like "¡Último día!")
- ❌ FAIL if MARKETING template is being sent to people who haven't opted in to marketing
- ⚠️ WARN if the template purpose is ambiguous between UTILITY and MARKETING

### Body text rules
- ❌ FAIL if body > 1024 characters
- ❌ FAIL if body contains a raw URL (use a URL button instead)
- ❌ FAIL if variables are not sequential starting at {{1}} (e.g. {{1}}, {{3}} without {{2}} is invalid)
- ❌ FAIL if any variable is used but no `example` value is provided for it
- ⚠️ WARN if body asks the user to "reply to this message" as a workaround for missing buttons — Meta flags this
- ⚠️ WARN if body makes any claim that could be seen as misleading
- ⚠️ WARN if body contains ALL CAPS words (looks spammy)

### Header rules
- ❌ FAIL if header text > 60 characters
- ❌ FAIL if header has variables but no `example` provided
- ❌ FAIL if footer contains variables (footer variables are not supported)

### Footer rules
- ❌ FAIL if footer > 60 characters

### Button rules
- ❌ FAIL if more than 3 QUICK_REPLY buttons
- ❌ FAIL if more than 2 CALL_TO_ACTION buttons (PHONE_NUMBER + URL combined)
- ❌ FAIL if any button text > 25 characters
- ❌ FAIL if QUICK_REPLY and CALL_TO_ACTION buttons are mixed (they cannot coexist)
- ⚠️ WARN if UTILITY template has no buttons — Meta strongly prefers interactive elements for utility messages

### Template name rules
- ❌ FAIL if name contains uppercase letters or spaces
- ❌ FAIL if name is longer than 512 characters
- ⚠️ WARN if the name is very generic (e.g. "message", "notification") — Meta may flag for ambiguity

### Language rules
- ❌ FAIL if language is not a valid BCP-47 code (valid examples: `es`, `es_ES`, `en_US`, `ca`)

### Example values rules
- ❌ FAIL if any `{{N}}` variable in body, header, or buttons lacks a corresponding example value
- ⚠️ WARN if example values look like placeholders ("ejemplo", "test", "xxx") — use realistic values

---

## Step 4 — Report and decide

Present the full risk report:

```
## Rejection Risk: LOW / MEDIUM / HIGH

### Checks
✅ Category: UTILITY — body is transactional, no promotional language
✅ Body length: 87 chars (limit: 1024)
✅ Variables: sequential {{1}}, {{2}}, {{3}} with examples provided
✅ Buttons: 1 QUICK_REPLY within limit
⚠️ WARN: No footer — not required, but common for Noa templates
❌ FAIL: ...

### Verdict
[If LOW/MEDIUM] Template looks approvable. Proceeding to add it.
[If HIGH]       Fix the ❌ FAIL items above before submitting. Suggest fixes.
```

- **LOW risk** (no FAILs, ≤1 WARN): proceed automatically
- **MEDIUM risk** (no FAILs, 2+ WARNs): show report and ask user to confirm before adding
- **HIGH risk** (any FAIL): do NOT add to code — show the failures and suggest a corrected design, then loop back to Step 2

---

## Step 5 — Add to codebase

Once risk is LOW or MEDIUM (with approval):

1. Read `app/messaging/whatsapp_templates.py`
2. Append the new template dict to the `TEMPLATES` list
3. Show the diff

Do not modify anything else in the file.

---

## Step 6 — Sync to Meta

The sync workflow (`sync-wa-templates.yml`) submits all templates in `TEMPLATES` to the Meta Graph API and polls until each is APPROVED or REJECTED. It is triggered manually via CI.

### When to sync

Sync any time `app/messaging/whatsapp_templates.py` changes — new template added, body text edited, buttons changed. No need to sync if only comments or non-template code changed.

### How to trigger

Always ask the user which environment to target (staging or production) before triggering. Default to staging unless explicitly told otherwise.

```bash
# Staging
gh workflow run sync-wa-templates.yml --ref main --field environment=staging

# Production
gh workflow run sync-wa-templates.yml --ref main --field environment=production
```

After triggering, get the run URL and poll until complete:

```bash
# Get the run ID (wait a moment for it to register)
gh run list --workflow=sync-wa-templates.yml --limit=1

# Poll until done
gh run watch <run-id>

# Or check logs if it fails
gh run view <run-id> --log-failed
```

### What the sync does

1. Lists all existing templates in the Meta account
2. For each template in `TEMPLATES`:
   - **Not found** → creates it, waits for approval
   - **Body changed** → updates it, re-submits for approval
   - **Unchanged + APPROVED** → skips
   - **Unchanged + not APPROVED** → waits for approval
3. Polls every 10s up to 300s for all pending templates to reach APPROVED
4. Raises `RuntimeError` if any template is REJECTED — the CI step fails

### If the sync fails with REJECTED

1. Check which template was rejected in the CI logs
2. Run the rejection risk check (Steps 3–4 above) on that template
3. Fix the ❌ FAIL items, commit, push
4. Re-trigger the sync workflow

### Environments

| Environment | Secret names used |
|-------------|------------------|
| staging | `STAGING_WHATSAPP_ACCESS_TOKEN`, `STAGING_WHATSAPP_BUSINESS_ACCOUNT_ID` |
| production | `PRODUCTION_WHATSAPP_ACCESS_TOKEN`, `PRODUCTION_WHATSAPP_BUSINESS_ACCOUNT_ID` |

Both environments use the same template definitions from `TEMPLATES`. There is no per-environment template registry.

---

## Meta policy reference (quick lookup)

| Rule | Limit |
|------|-------|
| Body text | max 1024 chars |
| Header text | max 60 chars |
| Footer text | max 60 chars |
| Button text | max 25 chars |
| QUICK_REPLY buttons | max 3 |
| CTA buttons (phone + URL) | max 2 total |
| Variables must have examples | always |
| QUICK_REPLY + CTA mixed | not allowed |
| Raw URLs in body | not allowed |
| Promotional language in UTILITY | not allowed |
| Template name | lowercase + underscores only |

### Common rejection reasons (from Noa's history)
- Missing `example` values for `{{N}}` variables → always include them
- Asking users to "reply to this message" instead of using a button → use QUICK_REPLY
- Body text that reads like marketing inside a UTILITY template
- URL in body text instead of a URL button
