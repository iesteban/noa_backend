from __future__ import annotations

import io
import logging

import httpx
import openai

from app.config import settings

logger = logging.getLogger(__name__)

_GRAPH_API = "https://graph.facebook.com/v19.0"
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_WHISPER_MODEL = "whisper-large-v3-turbo"

_groq: openai.AsyncOpenAI | None = None


def _get_groq() -> openai.AsyncOpenAI:
    global _groq
    if _groq is None:
        _groq = openai.AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url=_GROQ_BASE_URL,
        )
    return _groq


async def _resolve_telegram_file_url(file_id: str) -> str:
    """Call Telegram getFile and return the authenticated download URL."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/getFile",
            params={"file_id": file_id},
        )
        r.raise_for_status()
        file_path: str = r.json()["result"]["file_path"]
    return f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"


async def _transcribe(audio_bytes: bytes) -> str:
    response = await _get_groq().audio.transcriptions.create(
        model=_WHISPER_MODEL,
        file=("voice.ogg", io.BytesIO(audio_bytes)),
        language="es",
    )
    logger.info("Whisper transcribed %d bytes: %r", len(audio_bytes), response.text[:80])
    return response.text


async def transcribe(file_id: str) -> tuple[str, str]:
    """Download a Telegram voice note and transcribe it with Whisper.

    Returns (transcription_text, voice_url).
    Raises on network or API failure — caller is responsible for the fallback.
    """
    voice_url = await _resolve_telegram_file_url(file_id)
    async with httpx.AsyncClient() as client:
        r = await client.get(voice_url)
        r.raise_for_status()
        audio_bytes = r.content
    return await _transcribe(audio_bytes), voice_url


async def transcribe_from_meta(media_id: str) -> tuple[str, str]:
    """Resolve a Meta media ID, download the audio, and transcribe with Whisper.

    Meta requires two steps: fetch the media URL first, then download with Bearer auth.
    Returns (transcription_text, media_url).
    Raises on network or API failure — caller is responsible for the fallback.
    """
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{_GRAPH_API}/{media_id}", headers=headers)
        r.raise_for_status()
        media_url: str = r.json()["url"]

        r = await client.get(media_url, headers=headers)
        r.raise_for_status()
        audio_bytes = r.content

    return await _transcribe(audio_bytes), media_url
