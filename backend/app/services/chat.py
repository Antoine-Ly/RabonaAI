"""Orchestration du chat : un tour de dialogue, avec au plus un tour d'outils (conception §2.1).

Phase 3 : sans historique ni base. Produit les événements SSE du contrat (conception §3.2) :
`status` (outil en cours), `delta`, puis `done` ou `error`.
"""

import logging
from collections.abc import AsyncIterator
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

from app.core.clock import PARIS
from app.core.errors import AppError, ErrorCode
from app.services.llm.base import (
    Finished,
    LLMClient,
    TextDelta,
    ToolCall,
    ToolCallsRequested,
    Usage,
)
from app.services.toolbox import Toolbox

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "football_system_prompt.md"
MAX_TOOL_CALLS = 3  # l'API exige une réponse par appel demandé ; on borne le coût (I)

MSG_EMPTY = "Le service de langage a renvoyé une réponse vide. Réessayez."

type SSEEvent = tuple[str, dict[str, object]]


@cache
def load_prompt() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8").strip()


def build_system_prompt(now: datetime | None = None) -> str:
    """Prompt du fichier + date du jour à Paris, ajoutée à chaque requête (jamais écrite en dur)."""
    today = (now or datetime.now(PARIS)).astimezone(PARIS).date()
    return f"{load_prompt()}\n\nDate du jour : {today.isoformat()}."


def _error_event(exc: AppError) -> SSEEvent:
    return "error", {
        "code": exc.code.value,
        "message": exc.message,
        "retry_after_seconds": exc.retry_after_seconds,
    }


def _assistant_tool_message(text: str, calls: tuple[ToolCall, ...]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": text or None,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments or "{}"},
            }
            for call in calls
        ],
    }


async def stream_chat(
    llm: LLMClient,
    message: str,
    toolbox: Toolbox | None = None,
    now: datetime | None = None,
) -> AsyncIterator[SSEEvent]:
    emitted = False
    try:
        system = build_system_prompt(now)
        messages: list[dict[str, Any]] = [{"role": "user", "content": message}]
        definitions = toolbox.definitions if toolbox else None
        usages: list[Usage] = []
        finish_reason: str | None = None
        for round_number in (1, 2):  # 1 : question ; 2 : réponse fondée sur les outils
            calls: tuple[ToolCall, ...] = ()
            parts: list[str] = []
            finished: Finished | None = None
            async for event in llm.stream(system, messages, definitions):
                if isinstance(event, TextDelta):
                    emitted = True
                    parts.append(event.text)
                    yield "delta", {"text": event.text}
                elif isinstance(event, ToolCallsRequested):
                    calls = event.calls
                else:
                    finished = event
            if finished is None:  # flux terminé sans `Finished`
                raise AppError(ErrorCode.LLM_UNAVAILABLE, MSG_EMPTY)
            finish_reason = finished.finish_reason
            if finished.usage:
                usages.append(finished.usage)
            # Un second tour d'outils n'est pas pris en charge : l'éventuelle demande est ignorée.
            if not calls or toolbox is None or round_number == 2:
                break
            calls = calls[:MAX_TOOL_CALLS]
            messages.append(_assistant_tool_message("".join(parts), calls))
            for call in calls:
                yield "status", {"tool": call.name, "state": "running"}
                result = await toolbox.run(call.name, call.arguments)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result.text})
        if not emitted:
            raise AppError(ErrorCode.LLM_UNAVAILABLE, MSG_EMPTY)
        yield (
            "done",
            {
                "finish_reason": finish_reason,
                "usage": {
                    "prompt_tokens": sum(u.prompt_tokens for u in usages),
                    "completion_tokens": sum(u.completion_tokens for u in usages),
                }
                if usages
                else None,
            },
        )
    except AppError as exc:
        yield _error_event(exc)
    except Exception:
        # Le détail reste dans les journaux ; jamais de contenu de conversation.
        logger.exception("Erreur inattendue pendant le chat")
        yield _error_event(AppError(ErrorCode.INTERNAL_ERROR, "Erreur interne du serveur."))
