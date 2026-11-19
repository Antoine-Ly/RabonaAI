"""Contrat entre l'orchestration du chat et les outils exposés au modèle."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolResult:
    text: str  # renvoyé au modèle
    args: dict[str, Any] | None  # arguments validés (None si invalides), pour l'évaluation


class Toolbox(Protocol):
    definitions: list[dict[str, Any]]

    async def run(self, name: str, arguments: str) -> ToolResult:
        """Exécute un outil ; ne lève jamais : toute erreur devient une phrase pour le modèle."""
        ...
