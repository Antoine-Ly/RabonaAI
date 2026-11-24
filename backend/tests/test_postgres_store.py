"""Tests d'intégration de `PgStore` et de la migration contre un vrai PostgreSQL.

Ignorés sans `TEST_DATABASE_URL` (ex. `postgresql://postgres@localhost:5432/rabona_test`). La base
est entièrement recréée : ne jamais pointer vers le projet Supabase. En CI, un service PostgreSQL
fournit cette variable.
"""

import asyncio
import os
from collections.abc import Callable, Coroutine, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.db.postgres import PgStore, build_engine
from tests.fakes import OTHER, USER

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL non définie")

BACKEND = Path(__file__).resolve().parent.parent
LIMITS: dict[str, Any] = {"daily_limit": 3, "global_token_limit": 1000, "history_max": 4}


def sync_url() -> str:
    assert URL is not None
    return URL.replace("postgresql://", "postgresql+psycopg://", 1)


def alembic_config() -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    return config


@pytest.fixture(scope="module", autouse=True)
def migrated() -> Iterator[None]:
    """Recrée une base vide avec un `auth.users` minimal (Supabase le fournit), puis migre."""
    engine = create_engine(sync_url())
    # Garde-fou : ces tests suppriment le schéma `auth` et les tables de l'application.
    if not (engine.url.database or "").endswith("_test"):
        pytest.exit("TEST_DATABASE_URL doit désigner une base dont le nom finit par _test.")
    with engine.begin() as conn:
        conn.execute(text("drop schema if exists auth cascade"))
        for table in ("messages", "conversations", "usage_daily", "alembic_version"):
            conn.execute(text(f"drop table if exists public.{table} cascade"))
        conn.execute(text("create schema auth"))
        conn.execute(text("create table auth.users (id uuid primary key)"))
    patch = pytest.MonkeyPatch()
    patch.setenv("DATABASE_URL", URL or "")
    get_settings.cache_clear()
    command.upgrade(alembic_config(), "head")
    # Le schéma de la phase 0 existe déjà sur Supabase : la migration doit l'adopter sans erreur.
    command.stamp(alembic_config(), "base", purge=True)
    command.upgrade(alembic_config(), "head")
    yield
    patch.undo()
    get_settings.cache_clear()
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables() -> None:
    engine = create_engine(sync_url())
    with engine.begin() as conn:
        conn.execute(text("truncate public.usage_daily, public.conversations cascade"))
        for user in (USER, OTHER):
            conn.execute(
                text("insert into auth.users (id) values (:u) on conflict do nothing"), {"u": user}
            )
    engine.dispose()


def run[T](scenario: Callable[[PgStore], Coroutine[Any, Any, T]]) -> T:
    async def go() -> T:
        assert URL is not None
        engine = build_engine(URL)
        try:
            return await scenario(PgStore(engine))
        finally:
            await engine.dispose()

    return asyncio.run(go())


async def say(store: PgStore, user: Any, text_: str, conversation_id: Any = None, **kw: Any) -> Any:
    """Un tour complet : question puis réponse enregistrée."""
    exchange = await store.begin_exchange(user, conversation_id, text_, **(LIMITS | kw))
    await store.finish_exchange(
        user,
        exchange,
        content=f"réponse à {text_}",
        status="complete",
        model="m",
        prompt_tokens=100,
        completion_tokens=50,
        tool_calls=[{"tool": "get_standings"}],
    )
    return exchange


def test_exchange_roundtrip_persists_messages_tokens_and_quota() -> None:
    async def scenario(store: PgStore) -> None:
        exchange = await say(store, USER, "Où en est la Ligue 1 au classement ?")
        assert exchange.messages_remaining_today == 2
        detail = await store.get_conversation(USER, exchange.conversation_id)
        assert detail is not None
        assert detail.title == "Où en est la Ligue 1 au classement ?"
        assert [(m.role, m.status) for m in detail.messages] == [
            ("user", "complete"),
            ("assistant", "complete"),
        ]
        assert detail.messages[1].id == exchange.assistant_message_id
        quota = await store.get_quota(USER, daily_limit=3, global_token_limit=1000)
        assert (quota.messages_used_today, quota.service_available) == (1, True)

    run(scenario)


def test_tool_calls_are_stored_as_jsonb() -> None:
    async def scenario(store: PgStore) -> None:
        await say(store, USER, "a")

    run(scenario)
    engine = create_engine(sync_url())
    with engine.connect() as conn:
        stored = conn.scalar(text("select tool_calls from messages where role = 'assistant'"))
        tokens = conn.scalar(text("select tokens from usage_daily"))
    engine.dispose()
    assert stored == [{"tool": "get_standings"}]
    assert tokens == 150


def test_history_is_a_window_without_failed_answers() -> None:
    async def scenario(store: PgStore) -> None:
        first = await say(store, USER, "un", daily_limit=9)
        await say(store, USER, "deux", first.conversation_id, daily_limit=9)
        failed = await store.begin_exchange(
            USER, first.conversation_id, "trois", **(LIMITS | {"daily_limit": 9})
        )
        await store.finish_exchange(
            USER,
            failed,
            content="boum",
            status="error",
            model="m",
            prompt_tokens=None,
            completion_tokens=None,
            tool_calls=None,
        )
        last = await store.begin_exchange(
            USER, first.conversation_id, "quatre", **(LIMITS | {"daily_limit": 9})
        )
        assert [m.content for m in last.history] == [
            "réponse à un",
            "deux",
            "réponse à deux",
            "trois",
        ]  # 4 derniers messages, la réponse en erreur est exclue, l'ordre est chronologique

    run(scenario)


