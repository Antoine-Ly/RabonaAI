"""Point d'entrée FastAPI : `uvicorn app.main:app`."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.auth import build_verifier
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.db.postgres import PgStore, build_engine
from app.routes import chat, conversations, health
from app.services.football.tools import build_football_tools
from app.services.llm.groq import GroqClient, build_groq_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if isinstance(app.state.llm, GroqClient):
        await app.state.llm.check_model()
    yield
    await app.state.tools.aclose()
    if app.state.engine is not None:
        await app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    is_prod = settings.app_env == "prod"

    app = FastAPI(
        title="RabonaAI API",
        version="0.1.0",
        docs_url=None if is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if is_prod else "/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.llm = build_groq_client(settings)
    key = settings.football_data_api_key
    app.state.tools = build_football_tools(key.get_secret_value() if key else None)
    app.state.auth = build_verifier(settings)
    database_url = settings.database_url
    app.state.engine = build_engine(database_url.get_secret_value()) if database_url else None
    app.state.store = PgStore(app.state.engine) if app.state.engine is not None else None

    # Authentification par en-tête Bearer, sans cookie : pas de credentials CORS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    return app


app = create_app()
