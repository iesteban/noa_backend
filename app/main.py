import logging

import sentry_sdk
from fastapi import FastAPI
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.ai import handlers as _ai_handlers  # noqa: F401 — registers all tool handlers
from app.api.calendar_auth import router as calendar_auth_router
from app.api.health import router as health_router
from app.api.webhook import router as webhook_router
from app.config import settings
from app.core.sentry import scrub_sensitive_data

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        traces_sample_rate=0,
        before_send=scrub_sensitive_data,
    )

app = FastAPI(title="Noa Backend", version="0.1.0")

app.include_router(health_router)
app.include_router(webhook_router)
app.include_router(calendar_auth_router)
