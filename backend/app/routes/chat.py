"""`POST /chat` : réponse en flux SSE (conception §3.2). Version réduite jusqu'à la phase 5 :
un seul tour, sans historique, sans base, sans authentification (usage local uniquement).
"""

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.errors import AppError, ErrorCode
from app.schemas.chat import ChatRequest
from app.services.chat import SSEEvent, stream_chat

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


async def _sse(events: AsyncIterator[SSEEvent]) -> AsyncIterator[str]:
    async for name, data in events:
        yield f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(body: ChatRequest, request: Request) -> StreamingResponse:
    settings = request.app.state.settings
    message = body.message.strip()
    if not message or len(message) > settings.max_message_chars:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"Le message doit contenir de 1 à {settings.max_message_chars} caractères.",
        )
    llm = request.app.state.llm
    if llm is None:
        logger.error("GROQ_API_KEY absente : /chat indisponible")
        raise AppError(ErrorCode.INTERNAL_ERROR, "Erreur interne du serveur.")
    return StreamingResponse(
        _sse(stream_chat(llm, message, request.app.state.tools)),
        media_type="text/event-stream",
        # X-Accel-Buffering : empêche un proxy de mettre le flux en mémoire tampon.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
