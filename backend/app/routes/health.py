"""Route de santé : sans base de données ni appel externe.

Sert au réveil du backend (Render gratuit) et à la supervision.
"""

from fastapi import APIRouter

router = APIRouter(tags=["santé"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
