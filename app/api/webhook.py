import logging

from fastapi import APIRouter, Header, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    from app.config import settings

    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    update = await request.json()
    logger.info("Received Telegram update: %s", update.get("update_id"))

    # Dispatch to message handler (to be implemented in #6)
    return {"ok": "true"}
