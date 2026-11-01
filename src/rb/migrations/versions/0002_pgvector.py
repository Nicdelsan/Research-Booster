"""Estensione pgvector su PostgreSQL, se disponibile (base per il recupero semantico del ciclo 1).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-01
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import context, op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    if context.is_offline_mode():
        # Script SQL per un amministratore: niente interrogazioni, si emette il comando da rivedere.
        if context.get_context().dialect.name == "postgresql":
            op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        return
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    available = bind.execute(sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")).scalar()
    if not available:
        log.warning("pgvector non installato sul server: il recupero semantico resterà disattivato.")
        return
    try:
        with bind.begin_nested():  # SAVEPOINT: un errore di permessi non annulla le altre migrazioni
            op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except sa.exc.DBAPIError as exc:
        log.warning("Impossibile creare l'estensione vector (%s): serve un utente con i permessi adeguati.", exc.orig)


def downgrade() -> None:
    if context.get_context().dialect.name == "postgresql":
        op.execute("DROP EXTENSION IF EXISTS vector")
