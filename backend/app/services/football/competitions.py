"""Compétitions exposées au modèle (ADR 0002) : slugs lisibles, jamais les codes bruts de l'API."""

from dataclasses import dataclass
from enum import StrEnum


class Competition(StrEnum):
    PREMIER_LEAGUE = "premier-league"
    CHAMPIONSHIP = "championship"
    LA_LIGA = "la-liga"
    SERIE_A = "serie-a"
    BUNDESLIGA = "bundesliga"
    LIGUE_1 = "ligue-1"
    EREDIVISIE = "eredivisie"
    PRIMEIRA_LIGA = "primeira-liga"
    CHAMPIONS_LEAGUE = "champions-league"
    BRASILEIRAO = "brasileirao"


@dataclass(frozen=True)
class CompetitionInfo:
    code: str  # code football-data.org
    label: (
        str  # nom affiché dans l'en-tête des retours (pays ajouté quand deux noms se ressemblent)
    )


COMPETITIONS: dict[Competition, CompetitionInfo] = {
    Competition.PREMIER_LEAGUE: CompetitionInfo("PL", "Premier League"),
    Competition.CHAMPIONSHIP: CompetitionInfo("ELC", "Championship"),
    Competition.LA_LIGA: CompetitionInfo("PD", "Liga (Espagne)"),
    Competition.SERIE_A: CompetitionInfo("SA", "Serie A"),
    Competition.BUNDESLIGA: CompetitionInfo("BL1", "Bundesliga (Allemagne)"),
    Competition.LIGUE_1: CompetitionInfo("FL1", "Ligue 1 (France)"),
    Competition.EREDIVISIE: CompetitionInfo("DED", "Eredivisie"),
    Competition.PRIMEIRA_LIGA: CompetitionInfo("PPL", "Primeira Liga"),
    Competition.CHAMPIONS_LEAGUE: CompetitionInfo("CL", "Ligue des champions"),
    Competition.BRASILEIRAO: CompetitionInfo("BSA", "Brasileirao"),
}
