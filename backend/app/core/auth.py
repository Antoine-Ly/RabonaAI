"""Authentification : vérification du JWT Supabase (conception §4).

Dépendance FastAPI unique pour toutes les routes protégées. Toute erreur renvoie `401 unauthorized`,
sans détailler la cause (le détail va dans les journaux, jamais le jeton).
"""

import logging
from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

# Clés asymétriques seulement (le projet signe en ES256, V3) : aucun secret partagé à protéger.
ALGORITHMS = ["ES256", "RS256"]
UNAUTHORIZED = AppError(ErrorCode.UNAUTHORIZED, "Authentification requise.")

type KeyResolver = Callable[[str], Any]


class JWTVerifier:
    """Vérifie signature, expiration, audience et émetteur ; renvoie le `sub` (identifiant)."""

    def __init__(
        self,
        key_resolver: KeyResolver,
        *,
        audience: str,
        issuer: str,
        leeway_seconds: int,
    ) -> None:
        self._key_resolver = key_resolver
        self._audience = audience
        self._issuer = issuer
        self._leeway = leeway_seconds

    def verify(self, token: str) -> UUID:
        try:
            key = self._key_resolver(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,  # écart d'horloge observé en V3 (≈ 2 s)
                options={"require": ["exp", "sub", "aud"]},
            )
            return UUID(str(claims["sub"]))
        except (jwt.PyJWTError, ValueError) as exc:
            logger.info("JWT refusé : %s", type(exc).__name__)
            raise UNAUTHORIZED from exc


def build_verifier(settings: Settings) -> JWTVerifier | None:
    """`None` si `SUPABASE_URL` n'est pas renseignée (développement sans authentification)."""
    if not settings.supabase_url:
        return None
    base = settings.supabase_url.rstrip("/")
    # PyJWKClient met les clés en cache et recharge la liste quand le `kid` est inconnu.
    jwks = PyJWKClient(f"{base}/auth/v1/.well-known/jwks.json", cache_keys=True, timeout=5)
    return JWTVerifier(
        lambda token: jwks.get_signing_key_from_jwt(token).key,
        audience=settings.supabase_jwt_audience,
        issuer=f"{base}/auth/v1",
        leeway_seconds=settings.jwt_leeway_seconds,
    )


_bearer = HTTPBearer(auto_error=False)


def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> UUID:
    """Identifiant de l'utilisateur authentifié. Fonction synchrone : FastAPI l'exécute dans un
    thread, ce qui convient au téléchargement (bloquant) de la liste de clés."""
    verifier: JWTVerifier | None = request.app.state.auth
    if verifier is None:
        logger.error("SUPABASE_URL absente : routes protégées indisponibles")
        raise AppError(ErrorCode.INTERNAL_ERROR, "Erreur interne du serveur.")
    if credentials is None:
        raise UNAUTHORIZED
    return verifier.verify(credentials.credentials)


CurrentUser = Annotated[UUID, Depends(current_user)]
