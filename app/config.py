import os

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = ".env.production" if os.getenv("ENVIRONMENT") == "production" else ".env"


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


settings = Settings()  # type: ignore[call-arg]
