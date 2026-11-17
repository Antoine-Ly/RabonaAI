"""Interface du client LLM (ADR 0001) : une seule implémentation, `GroqClient`.

Une erreur du fournisseur est toujours convertie en `AppError` (code du contrat d'API) ;
aucune exception du SDK ne sort de cette couche.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class TextDelta:
    """Fragment de la réponse, relayé tel quel."""

    text: str


@dataclass(frozen=True)
class Finished:
    """Dernier événement d'un flux réussi."""

    finish_reason: str | None
    usage: Usage | None


type LLMEvent = TextDelta | Finished


class LLMClient(Protocol):
    def stream(self, system: str, messages: list[dict[str, str]]) -> AsyncIterator[LLMEvent]:
        """Produit des `TextDelta`, puis un `Finished`. Lève `AppError` en cas d'échec."""
        ...
