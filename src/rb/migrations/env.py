"""Ambiente Alembic. L'URL viene da sqlalchemy.url (se impostato) oppure da RB_DATABASE_URL."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context

import rb.models  # noqa: F401  (registra le tabelle nei metadati)
from rb.db import Base, make_engine

config = context.config
if config.config_file_name:  # solo da riga di comando: le chiamate programmatiche non toccano i logger
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or os.getenv("RB_DATABASE_URL", "sqlite:///./research_booster.db")


def _configure(**kwargs) -> None:
    context.configure(target_metadata=target_metadata, compare_type=True, **kwargs)


def run_migrations_offline() -> None:
    url = _url()
    _configure(url=url, literal_binds=True, render_as_batch=url.startswith("sqlite"))
    with context.begin_transaction():
        context.run_migrations()


def _run_with(connection) -> None:
    # SQLite non supporta ALTER TABLE completo: le modifiche future useranno la modalità batch.
    _configure(connection=connection, render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:  # chiamata programmatica da rb.db.upgrade_db
        _run_with(connection)
        return
    engine = make_engine(_url())
    try:
        with engine.connect() as conn:
            _run_with(conn)
            conn.commit()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
