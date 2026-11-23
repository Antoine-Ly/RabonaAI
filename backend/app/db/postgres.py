"""Implémentation PostgreSQL (Supabase) de `Store` : SQL direct, transactions courtes (§6).

Aucune connexion n'est gardée ouverte pendant le streaming de la réponse : un tour de dialogue
utilise une transaction avant (`begin_exchange`) et une après (`finish_exchange`).
"""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.clock import seconds_until_utc_midnight
from app.core.errors import AppError, ErrorCode
from app.db.store import (
    ConversationDetail,
    ConversationSummary,
    Cursor,
    Exchange,
    HistoryMessage,
    MessageStatus,
    QuotaState,
    StoredMessage,
    make_title,
)

_TODAY = "(now() at time zone 'utc')::date"


def build_engine(database_url: str) -> AsyncEngine:
    # Le préfixe choisit le pilote psycopg 3 ; `prepare_threshold=None` désactive les requêtes
    # préparées, ce qui convient aux deux modes de pooler Supabase (session et transaction).
    url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_async_engine(
        url,
        pool_size=3,
        max_overflow=2,
        pool_pre_ping=True,  # Supabase ferme les connexions inactives
        connect_args={"prepare_threshold": None},
    )


class PgStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def begin_exchange(
        self,
        user_id: UUID,
        conversation_id: UUID | None,
        message: str,
        *,
        daily_limit: int,
        global_token_limit: int,
        history_max: int,
    ) -> Exchange:
        async with self._engine.begin() as conn:
            # 1. Conversation inexistante ou d'un autre utilisateur : 404 sans consommer de quota.
            if conversation_id is not None:
                owned = await conn.scalar(
                    text("select 1 from conversations where id = :c and user_id = :u"),
                    {"c": conversation_id, "u": user_id},
                )
                if owned is None:
                    raise AppError(ErrorCode.NOT_FOUND, "Conversation introuvable.")

            # 2. Budget global : refusé avant de réserver, pour ne pas brûler un message.
            tokens = await conn.scalar(
                text(f"select coalesce(sum(tokens), 0) from usage_daily where day = {_TODAY}")
            )
            if int(tokens or 0) >= global_token_limit:
                raise AppError(
                    ErrorCode.QUOTA_GLOBAL_DAILY,
                    "Le service est saturé pour aujourd'hui. Réessaie demain.",
                    retry_after_seconds=seconds_until_utc_midnight(),
                )

            # 3. Réservation atomique d'un message (§6.2) : aucune ligne = plafond atteint.
            used = await conn.scalar(
                text(
                    f"""
                    insert into usage_daily (day, user_id, messages)
                    values ({_TODAY}, :u, 1)
                    on conflict (day, user_id) do update
                      set messages = usage_daily.messages + 1
                      where usage_daily.messages < :limit
                    returning messages
                    """
                ),
                {"u": user_id, "limit": daily_limit},
            )
            if used is None:
                raise AppError(
                    ErrorCode.QUOTA_USER_DAILY,
                    "Tu as atteint ta limite de messages pour aujourd'hui.",
                    retry_after_seconds=seconds_until_utc_midnight(),
                )

            # 4. Historique envoyé au modèle : les derniers messages, sans les réponses en erreur.
            history: list[HistoryMessage] = []
            if conversation_id is not None and history_max > 0:
                rows = await conn.execute(
                    text(
                        """
                        select role, content from messages
                        where conversation_id = :c and status <> 'error'
                        order by created_at desc, id desc limit :n
                        """
                    ),
                    {"c": conversation_id, "n": history_max},
                )
                history = [HistoryMessage(r.role, r.content) for r in reversed(rows.all())]

            # 5. Conversation (créée ou touchée) et message de l'utilisateur.
            if conversation_id is None:
                conversation_id = await conn.scalar(
                    text("insert into conversations (user_id, title) values (:u, :t) returning id"),
                    {"u": user_id, "t": make_title(message)},
                )
            else:
                await conn.execute(
                    text("update conversations set updated_at = now() where id = :c"),
                    {"c": conversation_id},
                )
            user_message_id = await conn.scalar(
                text(
                    "insert into messages (conversation_id, role, content) "
                    "values (:c, 'user', :m) returning id"
                ),
                {"c": conversation_id, "m": message},
            )
            assistant_message_id = await conn.scalar(text("select gen_random_uuid()"))
        assert conversation_id is not None and user_message_id is not None
        assert assistant_message_id is not None and used is not None
        return Exchange(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            history=history,
            messages_remaining_today=daily_limit - int(used),
        )

    async def finish_exchange(
        self,
        user_id: UUID,
        exchange: Exchange,
        *,
        content: str,
        status: MessageStatus,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        tool_calls: list[dict[str, Any]] | None,
    ) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    insert into messages
                      (id, conversation_id, role, content, status, model,
                       prompt_tokens, completion_tokens, tool_calls)
                    values
                      (:id, :c, 'assistant', :content, :status, :model,
                       :pt, :ct, cast(:tools as jsonb))
                    """
                ),
                {
                    "id": exchange.assistant_message_id,
                    "c": exchange.conversation_id,
                    "content": content,
                    "status": status,
                    "model": model,
                    "pt": prompt_tokens,
                    "ct": completion_tokens,
                    "tools": json.dumps(tool_calls) if tool_calls else None,
                },
            )
            await conn.execute(
                text("update conversations set updated_at = now() where id = :c"),
                {"c": exchange.conversation_id},
            )
            consumed = (prompt_tokens or 0) + (completion_tokens or 0)
            if consumed:
                await conn.execute(
                    text(
                        f"update usage_daily set tokens = tokens + :n "
                        f"where day = {_TODAY} and user_id = :u"
                    ),
                    {"n": consumed, "u": user_id},
                )

    async def list_conversations(
        self, user_id: UUID, limit: int, cursor: Cursor | None
    ) -> list[ConversationSummary]:
        params: dict[str, Any] = {"u": user_id, "n": limit + 1}
        after = ""
        if cursor is not None:
            after = "and (updated_at, id) < (:ts, :cid)"
            params |= {"ts": cursor[0], "cid": cursor[1]}
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(
                    f"""
                    select id, title, updated_at from conversations
                    where user_id = :u {after}
                    order by updated_at desc, id desc limit :n
                    """
                ),
                params,
            )
            return [ConversationSummary(r.id, r.title, r.updated_at) for r in rows.all()]

    async def get_conversation(
        self, user_id: UUID, conversation_id: UUID
    ) -> ConversationDetail | None:
        async with self._engine.connect() as conn:
            head = (
                await conn.execute(
                    text(
                        "select id, title, created_at, updated_at from conversations "
                        "where id = :c and user_id = :u"
                    ),
                    {"c": conversation_id, "u": user_id},
                )
            ).first()
            if head is None:
                return None
            rows = await conn.execute(
                text(
                    """
                    select id, role, content, status, created_at from messages
                    where conversation_id = :c order by created_at, id
                    """
                ),
                {"c": conversation_id},
            )
            messages = [
                StoredMessage(r.id, r.role, r.content, r.status, r.created_at) for r in rows.all()
            ]
        return ConversationDetail(head.id, head.title, head.created_at, head.updated_at, messages)

    async def rename_conversation(
        self, user_id: UUID, conversation_id: UUID, title: str
    ) -> ConversationSummary | None:
        # `updated_at` inchangé : renommer ne réordonne pas la liste.
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "update conversations set title = :t where id = :c and user_id = :u "
                        "returning id, title, updated_at"
                    ),
                    {"t": title, "c": conversation_id, "u": user_id},
                )
            ).first()
        return ConversationSummary(row.id, row.title, row.updated_at) if row else None

    async def delete_conversation(self, user_id: UUID, conversation_id: UUID) -> bool:
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("delete from conversations where id = :c and user_id = :u"),
                {"c": conversation_id, "u": user_id},
            )
        return result.rowcount > 0

    async def get_quota(
        self, user_id: UUID, *, daily_limit: int, global_token_limit: int
    ) -> QuotaState:
        async with self._engine.connect() as conn:
            used = await conn.scalar(
                text(f"select messages from usage_daily where day = {_TODAY} and user_id = :u"),
                {"u": user_id},
            )
            tokens = await conn.scalar(
                text(f"select coalesce(sum(tokens), 0) from usage_daily where day = {_TODAY}")
            )
        return QuotaState(
            messages_used_today=int(used or 0),
            messages_limit=daily_limit,
            service_available=int(tokens or 0) < global_token_limit,
        )
