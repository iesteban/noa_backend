import hashlib
import hmac
import logging

import sentry_sdk
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.claude import call_claude, get_recent_messages
from app.ai.whisper import transcribe, transcribe_from_meta
from app.config import settings
from app.database import async_session_factory
from app.messaging.options import parse_options
from app.messaging.parser import parse_update
from app.messaging.telegram_sender import ack_callback_query
from app.messaging.telegram_sender import send_message as telegram_send
from app.messaging.types import InboundMessage, MessageSender, MessageType
from app.messaging.whatsapp_parser import parse_whatsapp
from app.messaging.whatsapp_sender import send_message as whatsapp_send
from app.models.session import ConversationSession, MessageRole, UserType
from app.schemas.telegram import TelegramUpdate
from app.schemas.whatsapp import MetaWebhook
from app.services.error_report import (
    ack_message,
    ask_message,
    detect_error_intent,
    detect_language,
    save_error_report,
)
from app.services.onboarding import handle_onboarding_message
from app.services.routing import resolve_routing
from app.services.session import append_message, get_or_create_session

logger = logging.getLogger(__name__)
router = APIRouter()


async def _try_handle_error_report(
    db: AsyncSession,
    session: ConversationSession,
    text: str,
    channel: str,
    send: MessageSender,
    recipient_id: str,
) -> bool:
    """Handle error-report turns. Returns True if the message was consumed."""
    if session.user_type != UserType.contractor:
        return False

    if session.context.get("pending_error_report"):
        lang = detect_language(text)
        ctx = dict(session.context)
        ctx.pop("pending_error_report")
        session.context = ctx
        await save_error_report(db, session, text, channel)  # commits report + context together
        reply = ack_message(lang)
        await append_message(db, session.id, MessageRole.assistant, reply)
        await send(recipient_id, reply)
        return True

    is_error, description = detect_error_intent(text)
    if not is_error:
        return False

    lang = detect_language(text)
    if description is not None:
        await save_error_report(db, session, description, channel)
        reply = ack_message(lang)
    else:
        session.context = {**session.context, "pending_error_report": True}
        await db.commit()
        reply = ask_message(lang)
    await append_message(db, session.id, MessageRole.assistant, reply)
    await send(recipient_id, reply)
    return True


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

        if inbound.message_type == MessageType.unknown:
            await send(
                inbound.recipient_id,
                "No he podido entender este tipo de mensaje. "
                "Puedes enviarme texto, audio, imágenes o contactos.",
            )
            return

        text = inbound.text or ""
        media_url: str | None = None

        if inbound.message_type == MessageType.voice and inbound.file_id:
            try:
                if channel == "telegram":
                    text, media_url = await transcribe(inbound.file_id)
                else:
                    text, media_url = await transcribe_from_meta(inbound.file_id)
            except Exception as exc:
                sentry_sdk.capture_exception(exc)
                logger.exception("Whisper transcription failed for file_id %s", inbound.file_id)
                await send(
                    inbound.recipient_id,
                    "No he podido transcribir el audio. ¿Puedes escribirlo?",
                )
                return

        history = await get_recent_messages(db, session.id)

        await append_message(db, session.id, MessageRole.user, text, media_url=media_url)

        if await _try_handle_error_report(
            db, session, text, channel, send, inbound.recipient_id
        ):
            return

        raw_reply = await call_claude(db, session, text, history=history)
        clean_text, options = parse_options(raw_reply)

        await append_message(db, session.id, MessageRole.assistant, clean_text)
        await send(inbound.recipient_id, clean_text, options)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

async def _handle_telegram_update(update: TelegramUpdate) -> None:
    if update.callback_query is not None:
        await ack_callback_query(update.callback_query.id)
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
# WhatsApp (Meta Graph API)
# ---------------------------------------------------------------------------

async def _validate_meta_signature(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
) -> None:
    if not settings.whatsapp_app_secret:
        return
    if not x_hub_signature_256:
        raise HTTPException(status_code=403, detail="Missing signature")
    body = await request.body()
    computed = "sha256=" + hmac.new(
        settings.whatsapp_app_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(x_hub_signature_256, computed):
        raise HTTPException(status_code=403, detail="Invalid signature")


async def _handle_whatsapp_update(webhook: MetaWebhook) -> None:
    inbound = parse_whatsapp(webhook)
    if inbound is None:
        return
    await _dispatch(inbound, whatsapp_send, "whatsapp")


@router.get("/whatsapp")
async def whatsapp_verify(
    hub_mode_dot: str | None = Query(default=None, alias="hub.mode"),
    hub_mode_us: str | None = Query(default=None, alias="hub_mode"),
    hub_verify_token_dot: str | None = Query(default=None, alias="hub.verify_token"),
    hub_verify_token_us: str | None = Query(default=None, alias="hub_verify_token"),
    hub_challenge_dot: str | None = Query(default=None, alias="hub.challenge"),
    hub_challenge_us: str | None = Query(default=None, alias="hub_challenge"),
) -> PlainTextResponse:
    # Some proxies convert dots to underscores in query param names; accept both forms.
    hub_mode = hub_mode_dot or hub_mode_us
    hub_verify_token = hub_verify_token_dot or hub_verify_token_us
    hub_challenge = hub_challenge_dot or hub_challenge_us
    if hub_mode != "subscribe" or hub_verify_token != settings.whatsapp_verify_token:
        raise HTTPException(status_code=403, detail="Verification failed")
    return PlainTextResponse(hub_challenge or "")


@router.post("/whatsapp", dependencies=[Depends(_validate_meta_signature)])
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    body = await request.json()
    webhook = MetaWebhook.model_validate(body)
    background_tasks.add_task(_handle_whatsapp_update, webhook)
    return {"ok": "true"}
