"""Limiteur global à seau de jetons (conception §2.4) : protège le plafond de 10 appels/minute."""

import time
from collections.abc import Callable


class TokenBucket:
    def __init__(self, per_minute: int, timer: Callable[[], float] = time.monotonic) -> None:
        self._capacity = float(per_minute)
        self._rate = per_minute / 60
        self._timer = timer
        self._tokens = self._capacity
        self._last = timer()

    def try_acquire(self) -> bool:
        """Prend un jeton s'il y en a un. Sans attente : l'outil répond « indisponible » sinon."""
        now = self._timer()
        self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
        self._last = now
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False
