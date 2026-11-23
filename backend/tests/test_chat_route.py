import asyncio
import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import AppError, ErrorCode
from app.db.store import HistoryMessage
from app.services.exchange import persisted_stream
from app.services.llm.base import Finished, TextDelta, ToolCall, ToolCallsRequested, Usage
from tests.fakes import OTHER, USER, FakeStore
from tests.test_chat_service import FakeLLM, ScriptedLLM


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        name, data = block.split("\n")
        events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


@pytest.fixture
def chat_client(app: FastAPI, store: FakeStore) -> TestClient:
    app.state.llm = FakeLLM(
        [TextDelta("Éric "), TextDelta("Cantona"), Finished("stop", Usage(50, 20))]
    )
    return TestClient(app, raise_server_exceptions=False)


def test_chat_streams_meta_deltas_and_done(chat_client: TestClient, store: FakeStore) -> None:
    response = chat_client.post("/chat", json={"message": "Qui est le Roi Eric ?"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["meta", "delta", "delta", "done"]
    assert events[1][1] == {"text": "Éric "}  # accents non échappés
    meta, done = events[0][1], events[3][1]
    assert done["usage"] == {"prompt_tokens": 50, "completion_tokens": 20}
    assert done["assistant_message_id"] == meta["assistant_message_id"]
    assert done["quota"] == {"messages_remaining_today": 9}
    conversation = store.conversations[next(iter(store.conversations))]
    assert conversation.title == "Qui est le Roi Eric ?"
    assert [(m.role, m.content, m.status) for m in conversation.messages] == [
        ("user", "Qui est le Roi Eric ?", "complete"),
        ("assistant", "Éric Cantona", "complete"),
    ]
    assert store.finished[0]["prompt_tokens"] == 50
    assert store.tokens == 70


def test_second_message_sends_the_history_to_the_model(
    app: FastAPI, chat_client: TestClient, store: FakeStore
) -> None:
    first = parse_sse(chat_client.post("/chat", json={"message": "Salut"}).text)[0][1]
    app.state.llm = FakeLLM([TextDelta("Oui"), Finished("stop", Usage(1, 1))])
    chat_client.post(
        "/chat", json={"message": "Et ensuite ?", "conversation_id": first["conversation_id"]}
    )
    sent = app.state.llm.calls[0][1]
    assert sent == [
        {"role": "user", "content": "Salut"},
        {"role": "assistant", "content": "Éric Cantona"},
        {"role": "user", "content": "Et ensuite ?"},
    ]


def test_history_window_is_limited(app: FastAPI, chat_client: TestClient, store: FakeStore) -> None:
    app.state.settings.history_max_messages = 2
    first = parse_sse(chat_client.post("/chat", json={"message": "un"}).text)[0][1]
    for text in ("deux", "trois"):
        app.state.llm = FakeLLM([TextDelta("ok"), Finished("stop", None)])
        chat_client.post(
            "/chat", json={"message": text, "conversation_id": first["conversation_id"]}
        )
    sent = app.state.llm.calls[0][1]
    assert [m["content"] for m in sent] == ["deux", "ok", "trois"]  # 2 messages d'historique


def test_unknown_or_foreign_conversation_is_404_and_free(
    chat_client: TestClient, store: FakeStore
) -> None:
    foreign = store.seed(OTHER)
    for conversation_id in (str(uuid4()), str(foreign)):
        response = chat_client.post(
            "/chat", json={"message": "Salut", "conversation_id": conversation_id}
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    assert store.used == {}  # aucun quota consommé


def test_user_quota_is_enforced_with_retry_after(
    app: FastAPI, chat_client: TestClient, store: FakeStore
) -> None:
    store.used[USER] = app.state.settings.user_daily_messages
    response = chat_client.post("/chat", json={"message": "Salut"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "quota_user_daily"
    assert response.json()["error"]["retry_after_seconds"] == 60
    assert response.headers["retry-after"] == "60"


def test_global_budget_is_checked_without_burning_the_user_quota(
    app: FastAPI, chat_client: TestClient, store: FakeStore
) -> None:
    store.tokens = app.state.settings.global_daily_tokens
    response = chat_client.post("/chat", json={"message": "Salut"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "quota_global_daily"
    assert store.used == {}


def test_llm_error_after_text_saves_a_partial_answer(app: FastAPI, store: FakeStore) -> None:
    app.state.llm = FakeLLM([TextDelta("Début")], error=AppError(ErrorCode.LLM_UNAVAILABLE, "KO"))
    events = parse_sse(TestClient(app).post("/chat", json={"message": "Salut"}).text)
    assert [name for name, _ in events] == ["meta", "delta", "error"]
    assert store.finished[0]["status"] == "partial"
    assert store.finished[0]["content"] == "Début"
    assert store.finished[0]["completion_tokens"] == 1  # estimation : 5 caractères // 4


def test_llm_error_without_text_keeps_only_the_user_message(app: FastAPI, store: FakeStore) -> None:
    app.state.llm = FakeLLM(error=AppError(ErrorCode.LLM_UNAVAILABLE, "KO"))
    TestClient(app).post("/chat", json={"message": "Salut"})
    assert store.finished == []
    messages = next(iter(store.conversations.values())).messages
    assert [m.role for m in messages] == ["user"]


def test_closing_the_stream_early_saves_the_partial_answer(store: FakeStore) -> None:
    llm = FakeLLM(
        [TextDelta("Un "), TextDelta("deux "), TextDelta("trois"), Finished("stop", None)]
    )

    async def scenario() -> None:
        exchange = await store.begin_exchange(
            USER, None, "Compte", daily_limit=10, global_token_limit=1000, history_max=6
        )
        stream = persisted_stream(
            store, llm, None, user_id=USER, exchange=exchange, message="Compte", model="m"
        )
        await anext(stream)  # meta
        await anext(stream)  # « Un »
        await anext(stream)  # « deux »
        await stream.aclose()  # le client a fermé la connexion (bouton Stop)

    asyncio.run(scenario())
    assert store.finished[0]["status"] == "partial"
    assert store.finished[0]["content"] == "Un deux "


def test_history_is_passed_to_stream_chat(store: FakeStore) -> None:
    llm = FakeLLM([TextDelta("ok"), Finished("stop", None)])

    async def scenario() -> None:
        exchange = await store.begin_exchange(
            USER, None, "x", daily_limit=10, global_token_limit=1000, history_max=6
        )
        exchange = type(exchange)(
            exchange.conversation_id,
            exchange.user_message_id,
            exchange.assistant_message_id,
            [HistoryMessage("user", "avant")],
            exchange.messages_remaining_today,
        )
        async for _ in persisted_stream(
            store, llm, None, user_id=USER, exchange=exchange, message="x", model="m"
        ):
            pass

    asyncio.run(scenario())
    assert llm.calls[0][1][0] == {"role": "user", "content": "avant"}


def test_tool_status_events_are_traced_in_the_saved_message(app: FastAPI, store: FakeStore) -> None:
    app.state.llm = ScriptedLLM(
        [
            ToolCallsRequested((ToolCall("c1", "get_standings", '{"competition":"ligue-1"}'),)),
            Finished("tool_calls", Usage(400, 20)),
        ],
        [TextDelta("Le PSG est premier."), Finished("stop", Usage(600, 30))],
    )
    from tests.test_football import Api, make_tools

    app.state.tools = make_tools(Api())
    events = parse_sse(TestClient(app).post("/chat", json={"message": "Classement ?"}).text)
    assert [name for name, _ in events] == ["meta", "status", "delta", "done"]
    assert events[3][1]["usage"] == {"prompt_tokens": 1000, "completion_tokens": 50}
    assert store.finished[0]["tool_calls"] == [{"tool": "get_standings"}]


@pytest.mark.parametrize("message", ["", "   \n", "x" * 2001])
def test_invalid_message_is_rejected_before_the_stream(
    chat_client: TestClient, store: FakeStore, message: str
) -> None:
    response = chat_client.post("/chat", json={"message": message})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert store.used == {}


def test_missing_message_or_bad_conversation_id_is_rejected(chat_client: TestClient) -> None:
    assert chat_client.post("/chat", json={}).status_code == 422
    bad = chat_client.post("/chat", json={"message": "a", "conversation_id": "pas-un-uuid"})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "validation_error"


def test_message_at_the_limit_is_accepted(chat_client: TestClient) -> None:
    assert chat_client.post("/chat", json={"message": "x" * 2000}).status_code == 200


def test_chat_requires_authentication(app: FastAPI) -> None:
    response = TestClient(app, raise_server_exceptions=False).post("/chat", json={"message": "a"})
    assert response.status_code == 500  # SUPABASE_URL absente : routes protégées indisponibles


def test_without_llm_or_store_chat_returns_internal_error(app: FastAPI, store: FakeStore) -> None:
    app.state.llm = None
    response = TestClient(app, raise_server_exceptions=False).post("/chat", json={"message": "a"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert store.used == {}
