from __future__ import annotations

import re

# Shared contact-parsing helpers used by all channel parsers (Telegram, WhatsApp, …).
# Each channel parser extracts (name, phones) in its own way, then calls
# format_contact_text() to produce a consistent string for Claude.

_VCARD_TYPE_LABELS: dict[str, str] = {
    "cell": "móvil",
    "mobile": "móvil",
    "work": "trabajo",
    "home": "casa",
    "main": "principal",
}


def parse_vcard_phones(vcard: str) -> list[tuple[str, str]]:
    """Return (number, label) pairs from vCard TEL entries."""
    results = []
    for line in vcard.splitlines():
        if not line.upper().startswith("TEL"):
            continue
        colon = line.find(":")
        if colon == -1:
            continue
        number = re.sub(r"[\s\-\(\)]", "", line[colon + 1:]).strip()
        if not number:
            continue
        type_match = re.search(r"TYPE=([^;:]+)", line, re.IGNORECASE)
        raw_types = type_match.group(1).lower().split(",") if type_match else []
        label = next(
            (_VCARD_TYPE_LABELS[t] for t in raw_types if t in _VCARD_TYPE_LABELS),
            "teléfono",
        )
        results.append((number, label))
    return results


def format_contact_text(name: str, phones: list[tuple[str, str]]) -> str:
    """Format a contact into the descriptive text Claude receives.

    Single phone  → "Nombre: X\nTeléfono: Y"
    Multiple phones → numbered list so Claude can ask which one to use.
    """
    if len(phones) == 1:
        number, _ = phones[0]
        return f"[Contacto compartido]\nNombre: {name}\nTeléfono: {number}"

    lines = [f"[Contacto compartido]\nNombre: {name}\nTeléfonos disponibles:"]
    for i, (number, label) in enumerate(phones, 1):
        lines.append(f"  {i}. {number} ({label})")
    return "\n".join(lines)
