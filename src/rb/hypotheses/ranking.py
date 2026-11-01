"""Progettazione sperimentale bayesiana: quale esperimento distingue meglio le ipotesi rivali, per euro speso.

Modello: ogni ipotesi h_i prevede che l'osservabile y segua una normale N(mu_i, s_i^2), con
s_i^2 = model_sigma_i^2 + measurement_sigma^2 / n_samples. Il guadagno di informazione atteso è
l'informazione mutua I(H; Y) = sum_i p_i * integral N_i(y) * log2(N_i(y) / p(y)) dy, in bit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from pydantic import BaseModel, Field
from scipy.special import logsumexp
from scipy.stats import norm


class HypothesisPrediction(BaseModel):
    mu: float
    model_sigma: float = Field(default=0.0, ge=0)


class Experiment(BaseModel):
    name: str
    cost: float = Field(gt=0)
    measurement_sigma: float = Field(gt=0, description="Incertezza di una singola misura")
    n_samples: int = Field(default=1, ge=1)
    predictions: dict[str, HypothesisPrediction] = Field(description="Previsione di ogni ipotesi, per id")


@dataclass
class RankedExperiment:
    name: str
    eig_bits: float
    cost: float
    priority: float
    max_bits: float

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize(priors: dict[str, float]) -> dict[str, float]:
    total = sum(priors.values())
    if total <= 0 or any(p < 0 for p in priors.values()):
        raise ValueError("Le probabilità iniziali devono essere non negative e non tutte nulle.")
    return {k: v / total for k, v in priors.items()}


def entropy_bits(priors: dict[str, float]) -> float:
    p = np.array([v for v in _normalize(priors).values() if v > 0])
    return float(-(p * np.log2(p)).sum())


def expected_information_gain(priors: dict[str, float], mus: dict[str, float], sigmas: dict[str, float],
                              grid_points: int = 4001) -> float:
    pri = _normalize(priors)
    keys = [k for k in pri if pri[k] > 0]
    if len(keys) < 2:
        return 0.0
    mu = np.array([mus[k] for k in keys])
    sd = np.array([max(sigmas[k], 1e-12) for k in keys])
    p = np.array([pri[k] for k in keys])
    # Griglia unione di griglie locali: precisa anche con incertezze piccole e previsioni lontane.
    y = np.unique(np.concatenate([np.linspace(m - 8 * s, m + 8 * s, grid_points // len(keys) + 1)
                                  for m, s in zip(mu, sd)]))
    # Calcolo in scala logaritmica: evita underflow quando le ipotesi prevedono valori molto lontani.
    log_dens = norm.logpdf(y[None, :], mu[:, None], sd[:, None])      # (ipotesi, griglia)
    log_mix = logsumexp(log_dens + np.log(p)[:, None], axis=0)
    integrand = np.exp(log_dens) * (log_dens - log_mix[None, :]) / np.log(2)
    per_h = np.trapezoid(integrand, y, axis=1)
    return float(max(0.0, (p * per_h).sum()))


def _sigmas(exp: Experiment, n: int | None = None) -> dict[str, float]:
    n = n or exp.n_samples
    return {k: float(np.hypot(pr.model_sigma, exp.measurement_sigma / np.sqrt(n))) for k, pr in exp.predictions.items()}


def experiment_eig(priors: dict[str, float], exp: Experiment, n: int | None = None) -> float:
    missing = set(priors) - set(exp.predictions)
    if missing:
        raise ValueError(f"L'esperimento '{exp.name}' non ha previsioni per: {', '.join(sorted(missing))}")
    mus = {k: pr.mu for k, pr in exp.predictions.items()}
    return expected_information_gain(priors, mus, _sigmas(exp, n))


def rank_experiments(priors: dict[str, float], experiments: list[Experiment]) -> list[RankedExperiment]:
    h0 = entropy_bits(priors)
    ranked = []
    for exp in experiments:
        eig = experiment_eig(priors, exp)
        ranked.append(RankedExperiment(name=exp.name, eig_bits=round(eig, 4), cost=exp.cost,
                                       priority=round(eig / exp.cost, 6), max_bits=round(h0, 4)))
    return sorted(ranked, key=lambda r: r.priority, reverse=True)


def samples_for_discrimination(priors: dict[str, float], exp: Experiment, target_fraction: float = 0.9,
                               n_max: int = 100_000) -> int | None:
    """Numero minimo di misure perché l'esperimento rimuova `target_fraction` dell'incertezza iniziale.

    Restituisce None se non basta nemmeno `n_max` (per esempio se le ipotesi prevedono lo stesso valore
    o l'incertezza teorica domina quella di misura).
    """
    target = target_fraction * entropy_bits(priors)
    if experiment_eig(priors, exp, n_max) < target:
        return None
    lo, hi = 1, 1
    while experiment_eig(priors, exp, hi) < target:
        lo, hi = hi, hi * 2
    while lo < hi:
        mid = (lo + hi) // 2
        if experiment_eig(priors, exp, mid) >= target:
            hi = mid
        else:
            lo = mid + 1
    return lo
