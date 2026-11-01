"""API HTTP di Research Booster. Avvio: uvicorn --factory rb.api.main:create_app"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from rb import __version__, provenance
from rb.config import Settings, get_settings
from rb.db import init_db, make_engine, make_session_factory
from rb.discovery.anomalies import scan_residuals
from rb.graph import export_graph
from rb.hypotheses.calibration import brier_score, reliability_bins
from rb.hypotheses.card import HypothesisCard
from rb.hypotheses.falsifiability import lint
from rb.hypotheses.ranking import Experiment, entropy_bits, rank_experiments, samples_for_discrimination
from rb.ingest.pipeline import IngestError, ingest_file
from rb.models import Artifact, Hypothesis, Project


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OutcomeIn(BaseModel):
    corroborated: bool
    note: str = ""


class RankRequest(BaseModel):
    priors: dict[str, float]
    experiments: list[Experiment] = Field(min_length=1)


class SamplesRequest(BaseModel):
    priors: dict[str, float]
    experiment: Experiment
    target_fraction: float = Field(default=0.9, gt=0, lt=1)


class AnomalyRequest(BaseModel):
    x: list[float] = Field(min_length=10)
    y: list[float] = Field(min_length=10)
    sigma: list[float] | float | None = None
    degree: int = Field(default=3, ge=0, le=10)
    min_width: int = Field(default=3, ge=1)
    max_width: int | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    if settings.auto_migrate:
        init_db(engine)
    session_factory = make_session_factory(engine)

    app = FastAPI(title="Research Booster API", version=__version__)
    app.state.settings = settings
    app.state.engine = engine

    def get_session():
        with session_factory() as session:
            yield session

    def get_project(project_id: str, session: Session) -> Project:
        project = session.get(Project, project_id)
        if project is None:
            raise HTTPException(404, "Progetto non trovato")
        return project

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.post("/projects", status_code=201)
    def create_project(body: ProjectIn, session: Session = Depends(get_session)):
        project = Project(name=body.name)
        session.add(project)
        session.flush()
        provenance.record(session, project.id, "project.create", params={"name": body.name})
        session.commit()
        return {"id": project.id, "name": project.name}

    @app.get("/projects")
    def list_projects(session: Session = Depends(get_session)):
        return [{"id": p.id, "name": p.name} for p in session.execute(select(Project)).scalars()]

    @app.post("/projects/{project_id}/artifacts", status_code=201)
    async def upload_artifact(project_id: str, file: UploadFile = File(...), classification: str = Form("internal"),
                              session: Session = Depends(get_session)):
        get_project(project_id, session)
        name = Path(file.filename or "upload.bin").name
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_bytes(await file.read())
            try:
                summary = ingest_file(session, project_id, path, storage_dir=settings.storage_dir,
                                      classification=classification, original_name=name)
            except IngestError as exc:
                session.rollback()
                raise HTTPException(422, str(exc)) from exc
        session.commit()
        return summary

    @app.get("/projects/{project_id}/artifacts")
    def list_artifacts(project_id: str, session: Session = Depends(get_session)):
        get_project(project_id, session)
        rows = session.execute(select(Artifact).where(Artifact.project_id == project_id)).scalars()
        return [{"id": a.id, "filename": a.filename, "kind": a.kind, "classification": a.classification,
                 "sha256": a.sha256, "meta": a.meta} for a in rows]

    @app.get("/projects/{project_id}/graph")
    def get_graph(project_id: str, session: Session = Depends(get_session)):
        get_project(project_id, session)
        return export_graph(session, project_id)

    @app.post("/hypotheses/lint")
    def lint_hypothesis(card: HypothesisCard):
        return lint(card).to_dict()

    @app.post("/projects/{project_id}/hypotheses", status_code=201)
    def create_hypothesis(project_id: str, card: HypothesisCard, session: Session = Depends(get_session)):
        get_project(project_id, session)
        report = lint(card)
        hyp = Hypothesis(project_id=project_id, statement=card.statement, card=card.model_dump(),
                         lint=report.to_dict(), status=card.status, prior=card.prior)
        session.add(hyp)
        session.flush()
        provenance.record(session, project_id, "hypothesis.create", outputs=[{"hypothesis_id": hyp.id}],
                          params={"lint_passed": report.passed, "score": report.score})
        session.commit()
        return {"id": hyp.id, "lint": report.to_dict()}

    @app.get("/projects/{project_id}/hypotheses")
    def list_hypotheses(project_id: str, session: Session = Depends(get_session)):
        get_project(project_id, session)
        rows = session.execute(select(Hypothesis).where(Hypothesis.project_id == project_id)).scalars()
        return [{"id": h.id, "statement": h.statement, "status": h.status, "prior": h.prior,
                 "outcome": h.outcome, "lint_score": h.lint.get("score")} for h in rows]

    @app.post("/projects/{project_id}/hypotheses/{hypothesis_id}/outcome")
    def record_outcome(project_id: str, hypothesis_id: str, body: OutcomeIn, session: Session = Depends(get_session)):
        hyp = session.get(Hypothesis, hypothesis_id)
        if hyp is None or hyp.project_id != project_id:
            raise HTTPException(404, "Ipotesi non trovata")
        hyp.outcome = body.corroborated
        hyp.status = "corroborated" if body.corroborated else "refuted"
        provenance.record(session, project_id, "hypothesis.outcome", outputs=[{"hypothesis_id": hyp.id}],
                          params={"corroborated": body.corroborated, "note": body.note})
        session.commit()
        return {"id": hyp.id, "status": hyp.status}

    @app.get("/projects/{project_id}/calibration")
    def calibration(project_id: str, session: Session = Depends(get_session)):
        get_project(project_id, session)
        resolved = session.execute(
            select(Hypothesis).where(Hypothesis.project_id == project_id, Hypothesis.outcome.is_not(None))
        ).scalars().all()
        if not resolved:
            return {"n_resolved": 0, "brier": None, "bins": []}
        probs = [h.prior for h in resolved]
        outcomes = [bool(h.outcome) for h in resolved]
        return {"n_resolved": len(resolved), "brier": brier_score(probs, outcomes),
                "bins": reliability_bins(probs, outcomes)}

    @app.post("/experiments/rank")
    def rank(body: RankRequest):
        try:
            return {"prior_entropy_bits": entropy_bits(body.priors),
                    "ranking": [r.to_dict() for r in rank_experiments(body.priors, body.experiments)]}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/experiments/samples")
    def samples(body: SamplesRequest):
        try:
            n = samples_for_discrimination(body.priors, body.experiment, body.target_fraction)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"n_samples": n, "target_fraction": body.target_fraction,
                "note": None if n is not None else "Le ipotesi non sono distinguibili con questo esperimento."}

    @app.post("/analysis/anomalies")
    def anomalies(body: AnomalyRequest):
        try:
            result = scan_residuals(body.x, body.y, sigma=body.sigma, degree=body.degree,
                                    min_width=body.min_width, max_width=body.max_width)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return result.to_dict()

    @app.get("/projects/{project_id}/provenance/verify")
    def verify(project_id: str, session: Session = Depends(get_session)):
        get_project(project_id, session)
        ok, broken = provenance.verify_chain(session, project_id)
        return {"intact": ok, "first_broken_record": broken}

    return app
