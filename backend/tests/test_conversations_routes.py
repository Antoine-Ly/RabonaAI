from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.routes.conversations import decode_cursor
from tests.fakes import OTHER, USER, FakeStore


@pytest.fixture
def api(client: TestClient, store: FakeStore) -> TestClient:
    return client


def test_list_is_sorted_and_paginated_with_an_opaque_cursor(
    api: TestClient, store: FakeStore
) -> None:
    ids = [store.seed(USER, f"Conversation {n}") for n in range(5)]
    store.seed(OTHER, "Autre")
    first = api.get("/conversations", params={"limit": 2}).json()
    assert [i["title"] for i in first["items"]] == ["Conversation 4", "Conversation 3"]
    assert first["next_cursor"]
    second = api.get("/conversations", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert [i["id"] for i in second["items"]] == [str(ids[2]), str(ids[1])]
    last = api.get("/conversations", params={"limit": 2, "cursor": second["next_cursor"]}).json()
    assert [i["id"] for i in last["items"]] == [str(ids[0])]
    assert last["next_cursor"] is None


def test_list_is_empty_for_a_new_user(api: TestClient) -> None:
    assert api.get("/conversations").json() == {"items": [], "next_cursor": None}


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 51}, {"cursor": "n'importe quoi"}])
def test_list_rejects_bad_parameters(api: TestClient, params: dict) -> None:
    response = api.get("/conversations", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_cursor_roundtrip_rejects_garbage() -> None:
    with pytest.raises(Exception, match="Curseur invalide"):
        decode_cursor("AAAA")


def test_get_conversation_with_messages(api: TestClient, store: FakeStore) -> None:
    conversation_id = store.seed(USER, "Hors-jeu")
    store._add(conversation_id, "user", "Explique", "complete")
    store._add(conversation_id, "assistant", "Voici", "partial")
    body = api.get(f"/conversations/{conversation_id}").json()
    assert body["title"] == "Hors-jeu"
    assert [(m["role"], m["status"]) for m in body["messages"]] == [
        ("user", "complete"),
        ("assistant", "partial"),
    ]


def test_foreign_unknown_and_malformed_ids(api: TestClient, store: FakeStore) -> None:
    foreign = store.seed(OTHER)
    for method in ("get", "delete"):
        for conversation_id in (foreign, uuid4()):
            response = getattr(api, method)(f"/conversations/{conversation_id}")
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "not_found"
    assert api.patch(f"/conversations/{foreign}", json={"title": "x"}).status_code == 404
    assert api.get("/conversations/pas-un-uuid").status_code == 422
    assert foreign in store.conversations  # la suppression d'un autre utilisateur n'a rien fait


def test_rename(api: TestClient, store: FakeStore) -> None:
    conversation_id = store.seed(USER, "Ancien")
    before = store.conversations[conversation_id].updated_at
    response = api.patch(f"/conversations/{conversation_id}", json={"title": "  Nouveau  titre "})
    assert response.status_code == 200
    assert response.json()["title"] == "Nouveau  titre"  # espaces de bord retirés
    assert store.conversations[conversation_id].updated_at == before


@pytest.mark.parametrize("title", ["", "   ", "x" * 121])
def test_rename_validation(api: TestClient, store: FakeStore, title: str) -> None:
    conversation_id = store.seed(USER)
    response = api.patch(f"/conversations/{conversation_id}", json={"title": title})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_delete(api: TestClient, store: FakeStore) -> None:
    conversation_id = store.seed(USER)
    response = api.delete(f"/conversations/{conversation_id}")
    assert response.status_code == 204
    assert response.content == b""
    assert api.get(f"/conversations/{conversation_id}").status_code == 404


def test_quota(api: TestClient, store: FakeStore) -> None:
    store.used[USER] = 3
    body = api.get("/me/quota").json()
    assert body["messages_used_today"] == 3
    assert body["messages_limit"] == 10
    assert body["service_available"] is True
    assert body["resets_at"].endswith("T00:00:00Z")
    store.tokens = 170_000
    assert api.get("/me/quota").json()["service_available"] is False


def test_cors_allows_patch(api: TestClient) -> None:
    response = api.options(
        "/conversations/abc",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]
