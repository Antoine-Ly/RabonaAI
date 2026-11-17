import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import AppError, ErrorCode
from app.services.llm.base import Finished, TextDelta, Usage
from tests.test_chat_service import FakeLLM


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        name, data = block.split("\n")
        events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


@pytest.fixture
def chat_client(app: FastAPI) -> TestClient:
    app.state.llm = FakeLLM(
        [TextDelta("Éric "), TextDelta("Cantona"), Finished("stop", Usage(50, 20))]
    )
    return TestClient(app, raise_server_exceptions=False)


def test_chat_streams_sse(chat_client: TestClient) -> None:
    response = chat_client.post("/chat", json={"message": "Qui est le Roi Eric ?"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["delta", "delta", "done"]
    assert events[0][1] == {"text": "Éric "}  # accents non échappés
    assert events[2][1]["usage"] == {"prompt_tokens": 50, "completion_tokens": 20}


def test_chat_ignores_future_contract_fields(chat_client: TestClient) -> None:
    response = chat_client.post("/chat", json={"message": "Salut", "conversation_id": None})
    assert response.status_code == 200


def test_llm_failure_is_an_error_event_not_an_http_error(app: FastAPI) -> None:
    app.state.llm = FakeLLM(error=AppError(ErrorCode.QUOTA_GLOBAL_DAILY, "limite atteinte"))
    response = TestClient(app).post("/chat", json={"message": "Salut"})
    assert response.status_code == 200
    assert parse_sse(response.text) == [
        (
            "error",
            {
                "code": "quota_global_daily",
                "message": "limite atteinte",
                "retry_after_seconds": None,
            },
        )
    ]


@pytest.mark.parametrize("message", ["", "   \n", "x" * 2001])
def test_invalid_message_is_rejected_before_the_stream(
    chat_client: TestClient, message: str
) -> None:
    response = chat_client.post("/chat", json={"message": message})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_missing_message_is_rejected(chat_client: TestClient) -> None:
    response = chat_client.post("/chat", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_message_at_the_limit_is_accepted(chat_client: TestClient) -> None:
    assert chat_client.post("/chat", json={"message": "x" * 2000}).status_code == 200


def test_without_api_key_chat_returns_internal_error(client: TestClient) -> None:
    response = client.post("/chat", json={"message": "Salut"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
