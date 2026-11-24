"""RLS sur la table de version d'Alembic.

Alembic crée `public.alembic_version` lui-même ; sans RLS, l'API REST de Supabase l'exposerait en
lecture et en écriture à quiconque possède la clé publique (alerte `rls_disabled_in_public`). Sans
politique, plus aucun accès via l'API ; le backend se connecte directement et n'est pas concerné.

Idempotent : sans effet si la RLS est déjà activée (par exemple à la main dans l'éditeur SQL).

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table public.alembic_version enable row level security")


def downgrade() -> None:
    op.execute("alter table public.alembic_version disable row level security")
