import logging

import sentry_sdk
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from twilio.request_validator import RequestValidator

from app.ai.claude import call_claude
from app.ai.whisper import transcribe, transcribe_from_url
from app.config import settings
from app.database import async_session_factory
from app.messaging.parser import parse_update
from app.messaging.telegram_sender import send_message as telegram_send
from app.messaging.types import InboundMessage, MessageSender, MessageType
from app.messaging.whatsapp_parser import parse_whatsapp
from app.messaging.whatsapp_sender import send_message as whatsapp_send
from app.models.session import MessageRole
from app.schemas.telegram import TelegramUpdate
from app.schemas.whatsapp import TwilioWebhook
from app.services.onboarding import handle_onboarding_message
from app.services.routing import resolve_routing
from app.services.session import append_message, get_or_create_session

logger = logging.getLogger(__name__)
router = APIRouter()


async def _dispatch(inbound: InboundMessage, send: MessageSender, channel: str) -> None:
    logger.info(
        "Dispatching update %d: type=%s recipient=%s",
        inbound.update_id,
        inbound.message_type,
        inbound.recipient_id,
    )

    async with async_session_factory() as db:
        telegram_chat_id = inbound.recipient_id if channel == "telegram" else None
        routing = await resolve_routing(db, telegram_chat_id, inbound.phone_number)

        if routing.user_type is None:
            if routing.candidates:
                lines = "\n".join(
                    f"{i + 1}. {name}" for i, (_, name) in enumerate(routing.candidates)
                )
                await send(inbound.recipient_id, f"¿Con quién quieres contactar?\n{lines}")
            else:
                reply = await handle_onboarding_message(
                    db, inbound.recipient_id, channel, inbound.text
                )
                await send(inbound.recipient_id, reply)
            return

        session = await get_or_create_session(
            db,
            session_key=inbound.recipient_id,
            channel=channel,
            routing=routing,
        )

        text = inbound.text or ""
        media_url: str | None = None

        if inbound.message_type == MessageType.voice and inbound.file_id:
            try:
                if channel == "telegram":
                    text, media_url = await transcribe(inbound.file_id)
                else:
                    text, media_url = await transcribe_from_url(
                        inbound.file_id,
                        auth=(settings.twilio_api_key, settings.twilio_api_secret),
                    )
            except Exception as exc:
                sentry_sdk.capture_exception(exc)
                logger.exception("Whisper transcription failed for file_id %s", inbound.file_id)
                await send(
                    inbound.recipient_id,
                    "No he podido transcribir el audio. ¿Puedes escribirlo?",
                )
                return

        await append_message(db, session.id, MessageRole.user, text, media_url=media_url)

        reply = await call_claude(db, session, text)

        await append_message(db, session.id, MessageRole.assistant, reply)
        await send(inbound.recipient_id, reply)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

async def _handle_telegram_update(update: TelegramUpdate) -> None:
    inbound = parse_update(update)
    if inbound is None:
        return
    await _dispatch(inbound, telegram_send, "telegram")


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    body = await request.json()
    update = TelegramUpdate.model_validate(body)
    background_tasks.add_task(_handle_telegram_update, update)

    return {"ok": "true"}


# ---------------------------------------------------------------------------
# WhatsApp (Twilio)
# ---------------------------------------------------------------------------

async def _validate_twilio_signature(
    request: Request,
    x_twilio_signature: str | None = Header(default=None),
) -> None:
    if not x_twilio_signature:
        raise HTTPException(status_code=403, detail="Missing Twilio signature")
    validator = RequestValidator(settings.twilio_api_secret)
    form = dict(await request.form())
    if not validator.validate(str(request.url), form, x_twilio_signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


async def _handle_whatsapp_update(webhook: TwilioWebhook) -> None:
    inbound = parse_whatsapp(webhook)
    await _dispatch(inbound, whatsapp_send, "whatsapp")


@router.post("/whatsapp", dependencies=[Depends(_validate_twilio_signature)])
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    form = dict(await request.form())
    webhook = TwilioWebhook.model_validate(form)
    background_tasks.add_task(_handle_whatsapp_update, webhook)
    return {"ok": "true"}
