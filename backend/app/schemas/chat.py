"""Modèles Pydantic de `POST /chat` (conception §3.2)."""

from uuid import UUID

from pydantic import BaseModel


class ChatRequest(BaseModel):
    # La longueur maximale (MAX_MESSAGE_CHARS, configurable) est contrôlée dans la route.
    conversation_id: UUID | None = None  # `None` : une conversation est créée
    message: str
