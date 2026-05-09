import os

from pydantic_settings import BaseSettings, SettingsConfigDict

# In production (container), settings come from real env vars — no .env file present.
# Locally, load from .env (or .env.production if ENVIRONMENT=production).
_ENV_FILE = None if os.getenv("ENVIRONMENT") == "production" else (
    ".env.production" if os.getenv("ENVIRONMENT") == "staging" else ".env"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    database_url: str
    telegram_bot_token: str
    telegram_webhook_secret: str
    anthropic_api_key: str
    openai_api_key: str
    scw_access_key: str
    scw_secret_key: str
    scw_region: str = "fr-par"
    scw_bucket: str = "noa-dev"
    environment: str = "development"
    log_level: str = "INFO"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    sentry_dsn: str = ""
    feature_hybrid_client_roster: bool = True
    twilio_account_sid: str = ""
    twilio_api_key: str = ""     # Key SID, e.g. "SKxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    twilio_client_secret: str = ""  # Client Secret shown once at API key creation
    twilio_whatsapp_from: str = ""  # E.164, e.g. "+14155238886"


settings = Settings()  # type: ignore[call-arg]
