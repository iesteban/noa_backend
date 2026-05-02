from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

SECRET = "test-secret"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    mock_settings = MagicMock()
    mock_settings.telegram_webhook_secret = SECRET
    monkeypatch.setattr("app.api.webhook.settings", mock_settings)
    # _handle_telegram_update is async and touches DB + Telegram API; stub it out so
    # tests that check HTTP behaviour don't need a real database or network.
    monkeypatch.setattr("app.api.webhook._handle_telegram_update", AsyncMock())
    return TestClient(app)


def _text_update(update_id: int = 1, text: str = "Hola") -> dict:  # type: ignore[type-arg]
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "from": {"id": 999, "first_name": "Pedro"},
            "chat": {"id": 111, "type": "private"},
            "date": 0,
            "text": text,
        },
    }


class TestSecretTokenValidation:
    def test_valid_secret_returns_200(self, client: TestClient) -> None:
        response = client.post(
            "/telegram",
            json=_text_update(),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )
        assert response.status_code == 200

    def test_missing_secret_returns_403(self, client: TestClient) -> None:
        response = client.post("/telegram", json=_text_update())
        assert response.status_code == 403

    def test_wrong_secret_returns_403(self, client: TestClient) -> None:
        response = client.post(
            "/telegram",
            json=_text_update(),
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )
        assert response.status_code == 403


class TestResponseShape:
    def test_returns_ok(self, client: TestClient) -> None:
        response = client.post(
            "/telegram",
            json=_text_update(),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )
        assert response.json() == {"ok": "true"}


class TestBackgroundDispatch:
    def test_handle_telegram_update_called_for_text(self, client: TestClient) -> None:
        with patch("app.api.webhook._handle_telegram_update") as mock_handle:
            client.post(
                "/telegram",
                json=_text_update(),
                headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
            )
            mock_handle.assert_called_once()
            update_arg = mock_handle.call_args[0][0]
            assert update_arg.update_id == 1

    def test_handle_telegram_update_called_for_voice(self, client: TestClient) -> None:
        payload = {
            "update_id": 2,
            "message": {
                "message_id": 2,
                "chat": {"id": 111, "type": "private"},
                "date": 0,
                "voice": {"file_id": "v1", "file_unique_id": "vu1", "duration": 4},
            },
        }
        with patch("app.api.webhook._handle_telegram_update") as mock_handle:
            client.post(
                "/telegram",
                json=payload,
                headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
            )
            mock_handle.assert_called_once()

    def test_handle_telegram_update_called_for_photo(self, client: TestClient) -> None:
        payload = {
            "update_id": 3,
            "message": {
                "message_id": 3,
                "chat": {"id": 111, "type": "private"},
                "date": 0,
                "photo": [{"file_id": "p1", "file_unique_id": "pu1", "width": 100, "height": 100}],
            },
        }
        with patch("app.api.webhook._handle_telegram_update") as mock_handle:
            client.post(
                "/telegram",
                json=payload,
                headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
            )
            mock_handle.assert_called_once()


class TestUnhandledUpdateTypes:
    def test_update_without_message_does_not_crash(self, client: TestClient) -> None:
        payload = {"update_id": 99}
        response = client.post(
            "/telegram",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )
        assert response.status_code == 200

    def test_unknown_message_content_does_not_crash(self, client: TestClient) -> None:
        payload = {
            "update_id": 100,
            "message": {
                "message_id": 5,
                "chat": {"id": 111, "type": "private"},
                "date": 0,
            },
        }
        response = client.post(
            "/telegram",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )
        assert response.status_code == 200
