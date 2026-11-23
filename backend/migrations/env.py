"""Environnement Alembic : connexion synchrone (psycopg 3) à `DATABASE_URL`, sans modèles."""

from alembic import context
from sqlalchemy import create_engine

from app.core.config import get_settings

database_url = get_settings().database_url
if database_url is None:
    raise SystemExit("DATABASE_URL n'est pas renseignée (backend/.env).")

url = database_url.get_secret_value().replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(url)

with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
