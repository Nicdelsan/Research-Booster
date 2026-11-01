"""Calibrazione onesta: le confidenze dichiarate si confrontano con gli esiti reali."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def _arrays(probs: Sequence[float], outcomes: Sequence[bool | int]) -> tuple[np.ndarray, np.ndarray]:
    p = np.asarray(probs, dtype=float)
    o = np.asarray(outcomes, dtype=float)
    if p.shape != o.shape or p.size == 0:
        raise ValueError("Servono probabilità ed esiti della stessa lunghezza, non vuoti.")
    if ((p < 0) | (p > 1)).any():
        raise ValueError("Le probabilità devono stare tra 0 e 1.")
    return p, o


def brier_score(probs: Sequence[float], outcomes: Sequence[bool | int]) -> float:
    """0 = perfetto; 0,25 = come dire sempre 50%."""
    p, o = _arrays(probs, outcomes)
    return float(np.mean((p - o) ** 2))


def log_loss(probs: Sequence[float], outcomes: Sequence[bool | int], eps: float = 1e-12) -> float:
    p, o = _arrays(probs, outcomes)
    p = np.clip(p, eps, 1 - eps)
    return float(-np.mean(o * np.log(p) + (1 - o) * np.log(1 - p)))


def reliability_bins(probs: Sequence[float], outcomes: Sequence[bool | int], n_bins: int = 5) -> list[dict]:
    p, o = _arrays(probs, outcomes)
    edges = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    out = []
    for b in range(n_bins):
        mask = idx == b
        if not mask.any():
            continue
        out.append({
            "range": [round(float(edges[b]), 3), round(float(edges[b + 1]), 3)],
            "mean_predicted": float(p[mask].mean()),
            "observed_rate": float(o[mask].mean()),
            "count": int(mask.sum()),
        })
    return out
