from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import AppError, ErrorCode


class Payload(BaseModel):
    message: str


def _add_test_routes(app: FastAPI) -> None:
    @app.post("/_test/validate")
    def validate(payload: Payload) -> dict[str, str]:
        return {"message": payload.message}

    @app.get("/_test/app-error")
    def app_error() -> None:
        raise AppError(ErrorCode.QUOTA_USER_DAILY, "Plafond atteint.", retry_after_seconds=3600)

    @app.get("/_test/boom")
    def boom() -> None:
        raise RuntimeError("détail interne secret")


def test_unknown_route_uses_error_format(client: TestClient) -> None:
    response = client.get("/n-existe-pas")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Ressource introuvable.",
            "retry_after_seconds": None,
        }
    }


def test_validation_error_format(app: FastAPI, client: TestClient) -> None:
    _add_test_routes(app)
    response = client.post("/_test/validate", json={})
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert body["retry_after_seconds"] is None


def test_app_error_format_and_retry_header(app: FastAPI, client: TestClient) -> None:
    _add_test_routes(app)
    response = client.get("/_test/app-error")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "3600"
    assert response.json()["error"] == {
        "code": "quota_user_daily",
        "message": "Plafond atteint.",
        "retry_after_seconds": 3600,
    }


def test_unexpected_error_hides_internal_details(app: FastAPI, client: TestClient) -> None:
    _add_test_routes(app)
    response = client.get("/_test/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret" not in response.text
