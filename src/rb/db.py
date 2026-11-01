"""Accesso al database. PostgreSQL in produzione, SQLite per sviluppo e test (ADR-002).

Lo schema è gestito solo dalle migrazioni Alembic (ADR-008): `init_db` porta il database all'ultima versione.
"""

from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
    return create_engine(url, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", "rb:migrations")
    return cfg


def upgrade_db(engine: Engine, revision: str = "head") -> None:
    cfg = alembic_config()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, revision)


def downgrade_db(engine: Engine, revision: str) -> None:
    cfg = alembic_config()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, revision)


def init_db(engine: Engine) -> None:
    upgrade_db(engine)
