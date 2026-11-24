import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_defaults_match_phase0_decisions() -> None:
    s = Settings(_env_file=None)
    assert s.app_env == "dev"
    assert s.groq_model == "openai/gpt-oss-120b"
    assert s.global_daily_tokens == 170_000
    assert s.user_daily_messages == 10
    assert s.jwt_leeway_seconds == 10


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("USER_DAILY_MESSAGES", "3")
    s = Settings(_env_file=None)
    assert s.groq_model == "openai/gpt-oss-20b"
    assert s.user_daily_messages == 3


def test_secrets_are_masked() -> None:
    s = Settings(_env_file=None, groq_api_key="gsk_secret_value")
    assert "gsk_secret_value" not in repr(s)
    assert s.groq_api_key is not None
    assert s.groq_api_key.get_secret_value() == "gsk_secret_value"


def test_prod_requires_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "GROQ_API_KEY",
        "FOOTBALL_DATA_API_KEY",
        "DATABASE_URL",
        "SUPABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValidationError, match="Variables obligatoires"):
        Settings(_env_file=None, app_env="prod", frontend_url="https://rabona.example")


def test_prod_requires_https_frontend() -> None:
    with pytest.raises(ValidationError, match="https"):
        Settings(
            _env_file=None,
            app_env="prod",
            frontend_url="http://rabona.example",
            groq_api_key="x",
            football_data_api_key="x",
            database_url="postgresql://u:p@h/db",
            supabase_url="https://x.supabase.co",
        )


def test_prod_ok_with_all_settings() -> None:
    s = Settings(
        _env_file=None,
        app_env="prod",
        frontend_url="https://rabona.example",
        groq_api_key="x",
        football_data_api_key="x",
        database_url="postgresql://u:p@h/db",
        supabase_url="https://x.supabase.co",
    )
    assert s.app_env == "prod"


@pytest.mark.parametrize("value", ["-1", "61"])
def test_leeway_bounds(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("JWT_LEEWAY_SECONDS", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_frontend_url_is_normalized_for_cors() -> None:
    settings = Settings(_env_file=None, frontend_url=" https://rabona.example/ ")
    assert settings.frontend_url == "https://rabona.example"
