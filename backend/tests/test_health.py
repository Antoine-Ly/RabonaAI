from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_allows_frontend_origin(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_other_origin(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_health_db_without_database_is_an_internal_error(client: TestClient) -> None:
    response = client.get("/health/db")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
