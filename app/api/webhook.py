import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.config import settings
from app.database import async_session_factory
from app.messaging.parser import parse_update
from app.messaging.telegram_sender import send_message
from app.messaging.types import InboundMessage, MessageSender
from app.models.session import MessageRole
from app.schemas.telegram import TelegramUpdate
from app.services.routing import resolve_routing
from app.services.session import append_message, get_or_create_session

logger = logging.getLogger(__name__)
router = APIRouter()

_ONBOARDING_MESSAGE = (
    "Hola, soy Noa. ¿Eres profesional autónomo o quieres contactar con algún profesional?"
)


async def _dispatch(inbound: InboundMessage, send: MessageSender, channel: str) -> None:
    logger.info(
        "Dispatching update %d: type=%s chat_id=%d",
        inbound.update_id,
        inbound.message_type,
        inbound.chat_id,
    )

    async with async_session_factory() as db:
        routing = await resolve_routing(db, inbound.chat_id, inbound.phone_number)

        if routing.user_type is None:
            if routing.candidates:
                lines = "\n".join(
                    f"{i + 1}. {name}" for i, (_, name) in enumerate(routing.candidates)
                )
                await send(inbound.chat_id, f"¿Con quién quieres contactar?\n{lines}")
            else:
                await send(inbound.chat_id, _ONBOARDING_MESSAGE)
            return

        session = await get_or_create_session(
            db,
            session_key=str(inbound.chat_id),
            channel=channel,
            routing=routing,
        )
        await append_message(
            db,
            session.id,
            MessageRole.user,
            inbound.text or "",
        )
        # AI response assembled in #10


async def _handle_telegram_update(update: TelegramUpdate) -> None:
    inbound = parse_update(update)
    if inbound is None:
        return
    await _dispatch(inbound, send_message, "telegram")


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
