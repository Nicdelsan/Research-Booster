"""Fixture comuni. I test girano su SQLite; con RB_TEST_DATABASE_URL girano su PostgreSQL.

Su PostgreSQL ogni test parte da uno schema vuoto (DROP SCHEMA public CASCADE) e lo porta
all'ultima migrazione, così si verificano anche le migrazioni stesse.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from rb.api.main import create_app
from rb.config import Settings
from rb.db import init_db, make_engine, make_session_factory
from rb.models import Project

TEST_DATABASE_URL = os.getenv("RB_TEST_DATABASE_URL")


def is_postgres(url: str) -> bool:
    return url.startswith("postgresql")


requires_postgres = pytest.mark.skipif(
    not (TEST_DATABASE_URL and is_postgres(TEST_DATABASE_URL)), reason="richiede RB_TEST_DATABASE_URL su PostgreSQL"
)


@pytest.fixture
def database_url(tmp_path) -> str:
    if TEST_DATABASE_URL:
        engine = create_engine(TEST_DATABASE_URL)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        engine.dispose()
        return TEST_DATABASE_URL
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def settings(database_url, tmp_path) -> Settings:
    return Settings(database_url=database_url, storage_dir=str(tmp_path / "storage"), llm_providers="offline")


@pytest.fixture
def engine(settings):
    eng = make_engine(settings.database_url)
    init_db(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    with make_session_factory(engine)() as s:
        yield s


@pytest.fixture
def project(session):
    p = Project(name="Test")
    session.add(p)
    session.flush()
    return p


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
    app.state.engine.dispose()
