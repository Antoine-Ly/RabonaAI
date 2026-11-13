import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


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
