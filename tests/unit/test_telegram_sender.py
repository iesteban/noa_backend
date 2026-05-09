"""Unit tests for app.messaging.telegram_sender."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_calls_telegram_api(self) -> None:
        mock_response = MagicMock()
        mock_response.is_success = True

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with (
            patch("app.messaging.telegram_sender.httpx.AsyncClient", return_value=mock_client),
            patch("app.messaging.telegram_sender.settings") as mock_settings,
        ):
            mock_settings.telegram_bot_token = "test-token"

            from app.messaging.telegram_sender import send_message

            await send_message(recipient_id="111", text="Hola")

        mock_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sends_correct_chat_id_and_text(self) -> None:
        mock_response = MagicMock()
        mock_response.is_success = True

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with (
            patch("app.messaging.telegram_sender.httpx.AsyncClient", return_value=mock_client),
            patch("app.messaging.telegram_sender.settings") as mock_settings,
        ):
            mock_settings.telegram_bot_token = "test-token"

            from app.messaging.telegram_sender import send_message

            await send_message(recipient_id="111", text="Recibido")

        _, kwargs = mock_client.post.call_args
        payload = kwargs.get("json", {})
        assert payload["chat_id"] == 111
        assert payload["text"] == "Recibido"

    @pytest.mark.asyncio
    async def test_url_contains_bot_token(self) -> None:
        mock_response = MagicMock()
        mock_response.is_success = True

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with (
            patch("app.messaging.telegram_sender.httpx.AsyncClient", return_value=mock_client),
            patch("app.messaging.telegram_sender.settings") as mock_settings,
        ):
            mock_settings.telegram_bot_token = "my-secret-token"

            from app.messaging.telegram_sender import send_message

            await send_message(recipient_id="111", text="hi")

        url = mock_client.post.call_args[0][0]
        assert "my-secret-token" in url

    @pytest.mark.asyncio
    async def test_logs_error_on_failure(self) -> None:
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with (
            patch("app.messaging.telegram_sender.httpx.AsyncClient", return_value=mock_client),
            patch("app.messaging.telegram_sender.settings") as mock_settings,
            patch("app.messaging.telegram_sender.logger") as mock_logger,
        ):
            mock_settings.telegram_bot_token = "test-token"

            from app.messaging.telegram_sender import send_message

            await send_message(recipient_id="111", text="hi")

        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_exception_on_api_failure(self) -> None:
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with (
            patch("app.messaging.telegram_sender.httpx.AsyncClient", return_value=mock_client),
            patch("app.messaging.telegram_sender.settings") as mock_settings,
            patch("app.messaging.telegram_sender.logger"),
        ):
            mock_settings.telegram_bot_token = "test-token"

            from app.messaging.telegram_sender import send_message

            # Must not raise
            await send_message(recipient_id="111", text="hi")
