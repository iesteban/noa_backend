from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.messaging.telegram_sender import send_message
from app.models.appointment import CalendarToken
from app.models.contractor import Contractor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/google", tags=["calendar-auth"])

_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


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


def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256."""
    verifier = secrets.token_urlsafe(32)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return verifier, challenge


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

    code_verifier, code_challenge = _pkce_pair()
    token.code_verifier = code_verifier
    await db.commit()

    flow = _make_flow()
    auth_url, _ = flow.authorization_url(
        state=state,
        access_type="offline",
        prompt="consent",
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    return RedirectResponse(url=auth_url)


_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Google Calendar conectado · Noa</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@1,300&display=swap"
        rel="stylesheet" />
  <style>
    :root {
      --brand: #2563eb;
      --text:  #111827;
      --muted: #6b7280;
      --bg:    #f9fafb;
      --white: #ffffff;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100dvh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .card {
      background: var(--white);
      border-radius: 16px;
      padding: 48px 40px;
      max-width: 400px;
      width: 100%;
      text-align: center;
      box-shadow: 0 1px 4px rgba(0,0,0,.08);
    }
    .check {
      width: 64px;
      height: 64px;
      background: #dcfce7;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 24px;
      font-size: 32px;
    }
    h1 {
      font-family: 'Fraunces', serif;
      font-weight: 300;
      font-style: italic;
      font-size: 26px;
      color: var(--text);
      margin-bottom: 12px;
    }
    p {
      font-size: 15px;
      color: var(--muted);
      line-height: 1.6;
      margin-bottom: 32px;
    }
</style>
</head>
<body>
  <div class="card">
    <div class="check">✓</div>
    <h1>¡Calendario conectado!</h1>
    <p>Google Calendar está vinculado a tu cuenta de Noa.<br>Ya puedo ver y gestionar tu agenda.</p>
    <p style="color:var(--muted);font-size:13px">Puedes cerrar esta pestaña y volver a Telegram.</p>
  </div>
</body>
</html>"""


@router.get("/callback")
async def google_callback(
    code: str, state: str, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
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
        flow.fetch_token(code=code, code_verifier=token.code_verifier)
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
                contractor.telegram_chat_id,
                "✅ Google Calendar conectado. Ya puedo gestionar tu agenda.",
            )
        except Exception:
            logger.warning("Could not notify contractor %s after calendar connect", contractor.id)

    return HTMLResponse(_SUCCESS_HTML)
