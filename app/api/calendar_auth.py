from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.messaging.telegram_sender import send_message
from app.models.appointment import CalendarToken
from app.models.contractor import Contractor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/google", tags=["calendar-auth"])

_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _make_flow() -> Any:
    from google_auth_oauthlib.flow import Flow

    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.google_redirect_uri],
            }
        },
        scopes=_SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )


@router.get("/connect")
async def google_connect(state: str, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    """Redirect contractor to Google OAuth consent screen."""
    result = await db.execute(
        select(CalendarToken).where(
            CalendarToken.state == state,
            CalendarToken.access_token.is_(None),
        )
    )
    token = result.scalar_one_or_none()
    if token is None:
        raise HTTPException(status_code=400, detail="Invalid or expired state.")

    flow = _make_flow()
    auth_url, _ = flow.authorization_url(
        state=state,
        access_type="offline",
        prompt="consent",
    )
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def google_callback(
    code: str, state: str, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    """Handle Google OAuth callback, store tokens, notify contractor."""
    result = await db.execute(
        select(CalendarToken).where(
            CalendarToken.state == state,
            CalendarToken.access_token.is_(None),
        )
    )
    token = result.scalar_one_or_none()
    if token is None:
        raise HTTPException(status_code=400, detail="Invalid or expired state.")

    flow = _make_flow()
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        logger.error("Google token exchange failed: %s", exc)
        raise HTTPException(status_code=400, detail="Token exchange failed.") from exc

    creds = flow.credentials
    token.access_token = creds.token
    token.refresh_token = creds.refresh_token
    token.expires_at = creds.expiry
    await db.flush()
    await db.commit()

    contractor = await db.get(Contractor, token.contractor_id)
    if contractor and contractor.telegram_chat_id:
        try:
            await send_message(
                int(contractor.telegram_chat_id),
                "✅ Google Calendar conectado. Ya puedo gestionar tu agenda.",
            )
        except Exception:
            logger.warning("Could not notify contractor %s after calendar connect", contractor.id)

    return {"status": "ok", "message": "Google Calendar conectado correctamente."}
