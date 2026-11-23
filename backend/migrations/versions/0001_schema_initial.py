"""Schéma initial (conception §6.1).

Idempotent : le schéma de la phase 0 (`schema.sql`, déjà exécuté sur le projet Supabase) est adopté
tel quel par `alembic upgrade head`, sans erreur ni modification.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists public.conversations (
          id          uuid primary key default gen_random_uuid(),
          user_id     uuid not null references auth.users(id) on delete cascade,
          title       text not null default 'Nouvelle conversation'
                      check (char_length(title) <= 120),
          created_at  timestamptz not null default now(),
          updated_at  timestamptz not null default now()
        )
        """
    )
    op.execute(
        "create index if not exists conversations_user_updated_idx "
        "on public.conversations (user_id, updated_at desc)"
    )
    op.execute(
        """
        create table if not exists public.messages (
          id                 uuid primary key default gen_random_uuid(),
          conversation_id    uuid not null references public.conversations(id) on delete cascade,
          role               text not null check (role in ('user', 'assistant')),
          content            text not null,
          status             text not null default 'complete'
                             check (status in ('complete', 'partial', 'error')),
          model              text,
          prompt_tokens      integer,
          completion_tokens  integer,
          tool_calls         jsonb,
          created_at         timestamptz not null default now()
        )
        """
    )
    op.execute(
        "create index if not exists messages_conversation_created_idx "
        "on public.messages (conversation_id, created_at)"
    )
    op.execute(
        """
        create table if not exists public.usage_daily (
          day       date    not null,
          user_id   uuid    not null references auth.users(id) on delete cascade,
          messages  integer not null default 0,
          tokens    integer not null default 0,
          primary key (day, user_id)
        )
        """
    )
    # Défense en profondeur : RLS activé, aucune politique (le backend se connecte directement).
    for table in ("conversations", "messages", "usage_daily"):
        op.execute(f"alter table public.{table} enable row level security")


def downgrade() -> None:
    op.execute("drop table if exists public.messages")
    op.execute("drop table if exists public.conversations")
    op.execute("drop table if exists public.usage_daily")
