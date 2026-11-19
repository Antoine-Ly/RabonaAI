"""Les trois outils exposés au modèle : validation, cache, limiteur, appel football-data.org."""

import json
import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.clock import PARIS
from app.services.football.cache import AsyncTTLCache
from app.services.football.client import FootballDataClient, FootballDataError, build_http_client
from app.services.football.competitions import COMPETITIONS, Competition
from app.services.football.format import format_matches, format_scorers, format_standings
from app.services.football.limiter import TokenBucket
from app.services.toolbox import ToolResult

logger = logging.getLogger(__name__)

MSG_UNAVAILABLE = "Données momentanément indisponibles."
MSG_NOT_COVERED = "Compétition non couverte."
MSG_BAD_ARGS = "Paramètres invalides."

TTL_STANDINGS_S = (
    15 * 60
)  # (I) les scores de l'offre gratuite sont différés : un TTL court n'apporte rien
TTL_MATCHES_S = 10 * 60
TTL_SCORERS_S = 60 * 60
CALLS_PER_MINUTE = 8  # marge sous le plafond de 10 (S)
RECENT_DAYS = 14  # couvre une trêve internationale ; V2 : fenêtre de 15 jours acceptée (S)
UPCOMING_DAYS = 14

_SLUGS = [c.value for c in Competition]
# Définitions de V1 (mesurées) : courtes et stables, envoyées à chaque requête.
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "get_standings", "description": "Classement actuel d'une competition.",
        "parameters": {"type": "object",
                       "properties": {"competition": {"type": "string", "enum": _SLUGS}},
                       "required": ["competition"]}}},
    {"type": "function", "function": {
        "name": "get_matches", "description": "Matchs d'une competition : recents, a venir, ou d'une journee.",  # noqa: E501
        "parameters": {"type": "object", "properties": {
            "competition": {"type": "string", "enum": _SLUGS},
            "scope": {"type": "string", "enum": ["recent", "upcoming", "matchday"]},
            "matchday": {"type": "integer", "minimum": 1}},
            "required": ["competition", "scope"]}}},
    {"type": "function", "function": {
        "name": "get_top_scorers", "description": "Meilleurs buteurs d'une competition.",
        "parameters": {"type": "object", "properties": {
            "competition": {"type": "string", "enum": _SLUGS},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10}},
            "required": ["competition"]}}},
]  # fmt: skip


class StandingsArgs(BaseModel):
    competition: Competition


class MatchesArgs(BaseModel):
    competition: Competition
    scope: Literal["recent", "upcoming", "matchday"]
    matchday: int | None = Field(default=None, ge=1, le=60)

    @model_validator(mode="after")
    def _matchday_only_for_matchday_scope(self) -> MatchesArgs:
        if self.scope == "matchday" and self.matchday is None:
            raise ValueError("matchday requis")
        if self.scope != "matchday":
            self.matchday = None
        return self


class ScorersArgs(BaseModel):
    competition: Competition
    limit: int = Field(default=5, ge=1, le=10)


ARG_MODELS: dict[str, type[BaseModel]] = {
    "get_standings": StandingsArgs,
    "get_matches": MatchesArgs,
    "get_top_scorers": ScorersArgs,
}


def _default_now() -> datetime:
    return datetime.now(PARIS)


class FootballTools:
    definitions = TOOL_DEFINITIONS

    def __init__(
        self,
        client: FootballDataClient,
        now: Callable[[], datetime] = _default_now,
        timer: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._now = now
        self._limiter = TokenBucket(CALLS_PER_MINUTE, timer)
        self._standings = AsyncTTLCache(TTL_STANDINGS_S, timer=timer)
        self._matches = AsyncTTLCache(TTL_MATCHES_S, timer=timer)
        self._scorers = AsyncTTLCache(TTL_SCORERS_S, timer=timer)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def run(self, name: str, arguments: str) -> ToolResult:
        model = ARG_MODELS.get(name)
        try:
            raw = json.loads(arguments or "{}")
        except ValueError:
            raw = None
        if model is None or not isinstance(raw, dict):
            logger.warning("Appel d'outil invalide : %s", name)
            return ToolResult(MSG_BAD_ARGS, None)
        try:
            args = model.model_validate(raw)
        except ValueError:  # pydantic.ValidationError
            logger.warning("Arguments invalides pour l'outil %s", name)
            known = raw.get("competition") in _SLUGS
            return ToolResult(MSG_BAD_ARGS if known else MSG_NOT_COVERED, None)
        try:
            text = await self._dispatch(args)
        except FootballDataError as exc:
            text = MSG_UNAVAILABLE if exc.kind == "unavailable" else MSG_NOT_COVERED
        return ToolResult(text, args.model_dump(mode="json"))

    async def _dispatch(self, args: BaseModel) -> str:
        if isinstance(args, StandingsArgs):
            return await self._standings.get_or_fetch(
                args.competition, lambda: self._fetch_standings(args)
            )
        if isinstance(args, MatchesArgs):
            key = (args.competition, args.scope, args.matchday, self._now().date())
            return await self._matches.get_or_fetch(key, lambda: self._fetch_matches(args))
        assert isinstance(args, ScorersArgs)
        key = (args.competition, args.limit)
        return await self._scorers.get_or_fetch(key, lambda: self._fetch_scorers(args))

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._limiter.try_acquire():
            logger.warning("Limiteur football-data.org : seau vide")
            raise FootballDataError("unavailable")
        return await self._client.get(path, params)

    async def _fetch_standings(self, args: StandingsArgs) -> str:
        info = COMPETITIONS[args.competition]
        data = await self._get(f"/competitions/{info.code}/standings")
        return format_standings(data, info.label, self._now())

    async def _fetch_matches(self, args: MatchesArgs) -> str:
        info = COMPETITIONS[args.competition]
        today = self._now().date()
        if args.scope == "recent":
            params = {
                "dateFrom": (today - timedelta(days=RECENT_DAYS)).isoformat(),
                "dateTo": today.isoformat(),
            }
        elif args.scope == "upcoming":
            params = {
                "dateFrom": today.isoformat(),
                "dateTo": (today + timedelta(days=UPCOMING_DAYS)).isoformat(),
            }
        else:
            params = {"matchday": args.matchday}
        data = await self._get(f"/competitions/{info.code}/matches", params)
        return format_matches(data, info.label, args.scope, args.matchday, self._now())

    async def _fetch_scorers(self, args: ScorersArgs) -> str:
        info = COMPETITIONS[args.competition]
        data = await self._get(f"/competitions/{info.code}/scorers", {"limit": args.limit})
        return format_scorers(data, info.label, self._now())


def build_football_tools(api_key: str | None) -> FootballTools:
    """Sans clé API, les outils répondent « données indisponibles » (journalisé)."""
    return FootballTools(FootballDataClient(build_http_client(api_key) if api_key else None))
