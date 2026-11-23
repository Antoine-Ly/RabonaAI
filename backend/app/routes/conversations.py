"""Conversations et quota (conception §3.4). Toute requête est filtrée sur le `sub` du JWT."""

import base64
import binascii
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.core.auth import CurrentUser
from app.core.clock import next_utc_midnight
from app.core.errors import AppError, ErrorCode
from app.db.store import ConversationSummary, Cursor, Store
from app.schemas.conversations import (
    ConversationItem,
    ConversationOut,
    ConversationPage,
    MessageOut,
    QuotaOut,
    RenameRequest,
)

router = APIRouter(tags=["conversations"])

MAX_PAGE_SIZE = 50
NOT_FOUND = AppError(ErrorCode.NOT_FOUND, "Conversation introuvable.")


def _store(request: Request) -> Store:
    store: Store | None = request.app.state.store
    if store is None:
        raise AppError(ErrorCode.INTERNAL_ERROR, "Erreur interne du serveur.")
    return store


def encode_cursor(item: ConversationSummary) -> str:
    raw = f"{item.updated_at.isoformat()}|{item.id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> Cursor:
    try:
        stamp, identifier = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(stamp), UUID(identifier)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Curseur invalide.") from exc


def _item(c: ConversationSummary) -> ConversationItem:
    return ConversationItem(id=c.id, title=c.title, updated_at=c.updated_at)


@router.get("/conversations")
async def list_conversations(
    request: Request,
    user_id: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    cursor: str | None = None,
) -> ConversationPage:
    rows = await _store(request).list_conversations(
        user_id, limit, decode_cursor(cursor) if cursor else None
    )
    page = rows[:limit]
    return ConversationPage(
        items=[_item(c) for c in page],
        next_cursor=encode_cursor(page[-1]) if len(rows) > limit else None,
    )


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID, request: Request, user_id: CurrentUser
) -> ConversationOut:
    found = await _store(request).get_conversation(user_id, conversation_id)
    if found is None:
        raise NOT_FOUND
    return ConversationOut(
        id=found.id,
        title=found.title,
        created_at=found.created_at,
        updated_at=found.updated_at,
        messages=[
            MessageOut(
                id=m.id, role=m.role, content=m.content, status=m.status, created_at=m.created_at
            )
            for m in found.messages
        ],
    )


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: UUID,
    body: RenameRequest,
    request: Request,
    user_id: CurrentUser,
) -> ConversationItem:
    renamed = await _store(request).rename_conversation(user_id, conversation_id, body.title)
    if renamed is None:
        raise NOT_FOUND
    return _item(renamed)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID, request: Request, user_id: CurrentUser
) -> Response:
    if not await _store(request).delete_conversation(user_id, conversation_id):
        raise NOT_FOUND
    return Response(status_code=204)


@router.get("/me/quota")
async def get_quota(request: Request, user_id: CurrentUser) -> QuotaOut:
    settings = request.app.state.settings
    state = await _store(request).get_quota(
        user_id,
        daily_limit=settings.user_daily_messages,
        global_token_limit=settings.global_daily_tokens,
    )
    return QuotaOut(
        messages_used_today=state.messages_used_today,
        messages_limit=state.messages_limit,
        service_available=state.service_available,
        resets_at=next_utc_midnight(),
    )
