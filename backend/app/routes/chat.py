"""`POST /chat` : réponse en flux SSE (conception §3.2), authentifiée, avec historique et quotas."""

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.auth import CurrentUser
from app.core.errors import AppError, ErrorCode
from app.schemas.chat import ChatRequest
from app.services.chat import SSEEvent
from app.services.exchange import persisted_stream

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


async def _sse(events: AsyncIterator[SSEEvent]) -> AsyncIterator[str]:
    async for name, data in events:
        yield f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(body: ChatRequest, request: Request, user_id: CurrentUser) -> StreamingResponse:
    settings = request.app.state.settings
    message = body.message.strip()
    if not message or len(message) > settings.max_message_chars:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"Le message doit contenir de 1 à {settings.max_message_chars} caractères.",
        )
    llm, store = request.app.state.llm, request.app.state.store
    if llm is None or store is None:
        logger.error("GROQ_API_KEY ou DATABASE_URL absente : /chat indisponible")
        raise AppError(ErrorCode.INTERNAL_ERROR, "Erreur interne du serveur.")

    # Avant tout appel externe : quotas, conversation, message de l'utilisateur (erreurs en JSON).
    exchange = await store.begin_exchange(
        user_id,
        body.conversation_id,
        message,
        daily_limit=settings.user_daily_messages,
        global_token_limit=settings.global_daily_tokens,
        history_max=settings.history_max_messages,
    )
    events = persisted_stream(
        store,
        llm,
        request.app.state.tools,
        user_id=user_id,
        exchange=exchange,
        message=message,
        model=settings.groq_model,
    )
    return StreamingResponse(
        _sse(events),
        media_type="text/event-stream",
        # X-Accel-Buffering : empêche un proxy de mettre le flux en mémoire tampon.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
