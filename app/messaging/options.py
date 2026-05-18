from __future__ import annotations

import re

# Matches a parenthesized list of slash-separated options at the end of a string.
# e.g. "(Sí / No / Editar)" or "(Agendar / Rechazar)"
_PAREN_OPTS = re.compile(r"\(([^)]+(?:\s*/\s*[^)]+)+)\)\s*$")

# Matches a single numbered list line: "1. Some text"
_NUMBERED = re.compile(r"^\d+\.\s+(.+)$")


def parse_options(text: str) -> tuple[str, list[str] | None]:
    """Extract button options from Claude's text output.

    Detects two patterns and strips them from the returned text:

    1. Parenthesised slash list at end of last line:
       "¿Lo guardo? (Sí / No / Editar)"
       → ("¿Lo guardo?", ["Sí", "No", "Editar"])

    2. Trailing numbered lines:
       "¿Cuál Pedro?\\n1. Pedro Mejuto\\n2. Pedro Sánchez"
       → ("¿Cuál Pedro?", ["Pedro Mejuto", "Pedro Sánchez"])

    Returns (text, None) when no pattern is found.
    """
    # Pattern 1: trailing (A / B / C)
    m = _PAREN_OPTS.search(text)
    if m:
        options = [o.strip() for o in m.group(1).split("/") if o.strip()]
        if len(options) >= 2:
            return text[: m.start()].rstrip(), options

    # Pattern 2: trailing numbered lines (need at least 2 consecutive)
    lines = text.splitlines()
    split = len(lines)
    while split > 0 and _NUMBERED.match(lines[split - 1].strip()):
        split -= 1
    numbered = lines[split:]
    if len(numbered) >= 2:
        options = [_NUMBERED.match(ln.strip()).group(1) for ln in numbered]  # type: ignore[union-attr]
        return "\n".join(lines[:split]).rstrip(), options

    return text, None
