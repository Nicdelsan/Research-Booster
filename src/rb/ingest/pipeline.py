"""Pipeline di ingestione: file -> artefatto -> nodi e archi del grafo -> record di provenienza."""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from rb import graph, provenance
from rb.ingest.datasets import describe_hdf5, describe_table
from rb.ingest.pdf import parse_pdf
from rb.models import CLASSIFICATIONS, Artifact, Node

DOCUMENT_EXT = {".pdf"}
TABLE_EXT = {".csv", ".tsv", ".parquet"}
HDF5_EXT = {".h5", ".hdf5", ".nxs", ".nx5"}
MAX_QUANTITY_NODES = 200


class IngestError(ValueError):
    pass


def _kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in DOCUMENT_EXT:
        return "document"
    if ext in TABLE_EXT | HDF5_EXT:
        return "dataset"
    return "other"


def ingest_file(session: Session, project_id: str, path: str | Path, *, storage_dir: str | Path,
                classification: str = "internal", original_name: str | None = None, agent: str = "system") -> dict:
    """Ingerisce un file e restituisce un riepilogo. Fa flush ma non commit."""
    src = Path(path)
    if classification not in CLASSIFICATIONS:
        raise IngestError(f"Classificazione non valida: {classification}. Ammesse: {', '.join(CLASSIFICATIONS)}")
    name = original_name or src.name
    digest = provenance.sha256_file(src)

    existing = session.execute(
        select(Artifact).where(Artifact.project_id == project_id, Artifact.sha256 == digest)
    ).scalars().first()
    if existing:
        return {"artifact_id": existing.id, "duplicate": True, "kind": existing.kind, "filename": existing.filename}

    dest_dir = Path(storage_dir) / project_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{digest[:16]}_{Path(name).name}"
    shutil.copyfile(src, dest)

    kind = _kind(Path(name))
    ext = Path(name).suffix.lower()
    try:
        if ext in DOCUMENT_EXT:
            meta = parse_pdf(dest)
        elif ext in TABLE_EXT:
            meta = describe_table(dest)
        elif ext in HDF5_EXT:
            meta = describe_hdf5(dest)
        else:
            meta = {}
    except Exception as exc:  # file corrotto o formato inatteso
        raise IngestError(f"Impossibile leggere {name}: {exc}") from exc

    text = meta.pop("text", None)
    artifact = Artifact(
        project_id=project_id, kind=kind, filename=name, media_type=ext.lstrip(".") or "bin",
        sha256=digest, size_bytes=dest.stat().st_size, classification=classification,
        storage_path=str(dest), meta={k: v for k, v in meta.items() if k not in ("quantities", "variables")},
    )
    session.add(artifact)
    session.flush()
    if text is not None:
        text_path = dest.with_suffix(dest.suffix + ".txt")
        text_path.write_text(text, encoding="utf-8")
        artifact.meta = {**artifact.meta, "text_path": str(text_path)}

    art_node = graph.add_node(session, project_id, kind, name, artifact_id=artifact.id,
                              props={"sha256": digest, "classification": classification})
    created = {"quantities": 0, "variables": 0, "references": 0, "links": 0}

    for ref_type, key in (("doi", "dois"), ("arxiv", "arxiv_ids")):
        for ident in meta.get(key, []):
            ref = graph.get_or_create_node(session, project_id, "reference", f"{ref_type}:{ident}")
            graph.add_edge(session, project_id, art_node, ref, "cites")
            created["references"] += 1

    for q in meta.get("quantities", [])[:MAX_QUANTITY_NODES]:
        label = f"{q['symbol'] + ' = ' if q['symbol'] else ''}{q['value']:g} {q['unit']}"
        qn = graph.add_node(session, project_id, "quantity", label, artifact_id=artifact.id, props=q)
        graph.add_edge(session, project_id, art_node, qn, "reports")
        created["quantities"] += 1

    for v in meta.get("variables", []):
        vn = graph.add_node(session, project_id, "variable", v["name"], artifact_id=artifact.id, props=v)
        graph.add_edge(session, project_id, art_node, vn, "contains")
        created["variables"] += 1

    created["links"] = link_by_dimension(session, project_id, artifact.id)

    provenance.record(session, project_id, "ingest", agent=agent, inputs=[{"sha256": digest, "filename": name}],
                      outputs=[{"artifact_id": artifact.id}], params={"classification": classification})
    return {"artifact_id": artifact.id, "duplicate": False, "kind": kind, "filename": name, "created": created}


def link_by_dimension(session: Session, project_id: str, artifact_id: str, max_links: int = 500) -> int:
    """Collega grandezze citate nei documenti e variabili dei dataset con la stessa dimensione fisica.

    Sono legami candidati (relazione 'same_dimension'), da confermare o scartare: servono al motore
    di anomalie per confrontare valori di letteratura e dati del gruppo.
    """
    nodes = session.execute(
        select(Node).where(Node.project_id == project_id, Node.type.in_(("quantity", "variable")))
    ).scalars().all()
    new = [n for n in nodes if n.artifact_id == artifact_id]
    old = [n for n in nodes if n.artifact_id != artifact_id]
    count = 0
    for a in new:
        dim = a.props.get("dimensionality")
        if not dim:
            continue
        for b in old:
            if b.type == a.type or b.props.get("dimensionality") != dim:
                continue
            graph.add_edge(session, project_id, a, b, "same_dimension", props={"dimensionality": dim, "confirmed": False})
            count += 1
            if count >= max_links:
                return count
    return count
