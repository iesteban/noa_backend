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
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""  # used to validate X-Hub-Signature-256; optional but recommended
    whatsapp_business_account_id: str = ""
    redis_url: str = "redis://localhost:6379/0"


settings = Settings()  # type: ignore[call-arg]
