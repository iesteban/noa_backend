"""Unit tests for app.core.sentry — scrub_sensitive_data()."""
from __future__ import annotations

from app.core.sentry import scrub_sensitive_data


def _event(**extra: object) -> dict:  # type: ignore[type-arg]
    return {"extra": extra} if extra else {}


# ---------------------------------------------------------------------------
# _scrub — dict key matching
# ---------------------------------------------------------------------------

def test_sensitive_key_redacted() -> None:
    event = {"request": {"data": {"nif": "12345678A", "name": "Pedro"}}}
    result = scrub_sensitive_data(event, {})
    assert result["request"]["data"]["nif"] == "[REDACTED]"
    assert result["request"]["data"]["name"] == "Pedro"


def test_all_sensitive_keys_redacted() -> None:
    sensitive = {
        "iban": "ES91 2100 0418 4502 0005 1332",
        "phone_number": "+34600123456",
        "phone": "+34600123456",
        "access_token": "tok_abc",
        "refresh_token": "rtok_abc",
        "amount": "120.00",
        "subtotal": "100.00",
        "total": "121.00",
        "iva_amount": "21.00",
        "irpf_amount": "15.00",
    }
    event = {"request": {"data": sensitive}}
    result = scrub_sensitive_data(event, {})
    for key in sensitive:
        assert result["request"]["data"][key] == "[REDACTED]", f"Key {key!r} not redacted"


def test_nested_dict_scrubbed() -> None:
    event = {"request": {"data": {"client": {"nif": "12345678A", "city": "Madrid"}}}}
    result = scrub_sensitive_data(event, {})
    assert result["request"]["data"]["client"]["nif"] == "[REDACTED]"
    assert result["request"]["data"]["client"]["city"] == "Madrid"


def test_list_values_scrubbed() -> None:
    event = {"request": {"data": {"items": [{"nif": "12345678A"}, {"name": "Ana"}]}}}
    result = scrub_sensitive_data(event, {})
    assert result["request"]["data"]["items"][0]["nif"] == "[REDACTED]"
    assert result["request"]["data"]["items"][1]["name"] == "Ana"


# ---------------------------------------------------------------------------
# _scrub_str — pattern matching in free-form strings
# ---------------------------------------------------------------------------

def test_nif_pattern_scrubbed_in_string() -> None:
    event = {"extra": {"msg": "Error for NIF 12345678A in DB"}}
    result = scrub_sensitive_data(event, {})
    assert "[NIF]" in result["extra"]["msg"]
    assert "12345678A" not in result["extra"]["msg"]


def test_iban_pattern_scrubbed_in_string() -> None:
    event = {"extra": {"msg": "Transfer to ES91 2100 0418 4502 0005 1332 failed"}}
    result = scrub_sensitive_data(event, {})
    assert "[IBAN]" in result["extra"]["msg"]
    assert "ES91" not in result["extra"]["msg"]


def test_phone_pattern_scrubbed_in_string() -> None:
    event = {"extra": {"msg": "Call from +34600123456"}}
    result = scrub_sensitive_data(event, {})
    assert "[PHONE]" in result["extra"]["msg"]
    assert "+34600123456" not in result["extra"]["msg"]


# ---------------------------------------------------------------------------
# request.headers removed
# ---------------------------------------------------------------------------

def test_request_headers_removed() -> None:
    event = {
        "request": {
            "data": {},
            "headers": {"Authorization": "Bearer secret", "Content-Type": "application/json"},
        }
    }
    result = scrub_sensitive_data(event, {})
    assert "headers" not in result["request"]


# ---------------------------------------------------------------------------
# event without request / extra passes through unchanged
# ---------------------------------------------------------------------------

def test_event_without_sensitive_fields_unchanged() -> None:
    event: dict = {"message": "hello", "level": "info"}
    result = scrub_sensitive_data(event, {})
    assert result == {"message": "hello", "level": "info"}


def test_non_sensitive_request_data_unchanged() -> None:
    event = {"request": {"data": {"job_id": "abc-123", "description": "Fixed pipe"}}}
    result = scrub_sensitive_data(event, {})
    assert result["request"]["data"] == {"job_id": "abc-123", "description": "Fixed pipe"}
