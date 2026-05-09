"""Integration tests for the WhatsApp webhook endpoint.

Twilio signature validation is bypassed via FastAPI dependency override so tests
don't need real Twilio credentials or a live request URL.

HTTP-level tests mock _handle_whatsapp_update to avoid event-loop conflicts from
_dispatch's internal async_session_factory; routing and session logic is exercised
in test_routing.py and test_onboarding.py via the db fixture.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.webhook import _validate_twilio_signature
from app.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client() -> TestClient:
    """TestClient with Twilio signature validation disabled."""
    app.dependency_overrides[_validate_twilio_signature] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def _form(from_number: str = "+34600000001", body: str = "Hola", **extra: str) -> dict[str, str]:
    return {
        "MessageSid": "SM" + "a" * 32,
        "From": f"whatsapp:{from_number}",
        "To": "whatsapp:+14155238886",
        "Body": body,
        "NumMedia": "0",
        **extra,
    }


# ---------------------------------------------------------------------------
# HTTP-level checks
# ---------------------------------------------------------------------------

class TestWebhookHTTP:
    def test_valid_request_returns_200(self, client: TestClient) -> None:
        with patch("app.api.webhook._handle_whatsapp_update", new_callable=AsyncMock):
            response = client.post("/whatsapp", data=_form())
        assert response.status_code == 200

    def test_response_body_is_ok(self, client: TestClient) -> None:
        with patch("app.api.webhook._handle_whatsapp_update", new_callable=AsyncMock):
            response = client.post("/whatsapp", data=_form())
        assert response.json() == {"ok": "true"}

    def test_handle_whatsapp_update_called_for_text(self, client: TestClient) -> None:
        with patch("app.api.webhook._handle_whatsapp_update") as mock_handle:
            client.post("/whatsapp", data=_form(body="Necesito una factura"))
            mock_handle.assert_called_once()

    def test_handle_whatsapp_update_called_for_voice(self, client: TestClient) -> None:
        with patch("app.api.webhook._handle_whatsapp_update") as mock_handle:
            client.post(
                "/whatsapp",
                data=_form(
                    body="",
                    NumMedia="1",
                    MediaUrl0="https://api.twilio.com/v1/voice.ogg",
                    MediaContentType0="audio/ogg",
                ),
            )
            mock_handle.assert_called_once()

    def test_webhook_parses_from_number(self, client: TestClient) -> None:
        """The TwilioWebhook passed to _handle_whatsapp_update has the correct From."""
        with patch("app.api.webhook._handle_whatsapp_update") as mock_handle:
            client.post("/whatsapp", data=_form(from_number="+34611223344"))
            webhook_arg = mock_handle.call_args[0][0]
            assert webhook_arg.from_number == "whatsapp:+34611223344"


# ---------------------------------------------------------------------------
# Signature validation
# ---------------------------------------------------------------------------

class TestSignatureValidation:
    def test_missing_signature_returns_403(self) -> None:
        plain_client = TestClient(app)
        with patch("app.api.webhook.settings") as mock_settings:
            mock_settings.twilio_auth_token = "test-token"
            response = plain_client.post("/whatsapp", data=_form())
        assert response.status_code == 403

    def test_wrong_signature_returns_403(self) -> None:
        plain_client = TestClient(app)
        with patch("app.api.webhook.settings") as mock_settings:
            mock_settings.twilio_auth_token = "test-token"
            response = plain_client.post(
                "/whatsapp",
                data=_form(),
                headers={"X-Twilio-Signature": "bad-signature"},
            )
        assert response.status_code == 403
