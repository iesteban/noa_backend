from __future__ import annotations

import re
from typing import Any

from sentry_sdk.types import Event

SENSITIVE_KEYS = {
    "nif",
    "iban",
    "phone_number",
    "phone",
    "access_token",
    "refresh_token",
    "amount",
    "subtotal",
    "total",
    "iva_amount",
    "irpf_amount",
}

_PHONE_RE = re.compile(r"\+?[\d\s\-]{9,15}")
_IBAN_RE = re.compile(r"[A-Z]{2}\d{2}[\d\s]{11,27}")
_NIF_RE = re.compile(r"\b\d{8}[A-Z]\b|\b[A-Z]\d{7}[A-Z]\b")


def _scrub_str(value: str) -> str:
    value = _IBAN_RE.sub("[IBAN]", value)
    value = _NIF_RE.sub("[NIF]", value)
    value = _PHONE_RE.sub("[PHONE]", value)
    return value


def _scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if k.lower() in SENSITIVE_KEYS else _scrub(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_scrub(item) for item in obj]
    if isinstance(obj, str):
        return _scrub_str(obj)
    return obj


def scrub_sensitive_data(event: Event, hint: dict[str, Any]) -> Event | None:
    if "request" in event:
        if "data" in event["request"]:
            event["request"]["data"] = _scrub(event["request"]["data"])
        event["request"].pop("headers", None)

    if "extra" in event:
        event["extra"] = _scrub(event["extra"])

    return event
