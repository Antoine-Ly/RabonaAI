"""Routes de santé.

`/health` : sans base ni appel externe ; sert au réveil du backend (Render gratuit) et aux sondes.
`/health/db` : une requête triviale vers PostgreSQL ; sert à garder le projet Supabase actif et à
vérifier un déploiement de bout en bout.
"""

import logging

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.core.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)
router = APIRouter(tags=["santé"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
async def health_db(request: Request) -> dict[str, str]:
    engine = request.app.state.engine
    if engine is None:
        raise AppError(ErrorCode.INTERNAL_ERROR, "Base de données non configurée.")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("select 1"))
    except Exception as exc:
        logger.exception("Base de données injoignable")
        raise AppError(ErrorCode.INTERNAL_ERROR, "Base de données injoignable.") from exc
    return {"status": "ok"}
