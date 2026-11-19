"""Retours compacts des outils (conception §2.2) : texte à barres verticales, jamais le JSON brut.

Les textes venus de l'API sont des données : on retire barres verticales et caractères de contrôle.
"""

import re
from datetime import datetime
from typing import Any

from app.core.clock import PARIS

FINISHED = {"FINISHED", "AWARDED"}
LIVE = {"IN_PLAY", "PAUSED"}
UPCOMING = {"TIMED", "SCHEDULED", "POSTPONED"}
STATUS_LABELS = {
    "FINISHED": "terminé", "AWARDED": "terminé", "IN_PLAY": "en cours", "PAUSED": "en cours",
    "TIMED": "à venir", "SCHEDULED": "à venir", "POSTPONED": "reporté", "SUSPENDED": "suspendu",
    "CANCELLED": "annulé",
}  # fmt: skip
MAX_LINES = 10  # matchs « récents » et « à venir »
NO_MATCH = "aucun match dans la période"
NO_DATA = "aucune donnée disponible"
UNSAFE = re.compile(r"[|\x00-\x1f\x7f]")


def _clean(value: object) -> str:
    return UNSAFE.sub(" ", str(value)).strip()


def _team(team: dict[str, Any]) -> str:
    return _clean(team.get("shortName") or team.get("name") or "?")


def _season(season: dict[str, Any]) -> str:
    start, end = str(season.get("startDate", ""))[:4], str(season.get("endDate", ""))[:4]
    return start if start == end else f"{start}-{end}"


def _header(
    title: str,
    label: str,
    season: dict[str, Any],
    retrieved_at: datetime,
    matchday: int | None = None,
) -> str:
    stamp = retrieved_at.astimezone(PARIS).strftime("%Y-%m-%d %H:%M")
    parts = [f"{title} {label}"]
    if season.get("startDate"):  # absente d'une fenêtre sans aucun match
        parts.append(f"saison {_season(season)}")
    if matchday is not None:
        parts.append(f"journée {matchday}")
    parts.append(f"récupéré le {stamp} (Paris)")
    return " | ".join(parts)


def format_standings(data: dict[str, Any], label: str, retrieved_at: datetime) -> str:
    season = data.get("season", {})
    tables = data.get("standings", [])
    table = next((t for t in tables if t.get("type") == "TOTAL"), tables[0] if tables else None)
    head = _header("Classement", label, season, retrieved_at, season.get("currentMatchday"))
    if not table or not table.get("table"):
        return f"{head}\n{NO_DATA}"
    lines = [head, "rang|équipe|J|V|N|D|diff|pts"]
    for row in table["table"]:
        cells = [
            row.get(k) for k in ("playedGames", "won", "draw", "lost", "goalDifference", "points")
        ]
        lines.append("|".join(map(str, [row.get("position"), _team(row.get("team", {})), *cells])))
    return "\n".join(lines)


def _kickoff(match: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(match["utcDate"]).astimezone(PARIS)


def _match_line(match: dict[str, Any]) -> str:
    status = match.get("status", "")
    kickoff = _kickoff(match)
    if status in FINISHED:  # match passé : la date seule
        when = kickoff.strftime("%Y-%m-%d")
        full_time = match.get("score", {}).get("fullTime", {})
        score = "-" if full_time.get("home") is None else f"{full_time['home']}-{full_time['away']}"
    else:  # à venir ou en cours : date et heure de Paris, jamais de score (pas de direct)
        when, score = kickoff.strftime("%Y-%m-%d %H:%M"), "-"
    teams = (_team(match.get("homeTeam", {})), _team(match.get("awayTeam", {})))
    return "|".join(
        [when, teams[0], score, teams[1], STATUS_LABELS.get(status, _clean(status.lower()))]
    )


def format_matches(
    data: dict[str, Any], label: str, scope: str, matchday: int | None, retrieved_at: datetime
) -> str:
    matches = sorted(data.get("matches", []), key=lambda m: m["utcDate"])
    season = (
        matches[0].get("season", {}) if matches else {}
    )  # la saison est portée par chaque match
    if scope == "recent":
        matches = [m for m in matches if m.get("status") in FINISHED | LIVE][-MAX_LINES:]
        title = "Résultats récents"
    elif scope == "upcoming":
        matches = [m for m in matches if m.get("status") in UPCOMING][:MAX_LINES]
        title = "Matchs à venir"
    else:  # une journée complète : jusqu'à 18 matchs en Ligue des champions
        title = f"Matchs de la journée {matchday}"
    head = _header(title, label, season, retrieved_at)
    if not matches:
        return f"{head}\n{NO_MATCH}"
    return "\n".join([head, "date|domicile|score|extérieur|statut", *map(_match_line, matches)])


def format_scorers(data: dict[str, Any], label: str, retrieved_at: datetime) -> str:
    head = _header("Buteurs", label, data.get("season", {}), retrieved_at)
    scorers = data.get("scorers", [])
    if not scorers:
        return f"{head}\n{NO_DATA}"
    lines = [head, "rang|joueur|équipe|buts"]
    for rank, row in enumerate(scorers, start=1):
        player = _clean(row.get("player", {}).get("name", "?"))
        lines.append(f"{rank}|{player}|{_team(row.get('team', {}))}|{row.get('goals')}")
    return "\n".join(lines)
