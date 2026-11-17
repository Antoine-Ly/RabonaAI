"""Implémentation Groq de `LLMClient` : streaming et erreurs normalisées (cadrage §4.3).

Réglages repris de V1 pour que les mesures de l'ADR 0001 restent valides : température 0,2,
effort de raisonnement par défaut. Le raisonnement du modèle n'est jamais relayé.
"""

import asyncio
import logging
import math
import time
from collections.abc import AsyncIterator

import groq
from groq import AsyncGroq

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.services.llm.base import Finished, LLMEvent, TextDelta, Usage

logger = logging.getLogger(__name__)

TEMPERATURE = 0.2
READ_TIMEOUT_S = 30.0  # attente maximale sans fragment, premier token compris (I)
TOTAL_TIMEOUT_S = 60.0  # durée maximale d'un flux (I)
MAX_RETRY_WAIT_S = 15.0  # au-delà, pas de réessai sur une limite par minute
DEFAULT_RETRY_WAIT_S = 5.0  # si Groq n'envoie pas d'en-tête retry-after (I)

MSG_UNAVAILABLE = "Le service de langage est momentanément indisponible. Réessayez dans un instant."
MSG_DAILY_LIMIT = "Le service a atteint sa limite quotidienne. Réessayez demain."
MSG_INTERNAL = "Erreur interne du serveur."


class GroqClient:
    def __init__(self, client: AsyncGroq, model: str, max_completion_tokens: int) -> None:
        self._client = client
        self._model = model
        self._max_completion_tokens = max_completion_tokens

    async def check_model(self) -> None:
        """Journalise une erreur si le modèle configuré n'est plus listé (retrait par Groq)."""
        try:
            models = await self._client.models.list()
        except Exception:  # démarrage : jamais bloquant
            logger.warning("Liste des modèles Groq indisponible : vérification ignorée")
            return
        if self._model not in {m.id for m in models.data}:
            logger.error(
                "Modèle %s absent de la liste Groq : retiré ou mal orthographié ?", self._model
            )

    async def stream(self, system: str, messages: list[dict[str, str]]) -> AsyncIterator[LLMEvent]:
        for attempt in (1, 2):
            started = False
            try:
                async for event in self._stream_once(system, messages):
                    started = True
                    yield event
                return
            except groq.RateLimitError as exc:
                if _is_daily_limit(exc):
                    logger.warning("Limite quotidienne Groq atteinte")
                    raise AppError(ErrorCode.QUOTA_GLOBAL_DAILY, MSG_DAILY_LIMIT) from exc
                wait = _retry_after(exc)
                if started or attempt == 2 or wait > MAX_RETRY_WAIT_S:
                    logger.warning(
                        "Limite Groq par minute : abandon (attente demandée %.0f s)", wait
                    )
                    raise AppError(
                        ErrorCode.LLM_UNAVAILABLE,
                        MSG_UNAVAILABLE,
                        retry_after_seconds=math.ceil(wait),
                    ) from exc
                logger.warning("Limite Groq par minute : nouvel essai dans %.1f s", wait)
                await asyncio.sleep(wait)
            except groq.APIConnectionError as exc:  # inclut les dépassements de délai
                logger.warning("Groq injoignable : %s", type(exc).__name__)
                raise AppError(ErrorCode.LLM_UNAVAILABLE, MSG_UNAVAILABLE) from exc
            except groq.APIStatusError as exc:
                if exc.status_code >= 500:
                    logger.warning("Erreur serveur Groq : %s", exc.status_code)
                    raise AppError(ErrorCode.LLM_UNAVAILABLE, MSG_UNAVAILABLE) from exc
                # 400, 401, 403, 404… : requête, clé ou modèle à corriger côté configuration.
                logger.error("Erreur de configuration Groq : HTTP %s", exc.status_code)
                raise AppError(ErrorCode.INTERNAL_ERROR, MSG_INTERNAL) from exc

    async def _stream_once(
        self, system: str, messages: list[dict[str, str]]
    ) -> AsyncIterator[LLMEvent]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}, *messages],
            stream=True,
            temperature=TEMPERATURE,
            max_completion_tokens=self._max_completion_tokens,
        )
        began = time.monotonic()
        finish_reason: str | None = None
        usage: Usage | None = None
        async with stream:
            async for chunk in stream:
                if time.monotonic() - began > TOTAL_TIMEOUT_S:
                    logger.warning("Flux Groq trop long : interrompu")
                    raise AppError(ErrorCode.LLM_UNAVAILABLE, MSG_UNAVAILABLE)
                if chunk.choices:
                    choice = chunk.choices[0]
                    if choice.delta.content:
                        yield TextDelta(choice.delta.content)
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                x_groq = chunk.x_groq
                if x_groq is not None and x_groq.error:
                    logger.warning("Erreur signalée par Groq dans le flux")
                    raise AppError(ErrorCode.LLM_UNAVAILABLE, MSG_UNAVAILABLE)
                # Le décompte des tokens arrive dans le dernier fragment (V1, S).
                counts = chunk.usage or (x_groq.usage if x_groq is not None else None)
                if counts is not None:
                    usage = Usage(counts.prompt_tokens or 0, counts.completion_tokens or 0)
        yield Finished(finish_reason, usage)


def _is_daily_limit(exc: groq.RateLimitError) -> bool:
    # Le message Groq nomme la limite atteinte, par exemple « tokens per day (TPD) » (V).
    message = str(exc).lower()
    return "per day" in message or "(tpd)" in message or "(rpd)" in message


def _retry_after(exc: groq.RateLimitError) -> float:
    try:
        return max(0.0, float(exc.response.headers["retry-after"]))
    except KeyError, ValueError:
        return DEFAULT_RETRY_WAIT_S


def build_groq_client(settings: Settings) -> GroqClient | None:
    """`None` si la clé est absente (développement sans clé : `/chat` renvoie une erreur 500)."""
    if settings.groq_api_key is None:
        return None
    sdk = AsyncGroq(
        api_key=settings.groq_api_key.get_secret_value(),
        max_retries=0,  # les réessais sont gérés ici, pas par le SDK
        timeout=READ_TIMEOUT_S,
    )
    return GroqClient(sdk, settings.groq_model, settings.max_completion_tokens)
