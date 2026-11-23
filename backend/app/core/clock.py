"""Fuseau horaire de l'application : les dates affichées à l'utilisateur sont à l'heure de Paris."""

import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def next_utc_midnight(now: datetime | None = None) -> datetime:
    """Début du prochain jour UTC : la journée des quotas est en UTC (conception §5.1)."""
    current = (now or datetime.now(UTC)).astimezone(UTC)
    return current.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)


def seconds_until_utc_midnight(now: datetime | None = None) -> int:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    return max(1, math.ceil((next_utc_midnight(current) - current).total_seconds()))
