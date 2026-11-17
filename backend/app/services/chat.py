"""Orchestration du chat — phase 2 : un seul tour, sans outils, sans historique ni base.

Produit les événements SSE du contrat (conception §3.2) : `delta`, puis `done` ou `error`.
"""

import logging
from collections.abc import AsyncIterator
from datetime import datetime
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.errors import AppError, ErrorCode
from app.services.llm.base import Finished, LLMClient, TextDelta

logger = logging.getLogger(__name__)

# Prompt temporaire sans outils (ADR 0006) ; remplacé par football_system_prompt.txt en phase 3.
PROMPT_FILE = (
    Path(__file__).resolve().parent.parent / "prompts" / "football_system_prompt_phase2.txt"
)
PARIS = ZoneInfo("Europe/Paris")

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


async def stream_chat(
    llm: LLMClient, message: str, now: datetime | None = None
) -> AsyncIterator[SSEEvent]:
    emitted = False
    try:
        history = [{"role": "user", "content": message}]
        async for event in llm.stream(build_system_prompt(now), history):
            if isinstance(event, TextDelta):
                emitted = True
                yield "delta", {"text": event.text}
            elif isinstance(event, Finished):
                if not emitted:
                    raise AppError(ErrorCode.LLM_UNAVAILABLE, MSG_EMPTY)
                usage = event.usage
                yield (
                    "done",
                    {
                        "finish_reason": event.finish_reason,
                        "usage": usage
                        and {
                            "prompt_tokens": usage.prompt_tokens,
                            "completion_tokens": usage.completion_tokens,
                        },
                    },
                )
                return
        raise AppError(ErrorCode.LLM_UNAVAILABLE, MSG_EMPTY)  # flux terminé sans `Finished`
    except AppError as exc:
        yield _error_event(exc)
    except Exception:
        # Le détail reste dans les journaux ; jamais de contenu de conversation.
        logger.exception("Erreur inattendue pendant le chat")
        yield _error_event(AppError(ErrorCode.INTERNAL_ERROR, "Erreur interne du serveur."))
