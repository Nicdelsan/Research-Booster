"""Scheda ipotesi: il formato standard di Research Booster (vedi documento di progetto, motore metodologico)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Prediction(BaseModel):
    quantity: str = Field(description="Grandezza osservabile, per esempio 'T_c'")
    unit: str = Field(default="", description="Unità di misura, compatibile con pint; vuota se adimensionale")
    expected_value: float | None = None
    lower: float | None = None
    upper: float | None = None
    model_sigma: float | None = Field(default=None, ge=0, description="Incertezza della previsione teorica")
    conditions: str = ""
    # Una previsione senza numeri è ammessa dallo schema ma è un errore per il controllo di falsificabilità.


class Falsification(BaseModel):
    observable: str = ""
    criterion: str = Field(default="", description="Quale risultato smentirebbe l'ipotesi, con soglia numerica")
    min_samples: int | None = Field(default=None, ge=1)
    alpha: float | None = Field(default=None, gt=0, lt=1)


class Evidence(BaseModel):
    stance: Literal["supports", "contradicts"]
    source: str = Field(default="", description="DOI, arXiv, id di nodo o di artefatto")
    excerpt: str = ""


class HypothesisCard(BaseModel):
    statement: str = Field(min_length=10)
    mechanism: str = ""
    predictions: list[Prediction] = Field(default_factory=list)
    falsification: Falsification = Field(default_factory=Falsification)
    minimal_test: str = ""
    rivals: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    novelty_notes: str = ""
    prior: float = Field(gt=0, lt=1, description="Probabilità iniziale dichiarata")
    cost: float | None = Field(default=None, gt=0)
    cost_unit: str = "giorni-persona"
    status: Literal["proposed", "testing", "corroborated", "refuted"] = "proposed"
