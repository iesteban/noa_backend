from __future__ import annotations

import io
import logging

import httpx
import openai

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level client — created once and reused across requests.
_openai: openai.AsyncOpenAI | None = None


def _get_openai() -> openai.AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai


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


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


async def transcribe(file_id: str) -> tuple[str, str]:
    """Download a Telegram voice note and transcribe it with Whisper.

    Returns (transcription_text, voice_url).
    Raises on network or API failure — caller is responsible for the fallback.
    """
    voice_url = await _resolve_telegram_file_url(file_id)
    audio_bytes = await _download(voice_url)

    response = await _get_openai().audio.transcriptions.create(
        model="whisper-1",
        file=("voice.ogg", io.BytesIO(audio_bytes)),
        language="es",
    )
    logger.info("Whisper transcribed %d bytes: %r", len(audio_bytes), response.text[:80])
    return response.text, voice_url
