"""Spanish NIF/NIE/CIF validation and data extraction from free-form text."""
from __future__ import annotations

import re

_NIF_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"

# Patterns intentionally loose on the letter so the checksum decides validity.
_DNI_RE = re.compile(r'\b(\d{8})([A-Za-z])\b')
_NIE_RE = re.compile(r'\b([XYZxyz])(\d{7})([A-Za-z])\b')
# CIF: letter (A-H, J-N, P, Q, R, S, U, V, W) + 7 digits + check char
_CIF_RE = re.compile(r'\b([A-HJ-NP-SU-Wa-hj-np-su-w])(\d{7})([0-9A-Ja-j])\b')
_EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')

# Label prefixes to strip when extracting address from mixed text.
_LABEL_RE = re.compile(
    r'(?i)\b(mi\s+)?(nif|cif|nie|dni)\s*[:=]?\s*',
)
_ADDR_PREFIX_RE = re.compile(
    r'(?i)\b(direcci[oó]n|domicilio|vivo\s+en|mi\s+direcci[oó]n\s+es)\s*[:=,]?\s*'
)


def validate_nif(text: str) -> str | None:
    """Return a normalised NIF/NIE/CIF found in *text*, or None if none is valid."""
    # DNI: 8 digits + checksum letter
    for m in _DNI_RE.finditer(text):
        number, letter = m.group(1), m.group(2).upper()
        if letter == _NIF_LETTERS[int(number) % 23]:
            return f"{number}{letter}"

    # NIE: X/Y/Z + 7 digits + checksum letter
    for m in _NIE_RE.finditer(text):
        prefix, digits, letter = m.group(1).upper(), m.group(2), m.group(3).upper()
        substitute = {"X": "0", "Y": "1", "Z": "2"}[prefix]
        if letter == _NIF_LETTERS[int(substitute + digits) % 23]:
            return f"{prefix}{digits}{letter}"

    # CIF: format check only (checksum algorithm is complex; Meta won't reject on content)
    for m in _CIF_RE.finditer(text):
        return m.group(0).upper()

    return None


def extract_emails(text: str) -> list[str]:
    return _EMAIL_RE.findall(text)


def extract_address(text: str) -> str | None:
    """Strip NIF/email patterns and common labels; return an address candidate or None."""
    cleaned = text
    cleaned = _DNI_RE.sub(" ", cleaned)
    cleaned = _NIE_RE.sub(" ", cleaned)
    cleaned = _CIF_RE.sub(" ", cleaned)
    cleaned = _EMAIL_RE.sub(" ", cleaned)
    cleaned = _LABEL_RE.sub(" ", cleaned)
    cleaned = _ADDR_PREFIX_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(",").strip()
    return cleaned if len(cleaned) >= 10 else None
