"""Modèles Pydantic des routes de conversations et de quota (conception §3.4)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, StringConstraints

from app.db.store import MessageStatus, Role

TITLE_MAX_CHARS = 120  # check (char_length(title) <= 120), conception §6.1


class ConversationItem(BaseModel):
    id: UUID
    title: str
    updated_at: datetime


class ConversationPage(BaseModel):
    items: list[ConversationItem]
    next_cursor: str | None


class MessageOut(BaseModel):
    id: UUID
    role: Role
    content: str
    status: MessageStatus
    created_at: datetime


class ConversationOut(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut]


class RenameRequest(BaseModel):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX_CHARS)
    ]


class QuotaOut(BaseModel):
    messages_used_today: int
    messages_limit: int
    service_available: bool
    resets_at: datetime
