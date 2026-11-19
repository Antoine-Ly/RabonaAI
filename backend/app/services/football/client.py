"""Client HTTP football-data.org (offre gratuite) : toute défaillance devient une erreur typée."""

import logging
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.football-data.org/v4"
TIMEOUT_S = 10.0  # (I)


class FootballDataError(Exception):
    def __init__(self, kind: Literal["unavailable", "not_covered"]) -> None:
        super().__init__(kind)
        self.kind = kind


def build_http_client(api_key: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL, headers={"X-Auth-Token": api_key}, timeout=TIMEOUT_S
    )


class FootballDataClient:
    def __init__(self, http: httpx.AsyncClient | None) -> None:
        self._http = http  # None : pas de clé API configurée

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._http is None:
            logger.error("FOOTBALL_DATA_API_KEY absente : données football indisponibles")
            raise FootballDataError("unavailable")
        try:
            response = await self._http.get(path, params=params)
        except httpx.HTTPError as exc:  # délai dépassé, connexion refusée…
            logger.warning("football-data.org injoignable : %s", type(exc).__name__)
            raise FootballDataError("unavailable") from exc
        if response.headers.get("X-Requests-Available-Minute") == "0":
            logger.warning("Quota par minute football-data.org épuisé")
        if response.status_code == 404:
            logger.warning("football-data.org : 404 sur %s", path)
            raise FootballDataError("not_covered")
        if not response.is_success:  # 403 hors offre gratuite, 429, 5xx
            logger.warning("football-data.org : HTTP %s sur %s", response.status_code, path)
            raise FootballDataError("unavailable")
        try:
            return response.json()
        except ValueError as exc:
            logger.warning("football-data.org : réponse non JSON sur %s", path)
            raise FootballDataError("unavailable") from exc

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
