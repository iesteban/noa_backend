"""Unit tests for the Whisper transcription module."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.ai.whisper as whisper_module
from app.ai.whisper import transcribe
from app.messaging.types import InboundMessage, MessageType


@pytest.fixture(autouse=True)
def reset_openai_client() -> None:
    """Ensure the module-level client is reset between tests."""
    whisper_module._openai = None
    yield  # type: ignore[misc]
    whisper_module._openai = None


def _mock_httpx_get(responses: list[MagicMock]) -> MagicMock:
    """Return a context-manager mock that yields responses in order."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=responses)
    return mock_client


def _file_response(file_path: str = "voice/abc.oga") -> MagicMock:
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json.return_value = {"result": {"file_path": file_path}}
    return r


def _audio_response(content: bytes = b"fake-audio") -> MagicMock:
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.content = content
    return r


class TestTranscribe:
    async def test_returns_transcription_and_url(self) -> None:
        mock_openai = AsyncMock()
        mock_openai.audio.transcriptions.create = AsyncMock(
            return_value=MagicMock(text="Añade a Ana García, teléfono 600123456")
        )
        whisper_module._openai = mock_openai

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.side_effect = [
                _mock_httpx_get([_file_response("voice/abc.oga")]),
                _mock_httpx_get([_audio_response(b"audio-data")]),
            ]
            text, url = await transcribe("file_id_123")

        assert text == "Añade a Ana García, teléfono 600123456"
        assert "voice/abc.oga" in url

    async def test_url_contains_bot_token(self) -> None:
        mock_openai = AsyncMock()
        mock_openai.audio.transcriptions.create = AsyncMock(
            return_value=MagicMock(text="hola")
        )
        whisper_module._openai = mock_openai

        with patch("httpx.AsyncClient") as mock_cls, \
             patch("app.ai.whisper.settings") as mock_settings:
            mock_settings.telegram_bot_token = "MY_TOKEN"
            mock_settings.openai_api_key = "sk-test"
            mock_cls.side_effect = [
                _mock_httpx_get([_file_response("voice/xyz.oga")]),
                _mock_httpx_get([_audio_response()]),
            ]
            _, url = await transcribe("file_id_abc")

        assert "MY_TOKEN" in url
        assert "voice/xyz.oga" in url

    async def test_whisper_called_with_correct_params(self) -> None:
        mock_openai = AsyncMock()
        mock_create = AsyncMock(return_value=MagicMock(text="transcripción"))
        mock_openai.audio.transcriptions.create = mock_create
        whisper_module._openai = mock_openai

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.side_effect = [
                _mock_httpx_get([_file_response()]),
                _mock_httpx_get([_audio_response(b"real-audio")]),
            ]
            await transcribe("fid")

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "whisper-1"
        assert call_kwargs["language"] == "es"
        filename, bio = call_kwargs["file"]
        assert filename == "voice.ogg"
        assert bio.read() == b"real-audio"

    async def test_raises_on_telegram_api_failure(self) -> None:
        import httpx as httpx_lib

        with patch("httpx.AsyncClient") as mock_cls:
            bad_response = MagicMock()
            bad_response.raise_for_status.side_effect = httpx_lib.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock()
            )
            mock_cls.side_effect = [_mock_httpx_get([bad_response])]
            with pytest.raises(httpx_lib.HTTPStatusError):
                await transcribe("bad_file_id")

    async def test_raises_on_whisper_api_failure(self) -> None:
        mock_openai = AsyncMock()
        mock_openai.audio.transcriptions.create = AsyncMock(
            side_effect=Exception("Whisper API error")
        )
        whisper_module._openai = mock_openai

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.side_effect = [
                _mock_httpx_get([_file_response()]),
                _mock_httpx_get([_audio_response()]),
            ]
            with pytest.raises(Exception, match="Whisper API error"):
                await transcribe("fid")


class TestDispatchVoiceFallback:
    """Test that _dispatch sends a fallback message when transcription fails."""

    def _voice_inbound(self) -> InboundMessage:
        return InboundMessage(
            update_id=1,
            recipient_id="111",
            phone_number=None,
            message_type=MessageType.voice,
            text=None,
            file_id="voice_file_id",
        )

    def _db_ctx(self) -> AsyncMock:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        return mock_session

    async def test_fallback_message_on_transcription_error(self) -> None:
        from app.api.webhook import _dispatch

        mock_send = AsyncMock()

        with patch("app.api.webhook.transcribe", side_effect=Exception("fail")), \
             patch("app.api.webhook.resolve_routing") as mock_routing, \
             patch("app.api.webhook.get_or_create_session", return_value=MagicMock(id="sid")), \
             patch("app.api.webhook.async_session_factory", return_value=self._db_ctx()):
            mock_routing.return_value = MagicMock(
                user_type="contractor", candidates=[], contractor_id="some-id"
            )
            await _dispatch(self._voice_inbound(), mock_send, "telegram")

        mock_send.assert_called_once()
        message_sent = mock_send.call_args[0][1]
        assert "transcribir" in message_sent or "escribirlo" in message_sent

    async def test_voice_text_passed_to_claude(self) -> None:
        from app.api.webhook import _dispatch

        mock_send = AsyncMock()
        mock_session = MagicMock(id="sid")
        mock_session.context = {}

        with patch("app.api.webhook.transcribe", return_value=("Añade a Juan", "https://tg/v")), \
             patch("app.api.webhook.resolve_routing") as mock_routing, \
             patch("app.api.webhook.get_or_create_session", return_value=mock_session), \
             patch("app.api.webhook.get_last_assistant_message", return_value=None), \
             patch("app.api.webhook.append_message") as mock_append, \
             patch("app.api.webhook.call_claude", return_value="ok") as mock_claude, \
             patch("app.api.webhook.async_session_factory", return_value=self._db_ctx()):
            mock_routing.return_value = MagicMock(
                user_type="contractor", candidates=[], contractor_id="some-id"
            )
            await _dispatch(self._voice_inbound(), mock_send, "telegram")

        mock_claude.assert_called_once()
        assert mock_claude.call_args[0][2] == "Añade a Juan"
        # append_message(db, session_id, role, content, media_url=...)
        user_append = mock_append.call_args_list[0]
        assert user_append[0][3] == "Añade a Juan"
        assert user_append[1]["media_url"] == "https://tg/v"
