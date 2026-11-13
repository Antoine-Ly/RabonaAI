"""Configuration de l'application, lue depuis l'environnement (et `.env` en local).

Les secrets sont optionnels en développement afin que `/health` et les tests fonctionnent
sans clé. En production (`APP_ENV=prod`), les variables indispensables sont exigées au démarrage.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_env: Literal["dev", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    frontend_url: str = "http://localhost:5173"

    # LLM (Groq) : un modèle fixe pour tout le projet (ADR 0001)
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-120b"

    # Données football
    football_data_api_key: SecretStr | None = None

    # Base de données et authentification (Supabase)
    database_url: SecretStr | None = None
    supabase_url: str | None = None
    supabase_jwt_audience: str = "authenticated"
    jwt_leeway_seconds: int = Field(default=10, ge=0, le=60)

    # Quotas et limites (conception §5.3)
    user_daily_messages: int = Field(default=10, ge=1)
    global_daily_tokens: int = Field(default=170_000, ge=1_000)
    max_message_chars: int = Field(default=2_000, ge=1)
    history_max_messages: int = Field(default=4, ge=0)
    max_completion_tokens: int = Field(default=1_500, ge=100)

    @model_validator(mode="after")
    def _require_secrets_in_prod(self) -> Self:
        if self.app_env == "prod":
            missing = [
                name
                for name in (
                    "groq_api_key",
                    "football_data_api_key",
                    "database_url",
                    "supabase_url",
                )
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"Variables obligatoires en production : {', '.join(missing)}")
            if not self.frontend_url.startswith("https://"):
                raise ValueError("FRONTEND_URL doit être en https:// en production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
