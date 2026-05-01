import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.config import settings
from app.messaging.parser import parse_update
from app.schemas.telegram import TelegramUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


def _handle_update(update: TelegramUpdate) -> None:
    inbound = parse_update(update)
    if inbound is None:
        return
    logger.info(
        "Dispatching update %d: type=%s chat_id=%d",
        inbound.update_id,
        inbound.message_type,
        inbound.chat_id,
    )
    # Routing and session handling implemented in #5 and #7


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
    background_tasks.add_task(_handle_update, update)

    return {"ok": "true"}
