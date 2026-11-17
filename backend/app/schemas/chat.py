"""Modèles Pydantic de `POST /chat` (conception §3.2, version réduite de la phase 2)."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    # La longueur maximale (MAX_MESSAGE_CHARS, configurable) est contrôlée dans la route.
    message: str
