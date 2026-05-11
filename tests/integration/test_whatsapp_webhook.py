"""Integration tests for the WhatsApp (Meta) webhook endpoint.

Signature validation is skipped when WHATSAPP_APP_SECRET is empty (the default in tests).
HTTP-level tests mock _handle_whatsapp_update to avoid event-loop conflicts from
_dispatch's internal async_session_factory; routing and session logic is exercised
in test_routing.py and test_onboarding.py via the db fixture.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _payload(
    from_number: str = "34600000001",
    body: str = "Hola",
    msg_type: str = "text",
    media_id: str | None = None,
) -> dict:
    message: dict = {
        "from": from_number,
        "id": "wamid.abc123",
        "timestamp": "1700000000",
        "type": msg_type,
    }
    if msg_type == "text":
        message["text"] = {"body": body}
    elif msg_type == "audio":
        message["audio"] = {
                "id": media_id or "media-id-1", "mime_type": "audio/ogg; codecs=opus", "voice": True
            }
    elif msg_type == "image":
        message["image"] = {"id": media_id or "media-id-2", "mime_type": "image/jpeg"}

    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "waba-id",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "messages": [message],
                },
                "field": "messages",
            }],
        }],
    }


# ---------------------------------------------------------------------------
# Webhook verification (GET)
# ---------------------------------------------------------------------------

class TestWebhookVerification:
    def test_valid_verify_token_returns_challenge(self, client: TestClient) -> None:
        with patch("app.api.webhook.settings") as mock_settings:
            mock_settings.whatsapp_verify_token = "my-verify-token"
            response = client.get(
                "/whatsapp",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "my-verify-token",
                    "hub.challenge": "1234567890",
                },
            )
        assert response.status_code == 200
        assert response.text == "1234567890"

    def test_wrong_verify_token_returns_403(self, client: TestClient) -> None:
        with patch("app.api.webhook.settings") as mock_settings:
            mock_settings.whatsapp_verify_token = "correct-token"
            response = client.get(
                "/whatsapp",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "wrong-token",
                    "hub.challenge": "abc",
                },
            )
        assert response.status_code == 403

    def test_wrong_mode_returns_403(self, client: TestClient) -> None:
        with patch("app.api.webhook.settings") as mock_settings:
            mock_settings.whatsapp_verify_token = "token"
            response = client.get(
                "/whatsapp",
                params={
                    "hub.mode": "unsubscribe",
                    "hub.verify_token": "token",
                    "hub.challenge": "abc",
                },
            )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Message webhook (POST)
# ---------------------------------------------------------------------------

class TestWebhookHTTP:
    def test_valid_request_returns_200(self, client: TestClient) -> None:
        with patch("app.api.webhook._handle_whatsapp_update", new_callable=AsyncMock):
            response = client.post("/whatsapp", json=_payload())
        assert response.status_code == 200

    def test_response_body_is_ok(self, client: TestClient) -> None:
        with patch("app.api.webhook._handle_whatsapp_update", new_callable=AsyncMock):
            response = client.post("/whatsapp", json=_payload())
        assert response.json() == {"ok": "true"}

    def test_handle_called_for_text(self, client: TestClient) -> None:
        with patch("app.api.webhook._handle_whatsapp_update") as mock_handle:
            client.post("/whatsapp", json=_payload(body="Necesito una factura"))
            mock_handle.assert_called_once()

    def test_handle_called_for_voice(self, client: TestClient) -> None:
        with patch("app.api.webhook._handle_whatsapp_update") as mock_handle:
            client.post("/whatsapp", json=_payload(msg_type="audio", media_id="some-media-id"))
            mock_handle.assert_called_once()

    def test_webhook_parses_from_number(self, client: TestClient) -> None:
        with patch("app.api.webhook._handle_whatsapp_update") as mock_handle:
            client.post("/whatsapp", json=_payload(from_number="34611223344"))
            webhook_arg = mock_handle.call_args[0][0]
            assert webhook_arg.entry[0].changes[0].value.messages[0].from_ == "34611223344"

    def test_status_update_accepted_silently(self, client: TestClient) -> None:
        status_payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "waba-id",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "statuses": [{
                            "id": "wamid.xyz", "status": "delivered",
                            "timestamp": "1700000001", "recipient_id": "34600000001",
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }
        with patch("app.api.webhook._handle_whatsapp_update", new_callable=AsyncMock):
            response = client.post("/whatsapp", json=status_payload)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Signature validation
# ---------------------------------------------------------------------------

class TestSignatureValidation:
    def test_missing_signature_returns_403_when_secret_set(self, client: TestClient) -> None:
        with patch("app.api.webhook.settings") as mock_settings:
            mock_settings.whatsapp_app_secret = "my-app-secret"
            response = client.post("/whatsapp", json=_payload())
        assert response.status_code == 403

    def test_wrong_signature_returns_403(self, client: TestClient) -> None:

        body = b'{"object":"test"}'
        with patch("app.api.webhook.settings") as mock_settings:
            mock_settings.whatsapp_app_secret = "my-app-secret"
            response = client.post(
                "/whatsapp",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": "sha256=badhash",
                },
            )
        assert response.status_code == 403

    def test_correct_signature_passes(self, client: TestClient) -> None:
        import hashlib
        import hmac
        import json

        secret = "my-app-secret"
        body = json.dumps(_payload()).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        with patch("app.api.webhook.settings") as mock_settings:
            mock_settings.whatsapp_app_secret = secret
            mock_settings.whatsapp_verify_token = ""
            with patch("app.api.webhook._handle_whatsapp_update", new_callable=AsyncMock):
                response = client.post(
                    "/whatsapp",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Hub-Signature-256": sig,
                    },
                )
        assert response.status_code == 200
