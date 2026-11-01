from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rb.api.main import create_app
from rb.config import Settings
from rb.db import init_db, make_engine, make_session_factory
from rb.models import Project


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", storage_dir=str(tmp_path / "storage"),
                    llm_providers="offline")


@pytest.fixture
def session(settings):
    engine = make_engine(settings.database_url)
    init_db(engine)
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
    return TestClient(create_app(settings))
