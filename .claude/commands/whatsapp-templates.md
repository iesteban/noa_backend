# WhatsApp Template Skill

Reference for creating, editing, and debugging Meta WhatsApp message templates in this project.
All templates live in `app/messaging/whatsapp_templates.py` under the `TEMPLATES` list.
The sync workflow is `.github/workflows/sync-wa-templates.yml` (manual `workflow_dispatch`).

---

## Template structure

```python
{
    "name": "snake_case_name",          # lowercase, digits, underscores only
    "language": "es",                   # ISO 639-1 code
    "category": "UTILITY",              # UTILITY | MARKETING | AUTHENTICATION
    "components": [
        {"type": "HEADER", ...},        # optional
        {"type": "BODY", ...},          # required
        {"type": "FOOTER", ...},        # optional
        {"type": "BUTTONS", ...},       # optional
    ],
}
```

---

## Components

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
- Do **not** start or end the body text with a variable
- Do **not** place two variables adjacent to each other
- Every variable **must** have a sample value in `example.body_text`
- Markdown formatting is supported: `*bold*`, `_italic_`, `~strikethrough~`

```python
{
    "type": "BODY",
    "text": "Hola {{1}}, {{2}} quiere organizar una cita de {{3}}.",
    "example": {"body_text": [["Ana", "Fontanería García", "fontanería"]]},
}
```

### FOOTER (optional, max 1)

- Max **60 characters**
- Plain text only — no variables, no markdown

```python
{"type": "FOOTER", "text": "Responde STOP para cancelar"}
```

### BUTTONS (optional)

| Type | Max per template | Text limit | Notes |
|------|-----------------|------------|-------|
| QUICK_REPLY | 10 | 25 chars | Sends the button text back as a user message |
| URL | 2 | 25 chars text, 2000 chars URL | Supports 1 variable at end of URL |
| PHONE_NUMBER | 1 | 25 chars | Opens dialer |
| OTP / COPY_CODE | 1 | fixed text | AUTHENTICATION only |

**Rules:**
- Max **10 buttons total** across all types
- Same-type buttons must be grouped consecutively
- OTP buttons cannot be mixed with other button types

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

## Categories

### UTILITY
For messages tied directly to a user action or ongoing transaction — confirmations,
reminders, status updates. **Strictly non-promotional.**

- No offers, upsells, discounts, or persuasive language
- Must relate to a specific transaction (include order/invoice/appointment IDs when relevant)
- Do not ask open-ended availability questions — that triggers auto-rejection
- If a template has any promotional element, Meta auto-reclassifies it as MARKETING

Good UTILITY examples: appointment confirmation, invoice sent, payment received, job logged.

### MARKETING
For promotions, re-engagement, or any message with persuasive intent.
More permissive content rules but requires explicit opt-in from the recipient.

- Use for: promotional offers, seasonal campaigns, renewal nudges, review requests
- Carousel templates (`CAROUSEL` component) are MARKETING only
- `COPY_OFFER_CODE` button type is MARKETING only

### AUTHENTICATION
OTP / verification codes only. Most restricted category.
- No URLs, media, emojis, or variables exceeding 15 characters
- Must use WhatsApp's official OTP template library
- Do not create custom auth templates

---

## Rejection reasons

| Code | Meaning | Fix |
|------|---------|-----|
| `INVALID_FORMAT` | Template structure is malformed | Check component order, variable syntax, character limits. If a body solicits a response, add QUICK_REPLY buttons to declare the expected interaction. |
| `TAG_CONTENT_MISMATCH` | Category doesn't match content | Move promotional content to MARKETING; strip promo language from UTILITY |
| `INVALID_PARAMETER` | Variable syntax wrong | Ensure `{{N}}` notation, sequential numbering, no spaces inside braces |
| `DUPLICATE_TEMPLATE` | Identical body/footer already exists | Change wording or delete the duplicate first |
| `ABUSIVE_CONTENT` | Policy violation | Remove sensitive data requests, illegal content, threatening language |
| `NONE` (with REJECTED status) | Automated content policy catch-all | Simplify body, remove solicitations, add sample values |

**Instant rejection** (within seconds) = automated policy check. Causes: open-ended question
in UTILITY body, body/footer starts or ends with `{{N}}`, missing sample values, adjacent variables.

**Delayed rejection** (hours) = human review. Usually a content policy edge case.

---

## Sample values — mandatory

Meta requires sample values for every variable so reviewers can evaluate the rendered message.
Without them, automated review rejects the template.

```python
{
    "type": "BODY",
    "text": "Hola {{1}}, tu factura {{2}} por {{3}}€ está lista.",
    "example": {
        "body_text": [["Pedro García", "2025-034", "120"]]
    },
}
```

---

## Quality & lifecycle

- **Template pacing**: new or low-quality templates have delivery throttled while Meta collects feedback
- **Quality drops** when users block or report the message — pausing schedule:
  1. First violation → 3-hour pause
  2. Second → 6-hour pause
  3. Third → permanent disable
- **Avoid**: multiple messages to same user in short succession, vague personalization, urgency tactics

---

## Codebase patterns

**Adding a new template:**
1. Add the dict to `TEMPLATES` in `app/messaging/whatsapp_templates.py`
2. Include `example` on every component that has variables
3. Run the sync workflow manually against staging first; poll for `APPROVED` before targeting production
4. If Meta rejects: check `rejected_reason` via:
   ```bash
   source .env.staging && curl -s \
     "https://graph.facebook.com/v19.0/${WHATSAPP_BUSINESS_ACCOUNT_ID}/message_templates\
   ?fields=id,name,status,rejected_reason,components&access_token=${WHATSAPP_ACCESS_TOKEN}" \
     | python3 -m json.tool
   ```

**Sync workflow:**
- `workflow_dispatch` only — trigger manually from GitHub Actions UI or:
  ```bash
  gh workflow run sync-wa-templates.yml --field environment=staging -R iesteban/noa_backend
  ```
- Staging secrets: `STAGING_WHATSAPP_ACCESS_TOKEN` + `STAGING_WHATSAPP_BUSINESS_ACCOUNT_ID`
- Production secrets: `PRODUCTION_WHATSAPP_ACCESS_TOKEN` + `PRODUCTION_WHATSAPP_BUSINESS_ACCOUNT_ID`
- If secrets drift from `.env.*` files, update with `gh secret set`

**Quota:** max 100 templates created per hour per WABA; 6,000 total (verified business).

---

## Approved template reference (staging)

| Name | Category | Status | Notes |
|------|----------|--------|-------|
| `presupuesto_generado` | — | APPROVED | Has HEADER + BODY + QUICK_REPLY button — use as structural reference |
| `appointment_request` | UTILITY | REJECTED (INVALID_FORMAT) | Missing sample values + body structured as open Q&A without buttons |
