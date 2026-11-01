"""Schema iniziale: progetti, artefatti, grafo, ipotesi, provenienza.

Revision ID: 0001
Revises:
Create Date: 2026-11-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("meta", JSONType, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_artifacts_project_id", "artifacts", ["project_id"])
    op.create_index("ix_artifacts_sha256", "artifacts", ["sha256"])

    op.create_table(
        "nodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("label", sa.String(500), nullable=False),
        sa.Column("props", JSONType, nullable=False),
        sa.Column("artifact_id", sa.String(36), sa.ForeignKey("artifacts.id"), nullable=True),
    )
    op.create_index("ix_nodes_project_id", "nodes", ["project_id"])
    op.create_index("ix_nodes_type", "nodes", ["type"])

    op.create_table(
        "edges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("nodes.id"), nullable=False),
        sa.Column("target_id", sa.String(36), sa.ForeignKey("nodes.id"), nullable=False),
        sa.Column("relation", sa.String(40), nullable=False),
        sa.Column("props", JSONType, nullable=False),
    )
    op.create_index("ix_edges_project_id", "edges", ["project_id"])
    op.create_index("ix_edges_source_id", "edges", ["source_id"])
    op.create_index("ix_edges_target_id", "edges", ["target_id"])

    op.create_table(
        "hypotheses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("card", JSONType, nullable=False),
        sa.Column("lint", JSONType, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("prior", sa.Float(), nullable=False),
        sa.Column("outcome", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_hypotheses_project_id", "hypotheses", ["project_id"])

    op.create_table(
        "provenance",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("activity", sa.String(100), nullable=False),
        sa.Column("agent", sa.String(100), nullable=False),
        sa.Column("inputs", JSONType, nullable=False),
        sa.Column("outputs", JSONType, nullable=False),
        sa.Column("params", JSONType, nullable=False),
        sa.Column("environment", JSONType, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("record_hash", sa.String(64), nullable=False, unique=True),
    )
    op.create_index("ix_provenance_project_id", "provenance", ["project_id"])


def downgrade() -> None:
    for table in ("provenance", "hypotheses", "edges", "nodes", "artifacts", "projects"):
        op.drop_table(table)