def test_reservation_is_atomic_under_concurrency() -> None:
    async def scenario(store: PgStore) -> None:
        results = await asyncio.gather(
            *(store.begin_exchange(USER, None, f"m{n}", **LIMITS) for n in range(6)),
            return_exceptions=True,
        )
        refused = [r for r in results if isinstance(r, AppError)]
        assert len(refused) == 3
        assert all(r.code is ErrorCode.QUOTA_USER_DAILY and r.retry_after_seconds for r in refused)
        quota = await store.get_quota(USER, daily_limit=3, global_token_limit=1000)
        assert quota.messages_used_today == 3
        assert len(await store.list_conversations(USER, 20, None)) == 3  # rien de créé en trop

    run(scenario)


def test_global_budget_refuses_without_burning_the_user_quota() -> None:
    async def scenario(store: PgStore) -> None:
        await say(store, OTHER, "gros consommateur", global_token_limit=100)
        with pytest.raises(AppError) as error:
            await store.begin_exchange(
                USER, None, "salut", **(LIMITS | {"global_token_limit": 100})
            )
        assert error.value.code is ErrorCode.QUOTA_GLOBAL_DAILY
        quota = await store.get_quota(USER, daily_limit=3, global_token_limit=100)
        assert (quota.messages_used_today, quota.service_available) == (0, False)

    run(scenario)


def test_conversations_are_isolated_between_users() -> None:
    async def scenario(store: PgStore) -> None:
        mine = await say(store, USER, "privé")
        assert await store.get_conversation(OTHER, mine.conversation_id) is None
        assert await store.rename_conversation(OTHER, mine.conversation_id, "piraté") is None
        assert await store.delete_conversation(OTHER, mine.conversation_id) is False
        assert await store.list_conversations(OTHER, 20, None) == []
        with pytest.raises(AppError) as error:
            await store.begin_exchange(OTHER, mine.conversation_id, "intrus", **LIMITS)
        assert error.value.code is ErrorCode.NOT_FOUND
        quota = await store.get_quota(OTHER, daily_limit=3, global_token_limit=1000)
        assert quota.messages_used_today == 0  # la tentative n'a rien consommé
        detail = await store.get_conversation(USER, mine.conversation_id)
        assert detail is not None
        assert detail.title == "privé"
        assert len(detail.messages) == 2

    run(scenario)


def test_pagination_is_stable_and_ordered_by_recent_activity() -> None:
    async def scenario(store: PgStore) -> None:
        ids = [
            (await store.begin_exchange(USER, None, f"c{n}", **(LIMITS | {"daily_limit": 9})))
            for n in range(5)
        ]
        # Une nouvelle activité sur la plus ancienne la remonte en tête.
        await store.begin_exchange(
            USER, ids[0].conversation_id, "retour", **(LIMITS | {"daily_limit": 9})
        )
        seen: list[Any] = []
        cursor = None
        while True:
            rows = await store.list_conversations(USER, 2, cursor)
            page = rows[:2]
            seen += [c.id for c in page]
            if len(rows) <= 2:
                break
            cursor = (page[-1].updated_at, page[-1].id)
        expected = [ids[0], ids[4], ids[3], ids[2], ids[1]]
        assert seen == [e.conversation_id for e in expected]

    run(scenario)


def test_rename_keeps_order_and_delete_cascades() -> None:
    async def scenario(store: PgStore) -> None:
        exchange = await say(store, USER, "a")
        before = (await store.list_conversations(USER, 20, None))[0].updated_at
        renamed = await store.rename_conversation(USER, exchange.conversation_id, "Nouveau titre")
        assert renamed is not None
        assert (renamed.title, renamed.updated_at) == ("Nouveau titre", before)
        assert await store.delete_conversation(USER, exchange.conversation_id) is True
        assert await store.delete_conversation(USER, exchange.conversation_id) is False

    run(scenario)
    engine = create_engine(sync_url())
    with engine.connect() as conn:
        assert conn.scalar(text("select count(*) from messages")) == 0
    engine.dispose()


def test_long_title_is_rejected_by_the_database_constraint() -> None:
    async def scenario(store: PgStore) -> None:
        exchange = await say(store, USER, "a")
        with pytest.raises(Exception, match="title"):
            await store.rename_conversation(USER, exchange.conversation_id, "x" * 121)

    run(scenario)


def test_health_db_reaches_the_database() -> None:
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app

    with TestClient(create_app(Settings(_env_file=None, database_url=URL))) as client:
        assert client.get("/health/db").json() == {"status": "ok"}


def test_every_public_table_has_row_level_security() -> None:
    """Garde-fou : une table de `public` sans RLS serait lisible avec la clé publique Supabase."""
    engine = create_engine(sync_url())
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                select c.relname, c.relrowsecurity from pg_class c
                join pg_namespace n on n.oid = c.relnamespace
                where n.nspname = 'public' and c.relkind in ('r', 'p')
                """
            )
        ).all()
    engine.dispose()
    assert {r.relname for r in rows} >= {
        "alembic_version",
        "conversations",
        "messages",
        "usage_daily",
    }
    assert [r.relname for r in rows if not r.relrowsecurity] == []
