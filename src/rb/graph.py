"""Operazioni sul grafo della ricerca, su tabelle relazionali (ADR-002: PostgreSQL prima di tutto)."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from rb.models import Edge, Node


def add_node(session: Session, project_id: str, type: str, label: str, *, props: dict | None = None,
             artifact_id: str | None = None) -> Node:
    node = Node(project_id=project_id, type=type, label=label[:500], props=props or {}, artifact_id=artifact_id)
    session.add(node)
    session.flush()
    return node


def get_or_create_node(session: Session, project_id: str, type: str, label: str, *, props: dict | None = None) -> Node:
    stmt = select(Node).where(Node.project_id == project_id, Node.type == type, Node.label == label[:500])
    existing = session.execute(stmt).scalars().first()
    return existing or add_node(session, project_id, type, label, props=props)


def add_edge(session: Session, project_id: str, source: Node, target: Node, relation: str,
             *, props: dict | None = None) -> Edge:
    edge = Edge(project_id=project_id, source_id=source.id, target_id=target.id, relation=relation, props=props or {})
    session.add(edge)
    session.flush()
    return edge


def neighbors(session: Session, node_id: str) -> list[tuple[Edge, Node]]:
    stmt = select(Edge).where(or_(Edge.source_id == node_id, Edge.target_id == node_id))
    out = []
    for edge in session.execute(stmt).scalars():
        other_id = edge.target_id if edge.source_id == node_id else edge.source_id
        out.append((edge, session.get(Node, other_id)))
    return out


def export_graph(session: Session, project_id: str) -> dict:
    nodes = session.execute(select(Node).where(Node.project_id == project_id)).scalars().all()
    edges = session.execute(select(Edge).where(Edge.project_id == project_id)).scalars().all()
    return {
        "nodes": [{"id": n.id, "type": n.type, "label": n.label, "props": n.props, "artifact_id": n.artifact_id}
                  for n in nodes],
        "edges": [{"id": e.id, "source": e.source_id, "target": e.target_id, "relation": e.relation, "props": e.props}
                  for e in edges],
    }
