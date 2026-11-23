import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import current_user
from app.core.config import Settings
from app.main import create_app
from tests.fakes import USER, FakeStore


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Les variables d'environnement de la machine (GROQ_API_KEY, APP_ENV…) ne doivent jamais
    # influencer les tests : une clé présente ferait appeler le vrai Groq depuis `create_app`.
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture
def settings() -> Settings:
    # `_env_file=None` : les tests ne dépendent jamais d'un `.env` local.
    return Settings(_env_file=None)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    # raise_server_exceptions=False : on teste la réponse 500, pas la propagation de l'exception.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def store(app: FastAPI) -> FakeStore:
    """Faux store branché sur l'application, avec l'utilisateur `USER` déjà authentifié."""
    fake = FakeStore()
    app.state.store = fake
    app.dependency_overrides[current_user] = lambda: USER
    return fake
