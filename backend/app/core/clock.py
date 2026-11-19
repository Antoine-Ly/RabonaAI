"""Fuseau horaire de l'application : les dates affichées à l'utilisateur sont à l'heure de Paris."""

from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
