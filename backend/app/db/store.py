"""Interface d'accès aux données (conception §6) et objets échangés avec les routes.

`PgStore` (postgres.py) est la seule implémentation de production ; les tests des routes utilisent
un faux en mémoire, comme pour `LLMClient`.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

Role = Literal["user", "assistant"]
MessageStatus = Literal["complete", "partial", "error"]

TITLE_MAX = 40  # titre dérivé des premiers caractères du premier message (conception §3.1)


def make_title(text: str) -> str:
    """Même règle que `makeTitle` côté frontend : espaces normalisés, 40 caractères au plus."""
    flat = " ".join(text.split())
    return f"{flat[: TITLE_MAX - 1].rstrip()}…" if len(flat) > TITLE_MAX else flat


@dataclass(frozen=True)
class HistoryMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class Exchange:
    """Un tour de dialogue ouvert : quota réservé, message de l'utilisateur enregistré."""

    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    history: list[HistoryMessage]
    messages_remaining_today: int


@dataclass(frozen=True)
class ConversationSummary:
    id: UUID
    title: str
    updated_at: datetime


@dataclass(frozen=True)
class StoredMessage:
    id: UUID
    role: Role
    content: str
    status: MessageStatus
    created_at: datetime


@dataclass(frozen=True)
class ConversationDetail:
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[StoredMessage] = field(default_factory=list)


@dataclass(frozen=True)
class QuotaState:
    messages_used_today: int
    messages_limit: int
    service_available: bool


type Cursor = tuple[datetime, UUID]


class Store(Protocol):
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
        """Vérifie les quotas, réserve un message, crée ou retrouve la conversation, enregistre le
        message de l'utilisateur et lit l'historique : en une seule transaction.

        Lève `AppError` : `not_found`, `quota_global_daily`, `quota_user_daily`.
        """
        ...

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
        """Enregistre la réponse de l'assistant et ajoute les tokens au compteur du jour."""
        ...

    async def list_conversations(
        self, user_id: UUID, limit: int, cursor: Cursor | None
    ) -> list[ConversationSummary]:
        """Au plus `limit + 1` éléments, du plus récent au plus ancien (le dernier : une suite)."""
        ...

    async def get_conversation(
        self, user_id: UUID, conversation_id: UUID
    ) -> ConversationDetail | None: ...

    async def rename_conversation(
        self, user_id: UUID, conversation_id: UUID, title: str
    ) -> ConversationSummary | None: ...

    async def delete_conversation(self, user_id: UUID, conversation_id: UUID) -> bool: ...

    async def get_quota(
        self, user_id: UUID, *, daily_limit: int, global_token_limit: int
    ) -> QuotaState: ...
