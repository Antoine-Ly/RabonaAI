"""Cache TTL en mémoire, avec une seule exécution par clé quand plusieurs requêtes se croisent."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable

from cachetools import TTLCache


class AsyncTTLCache:
    def __init__(
        self, ttl_seconds: float, maxsize: int = 256, timer: Callable[[], float] = time.monotonic
    ) -> None:
        self._cache: TTLCache[Hashable, str] = TTLCache(
            maxsize=maxsize, ttl=ttl_seconds, timer=timer
        )
        self._locks: dict[Hashable, asyncio.Lock] = {}  # bornée par le nombre de clés possibles

    async def get_or_fetch(self, key: Hashable, fetch: Callable[[], Awaitable[str]]) -> str:
        if key in self._cache:
            return self._cache[key]
        async with self._locks.setdefault(key, asyncio.Lock()):
            if key in self._cache:  # une requête concurrente vient de remplir le cache
                return self._cache[key]
            value = await fetch()  # une erreur n'est jamais mise en cache
            self._cache[key] = value
            return value
