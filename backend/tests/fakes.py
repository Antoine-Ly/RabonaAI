"""Faux `Store` en mémoire : mêmes règles que `PgStore` (vérifiées contre PostgreSQL dans
`test_postgres_store.py`), pour tester les routes sans base."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

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

USER = UUID("00000000-0000-0000-0000-000000000001")
OTHER = UUID("00000000-0000-0000-0000-000000000002")


class FakeStore:
    def __init__(self) -> None:
        self._tick = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
        self.conversations: dict[UUID, ConversationDetail] = {}
        self.owners: dict[UUID, UUID] = {}
        self.used: dict[UUID, int] = {}
        self.tokens = 0
        self.finished: list[dict[str, Any]] = []

    def _now(self) -> datetime:
        self._tick += timedelta(seconds=1)
        return self._tick

    def seed(self, user_id: UUID, title: str = "Titre") -> UUID:
        now = self._now()
        conversation = ConversationDetail(uuid4(), title, now, now, [])
        self.conversations[conversation.id] = conversation
        self.owners[conversation.id] = user_id
        return conversation.id

    def _replace(self, conversation_id: UUID, **changes: Any) -> None:
        old = self.conversations[conversation_id]
        self.conversations[conversation_id] = ConversationDetail(
            changes.get("id", old.id),
            changes.get("title", old.title),
            old.created_at,
            changes.get("updated_at", old.updated_at),
            changes.get("messages", old.messages),
        )

    def _add(self, conversation_id: UUID, role: str, content: str, status: str, id_=None) -> UUID:
        message = StoredMessage(id_ or uuid4(), role, content, status, self._now())  # type: ignore[arg-type]
        messages = [*self.conversations[conversation_id].messages, message]
        self._replace(conversation_id, messages=messages, updated_at=message.created_at)
        return message.id

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
        if conversation_id is not None and self.owners.get(conversation_id) != user_id:
            raise AppError(ErrorCode.NOT_FOUND, "Conversation introuvable.")
        if self.tokens >= global_token_limit:
            raise AppError(ErrorCode.QUOTA_GLOBAL_DAILY, "saturé", retry_after_seconds=60)
        if self.used.get(user_id, 0) >= daily_limit:
            raise AppError(ErrorCode.QUOTA_USER_DAILY, "limite", retry_after_seconds=60)
        self.used[user_id] = self.used.get(user_id, 0) + 1
        history: list[HistoryMessage] = []
        if conversation_id is None:
            conversation_id = self.seed(user_id, make_title(message))
        elif history_max > 0:
            kept = [m for m in self.conversations[conversation_id].messages if m.status != "error"]
            history = [HistoryMessage(m.role, m.content) for m in kept[-history_max:]]
        user_message_id = self._add(conversation_id, "user", message, "complete")
        return Exchange(
            conversation_id, user_message_id, uuid4(), history, daily_limit - self.used[user_id]
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
        self._add(
            exchange.conversation_id, "assistant", content, status, exchange.assistant_message_id
        )
        self.tokens += (prompt_tokens or 0) + (completion_tokens or 0)
        self.finished.append(
            {
                "content": content,
                "status": status,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "tool_calls": tool_calls,
            }
        )

    async def list_conversations(
        self, user_id: UUID, limit: int, cursor: Cursor | None
    ) -> list[ConversationSummary]:
        mine = [c for c in self.conversations.values() if self.owners[c.id] == user_id]
        mine.sort(key=lambda c: (c.updated_at, c.id), reverse=True)
        if cursor is not None:
            mine = [c for c in mine if (c.updated_at, c.id) < cursor]
        return [ConversationSummary(c.id, c.title, c.updated_at) for c in mine[: limit + 1]]

    async def get_conversation(
        self, user_id: UUID, conversation_id: UUID
    ) -> ConversationDetail | None:
        if self.owners.get(conversation_id) != user_id:
            return None
        return self.conversations[conversation_id]

    async def rename_conversation(
        self, user_id: UUID, conversation_id: UUID, title: str
    ) -> ConversationSummary | None:
        if self.owners.get(conversation_id) != user_id:
            return None
        self._replace(conversation_id, title=title)
        c = self.conversations[conversation_id]
        return ConversationSummary(c.id, c.title, c.updated_at)

    async def delete_conversation(self, user_id: UUID, conversation_id: UUID) -> bool:
        if self.owners.get(conversation_id) != user_id:
            return False
        del self.conversations[conversation_id], self.owners[conversation_id]
        return True

    async def get_quota(
        self, user_id: UUID, *, daily_limit: int, global_token_limit: int
    ) -> QuotaState:
        return QuotaState(self.used.get(user_id, 0), daily_limit, self.tokens < global_token_limit)
