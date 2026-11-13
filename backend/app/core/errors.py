"""Format d'erreur unique de l'API (conception §3.3).

Corps : {"error": {"code": ..., "message": ..., "retry_after_seconds": ...}}
Aucun détail interne n'est jamais renvoyé au client pour les erreurs inattendues.
"""

import logging
from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    VALIDATION_ERROR = "validation_error"
    QUOTA_USER_DAILY = "quota_user_daily"
    QUOTA_GLOBAL_DAILY = "quota_global_daily"
    RATE_LIMITED = "rate_limited"
    LLM_UNAVAILABLE = "llm_unavailable"
    INTERNAL_ERROR = "internal_error"


HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.QUOTA_USER_DAILY: 429,
    ErrorCode.QUOTA_GLOBAL_DAILY: 429,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.LLM_UNAVAILABLE: 503,
    ErrorCode.INTERNAL_ERROR: 500,
}

_CODE_FOR_STATUS: dict[int, ErrorCode] = {
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    429: ErrorCode.RATE_LIMITED,
}


class AppError(Exception):
    """Erreur métier convertie en réponse JSON au format du contrat."""

    def __init__(
        self, code: ErrorCode, message: str, *, retry_after_seconds: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds


def error_body(
    code: ErrorCode, message: str, retry_after_seconds: int | None = None
) -> dict[str, dict[str, object]]:
    return {
        "error": {
            "code": code.value,
            "message": message,
            "retry_after_seconds": retry_after_seconds,
        }
    }


def _response(
    code: ErrorCode,
    message: str,
    *,
    status_code: int | None = None,
    retry_after_seconds: int | None = None,
) -> JSONResponse:
    headers = {"Retry-After": str(retry_after_seconds)} if retry_after_seconds else None
    return JSONResponse(
        status_code=status_code or HTTP_STATUS[code],
        content=error_body(code, message, retry_after_seconds),
        headers=headers,
    )


async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return _response(exc.code, exc.message, retry_after_seconds=exc.retry_after_seconds)


async def _handle_validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
    return _response(ErrorCode.VALIDATION_ERROR, "Requête invalide.")


async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _CODE_FOR_STATUS.get(exc.status_code)
    if code is None:
        code = ErrorCode.INTERNAL_ERROR if exc.status_code >= 500 else ErrorCode.VALIDATION_ERROR
    message = "Ressource introuvable." if code is ErrorCode.NOT_FOUND else "Requête refusée."
    return _response(code, message, status_code=exc.status_code)


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    # Le détail (pile d'appels) reste dans les journaux ; jamais de contenu de conversation.
    logger.error("Erreur inattendue sur %s %s", request.method, request.url.path, exc_info=exc)
    return _response(ErrorCode.INTERNAL_ERROR, "Erreur interne du serveur.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unexpected)
