from fastapi import FastAPI

from app.ai import handlers as _ai_handlers  # noqa: F401 — registers all tool handlers
from app.api.calendar_auth import router as calendar_auth_router
from app.api.health import router as health_router
from app.api.webhook import router as webhook_router

app = FastAPI(title="Noa Backend", version="0.1.0")

app.include_router(health_router)
app.include_router(webhook_router)
app.include_router(calendar_auth_router)
