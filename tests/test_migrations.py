"""Le migrazioni sono l'unica fonte dello schema: devono coincidere con i modelli ed essere reversibili."""

from __future__ import annotations

import io
import threading

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from conftest import requires_postgres
from rb import provenance
from rb.db import Base, downgrade_db, make_session_factory, upgrade_db
from rb.models import Project

APP_TABLES = {"projects", "artifacts", "nodes", "edges", "hypotheses", "provenance"}


def test_upgrade_creates_all_tables_at_head(engine):
    tables = set(inspect(engine).get_table_names())
    assert APP_TABLES <= tables and "alembic_version" in tables
    with engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() == "0002"


def test_models_and_migrations_do_not_drift(engine):
    with engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diffs == [], f"Modelli e migrazioni divergono: generare una nuova migrazione. {diffs}"


def test_downgrade_to_base_and_upgrade_again(engine):
    downgrade_db(engine, "base")
    assert not APP_TABLES & set(inspect(engine).get_table_names())
    upgrade_db(engine)
    assert APP_TABLES <= set(inspect(engine).get_table_names())


def test_upgrade_is_idempotent(engine):
    upgrade_db(engine)  # già a head: nessun errore, nessun cambiamento
    with engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() == "0002"


def test_offline_sql_script_for_postgres():
    """Gli amministratori di database possono ricevere lo script SQL da rivedere, senza connessione."""
    buf = io.StringIO()
    cfg = Config(output_buffer=buf)
    cfg.set_main_option("script_location", "rb:migrations")
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://utente@server/rb")
    command.upgrade(cfg, "head", sql=True)
    sql = buf.getvalue()
    assert sql.count("CREATE TABLE") == len(APP_TABLES) + 1  # più alembic_version
    assert "JSONB" in sql and "CREATE EXTENSION IF NOT EXISTS vector" in sql


@requires_postgres
def test_postgres_uses_jsonb_and_pgvector(engine):
    columns = {c["name"]: c["type"] for c in inspect(engine).get_columns("nodes")}
    assert columns["props"].__class__.__name__ == "JSONB"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar() == 1


@requires_postgres
def test_provenance_chain_survives_concurrent_writers(engine):
    factory = make_session_factory(engine)
    with factory() as s:
        project = Project(name="concorrenza")
        s.add(project)
        s.commit()
        pid = project.id

    errors: list[Exception] = []

    def writer(n: int) -> None:
        try:
            for i in range(15):
                with factory() as s:
                    provenance.record(s, pid, "test.concurrent", params={"writer": n, "i": i})
                    s.commit()
        except Exception as exc:  # pragma: no cover - riportato sotto
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    with factory() as s:
        assert provenance.verify_chain(s, pid) == (True, None)
        count = s.execute(text("SELECT count(*) FROM provenance WHERE project_id = :p"), {"p": pid}).scalar()
        assert count == 60
