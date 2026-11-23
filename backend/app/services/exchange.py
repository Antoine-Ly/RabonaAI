"""Un tour de dialogue persistant : relaie le flux du modèle et enregistre la réponse (§3.2, §5.4).

La réponse est enregistrée à la fin du flux (`complete`). Si le flux s'arrête avant (erreur du
modèle, bouton Stop, onglet fermé), le texte déjà reçu est enregistré avec le statut `partial`.
"""

import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import anyio

from app.db.store import Exchange, MessageStatus, Store
from app.services.chat import SSEEvent, stream_chat
from app.services.llm.base import LLMClient
from app.services.toolbox import Toolbox

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4  # estimation grossière quand le fournisseur ne renvoie pas `usage` (I)


async def persisted_stream(
    store: Store,
    llm: LLMClient,
    tools: Toolbox | None,
    *,
    user_id: UUID,
    exchange: Exchange,
    message: str,
    model: str,
) -> AsyncIterator[SSEEvent]:
    parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    saved = False

    async def save(status: MessageStatus, usage: dict[str, Any] | None = None) -> None:
        nonlocal saved
        saved = True
        content = "".join(parts)
        if not content and status != "complete":
            return  # rien à conserver : seul le message de l'utilisateur reste
        prompt_tokens = completion_tokens = None
        if usage:
            prompt_tokens, completion_tokens = usage["prompt_tokens"], usage["completion_tokens"]
        else:
            completion_tokens = max(1, len(content) // CHARS_PER_TOKEN) if content else None
        try:
            await store.finish_exchange(
                user_id,
                exchange,
                content=content,
                status=status,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                tool_calls=tool_calls or None,
            )
        except Exception:
            # La réponse a déjà été diffusée : on journalise sans interrompre le flux.
            logger.exception("Enregistrement de la réponse impossible")

    yield (
        "meta",
        {
            "conversation_id": str(exchange.conversation_id),
            "user_message_id": str(exchange.user_message_id),
            "assistant_message_id": str(exchange.assistant_message_id),
        },
    )
    try:
        async for name, data in stream_chat(llm, message, tools, history=exchange.history):
            if name == "delta":
                parts.append(str(data["text"]))
            elif name == "status":
                tool_calls.append({"tool": data["tool"]})
            elif name == "done":
                usage = data.get("usage")
                await save("complete", usage if isinstance(usage, dict) else None)
                yield (
                    "done",
                    {
                        "assistant_message_id": str(exchange.assistant_message_id),
                        **data,
                        "quota": {"messages_remaining_today": exchange.messages_remaining_today},
                    },
                )
                return
            elif name == "error":
                await save("partial")
            yield name, data
    finally:
        if not saved:  # annulation (Stop, onglet fermé) : on termine l'écriture malgré l'annulation
            with anyio.CancelScope(shield=True):
                await save("partial")
