"""Provenienza nativa: hash dei file, istantanea dell'ambiente, registro a catena di hash."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from rb.models import ProvenanceRecord

GENESIS = "0" * 64
_TRACKED_PACKAGES = ("research-booster", "numpy", "scipy", "pandas", "scikit-learn", "h5py", "pint")


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def sha256_json(obj) -> str:
    return hashlib.sha256(_canonical(obj).encode()).hexdigest()


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def environment_snapshot() -> dict:
    versions = {}
    for pkg in _TRACKED_PACKAGES:
        try:
            versions[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            continue
    env = {"python": sys.version.split()[0], "platform": platform.platform(), "packages": versions}
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=2, check=False
        ).stdout.strip()
        if commit:
            env["git_commit"] = commit
    except (OSError, subprocess.SubprocessError):
        pass
    return env


def _lock_chain(session: Session, project_id: str) -> None:
    """Su PostgreSQL serializza le scritture sulla catena di un progetto fino al commit della transazione.

    Senza il lock due richieste concorrenti leggerebbero lo stesso ultimo hash e la catena si biforcherebbe.
    SQLite serializza già le scritture sull'intero database.
    """
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                        {"key": f"rb-provenance:{project_id}"})


def _last_hash(session: Session, project_id: str) -> str:
    stmt = (
        select(ProvenanceRecord.record_hash)
        .where(ProvenanceRecord.project_id == project_id)
        .order_by(ProvenanceRecord.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none() or GENESIS


def record(
    session: Session,
    project_id: str,
    activity: str,
    *,
    agent: str = "system",
    inputs: list | None = None,
    outputs: list | None = None,
    params: dict | None = None,
) -> ProvenanceRecord:
    """Aggiunge un record alla catena del progetto. Non fa commit."""
    _lock_chain(session, project_id)
    body = {
        "project_id": project_id,
        "activity": activity,
        "agent": agent,
        "inputs": inputs or [],
        "outputs": outputs or [],
        "params": params or {},
        "environment": environment_snapshot(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    prev = _last_hash(session, project_id)
    rec = ProvenanceRecord(**body, prev_hash=prev, record_hash=sha256_json({"prev": prev, **body}))
    session.add(rec)
    session.flush()
    return rec


def verify_chain(session: Session, project_id: str) -> tuple[bool, int | None]:
    """Ricalcola la catena. Restituisce (integra, id del primo record alterato)."""
    stmt = select(ProvenanceRecord).where(ProvenanceRecord.project_id == project_id).order_by(ProvenanceRecord.id)
    prev = GENESIS
    for rec in session.execute(stmt).scalars():
        body = {
            "project_id": rec.project_id,
            "activity": rec.activity,
            "agent": rec.agent,
            "inputs": rec.inputs,
            "outputs": rec.outputs,
            "params": rec.params,
            "environment": rec.environment,
            "created_at": rec.created_at,
        }
        if rec.prev_hash != prev or rec.record_hash != sha256_json({"prev": prev, **body}):
            return False, rec.id
        prev = rec.record_hash
    return True, None
