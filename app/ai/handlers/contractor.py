"""Tool handler for updating the contractor's own profile."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.dispatcher import register
from app.models.contractor import Contractor
from app.models.session import ConversationSession
from app.services.nif_validation import validate_nif

# Public tool input names accepted by the handler. Each maps 1-to-1 to a
# Contractor attribute name.
_UPDATABLE_TEXT_FIELDS: tuple[str, ...] = (
    "name",
    "business_name",
    "nif",
    "address",
    "iban",
    "email",
)
_UPDATABLE_RATE_FIELDS: tuple[str, ...] = ("iva_rate", "irpf_rate")

# Labels used in the confirmation string (Spanish, matches Layer 3 style).
_FIELD_LABELS_ES: dict[str, str] = {
    "name": "Nombre",
    "business_name": "Negocio",
    "nif": "NIF",
    "address": "Dirección",
    "iban": "IBAN",
    "email": "Email",
    "iva_rate": "IVA",
    "irpf_rate": "IRPF",
}

# Per-field length caps for free-form text. Aligned with the column widths
# defined on the Contractor model: String(255) / Text.
_TEXT_LENGTH_LIMITS: dict[str, int] = {
    "name": 255,
    "business_name": 255,
    "address": 500,
}

# Loose email check — anchored variant of the pattern used in
# services.nif_validation.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


# Sentinels returned by validators. We can't use `None` to signal "no change
# requested" because `None` is also a legitimate value (clear the field).
class _Invalid:
    """Wraps the error message a validator wants to surface to Claude."""

    __slots__ = ("message",)

    def __init__(self, message: str) -> None:
        self.message = message


# A validated value is either the new value to assign (str | float | None),
# or an _Invalid sentinel carrying the error message to send back to Claude.
_Validated = str | float | None | _Invalid


def _parse_iban(raw: object) -> _Validated:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    normalised = re.sub(r"\s+", "", text).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", normalised):
        return _Invalid(
            "IBAN no válido. Debe empezar con dos letras de país, dos dígitos "
            "y entre 11 y 30 caracteres más."
        )
    return normalised


def _parse_nif(raw: object) -> _Validated:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    valid = validate_nif(text)
    if valid is None:
        return _Invalid(f"NIF '{text}' no válido.")
    return valid


def _parse_email(raw: object) -> _Validated:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if not _EMAIL_RE.match(text):
        return _Invalid(f"Email '{text}' no válido.")
    return text


def _parse_text(raw: object, label: str, *, max_length: int) -> _Validated:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if len(text) > max_length:
        return _Invalid(f"{label} es demasiado largo (máximo {max_length} caracteres).")
    return text


def _parse_rate(raw: object, label: str) -> _Validated:
    """Accept 0.21, 21, or '21%' style values; return as fraction (0–1)."""
    if raw is None:
        return _Invalid(f"{label} no puede ser nulo.")
    if isinstance(raw, bool):  # bool is a subclass of int — reject explicitly
        return _Invalid(f"{label} '{raw}' no es un número válido.")
    text = str(raw).strip().rstrip("%").strip()
    try:
        value = float(text)
    except (TypeError, ValueError):
        return _Invalid(f"{label} '{raw}' no es un número válido.")
    if value > 1:
        value = value / 100
    if value < 0 or value > 1:
        return _Invalid(f"{label} debe estar entre 0% y 100%.")
    return round(value, 4)


def _validate_input(tool_input: dict[str, Any]) -> dict[str, object | None] | str:
    """Return either {field: new_value, ...} or an error string for Claude."""
    updates: dict[str, object | None] = {}

    def _take(field: str, parsed: _Validated) -> str | None:
        if isinstance(parsed, _Invalid):
            return parsed.message
        updates[field] = parsed
        return None

    if "nif" in tool_input:
        err = _take("nif", _parse_nif(tool_input["nif"]))
        if err is not None:
            return err
    if "iban" in tool_input:
        err = _take("iban", _parse_iban(tool_input["iban"]))
        if err is not None:
            return err
    if "email" in tool_input:
        err = _take("email", _parse_email(tool_input["email"]))
        if err is not None:
            return err

    for field in ("name", "business_name", "address"):
        if field in tool_input:
            err = _take(
                field,
                _parse_text(
                    tool_input[field],
                    _FIELD_LABELS_ES[field],
                    max_length=_TEXT_LENGTH_LIMITS[field],
                ),
            )
            if err is not None:
                return err

    for field in _UPDATABLE_RATE_FIELDS:
        if field in tool_input:
            err = _take(field, _parse_rate(tool_input[field], _FIELD_LABELS_ES[field]))
            if err is not None:
                return err

    if not updates:
        return (
            "No se ha indicado ningún campo a actualizar. "
            "Especifica al menos uno de: "
            f"{', '.join(_UPDATABLE_TEXT_FIELDS + _UPDATABLE_RATE_FIELDS)}."
        )

    if "name" in updates and updates["name"] is None:
        return "El nombre es obligatorio y no puede borrarse."

    return updates


def _format_value(field: str, value: object) -> str:
    if field in _UPDATABLE_RATE_FIELDS and isinstance(value, (int, float)):
        return f"{float(value) * 100:.0f}%"
    return str(value)


def _format_summary(updates: dict[str, object | None]) -> str:
    lines = ["Perfil actualizado:"]
    for field, value in updates.items():
        label = _FIELD_LABELS_ES.get(field, field)
        if value is None:
            lines.append(f"  {label}: (sin definir)")
        else:
            lines.append(f"  {label}: {_format_value(field, value)}")
    return "\n".join(lines)


@register("update_contractor")
async def handle_update_contractor(
    tool_input: dict[str, Any],
    db: AsyncSession,
    session: ConversationSession,
) -> str:
    """Update the contractor's own profile.

    Accepts any subset of: name, business_name, nif, address, iban, email,
    iva_rate, irpf_rate. The caller (Claude) is expected to have shown a
    summary and obtained confirmation before invoking this tool.
    """
    if session.contractor_id is None:
        return "Session error: contractor not identified."

    contractor = await db.get(Contractor, session.contractor_id)
    if contractor is None:
        return "Contractor no encontrado."

    validated = _validate_input(tool_input)
    if isinstance(validated, str):
        return validated

    for field, value in validated.items():
        setattr(contractor, field, value)
    await db.flush()

    return _format_summary(validated)
