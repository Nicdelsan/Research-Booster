"""Motore delle anomalie: deviazioni dal modello atteso, con significatività corretta per il fattore di prova.

Il sistema non dice mai "scoperta": restituisce anomalie candidate con un livello di evidenza globale
e la lista dei controlli sistematici da fare prima di salire di livello.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import curve_fit

SYSTEMATIC_CHECKS = [
    "Verificare la calibrazione dello strumento nell'intervallo segnalato",
    "Controllare nei log di acquisizione cambi di setup, campione o condizioni",
    "Verificare la deriva temporale dei residui",
    "Confrontare con risultati di letteratura nello stesso intervallo",
    "Ripetere la misura in cieco o su un campione indipendente",
]


@dataclass
class AnomalyCandidate:
    x_start: float
    x_end: float
    n_points: int
    mean_z: float
    chi2: float
    local_p: float
    local_sigma: float
    global_p: float
    global_sigma: float
    level: str
    checks: list[str] = field(default_factory=lambda: list(SYSTEMATIC_CHECKS))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanResult:
    candidates: list[AnomalyCandidate]
    trials: int
    sigma_used: str
    baseline: str

    def to_dict(self) -> dict:
        return {"candidates": [c.to_dict() for c in self.candidates], "trials": self.trials,
                "sigma_used": self.sigma_used, "baseline": self.baseline}


def p_to_sigma(p: float) -> float:
    """Significatività unilaterale equivalente (convenzione della fisica delle particelle)."""
    return float(stats.norm.isf(min(max(p, 1e-300), 1.0)))


def evidence_level(global_sigma: float) -> str:
    if global_sigma >= 5:
        return "anomalia forte"
    if global_sigma >= 3:
        return "evidenza candidata"
    if global_sigma >= 2:
        return "indizio"
    return "nessuna"


def _robust_sigma(r: np.ndarray) -> float:
    mad = np.median(np.abs(r - np.median(r)))
    return float(1.4826 * mad) if mad > 0 else float(np.std(r) or 1.0)


def _fit_baseline(x: np.ndarray, y: np.ndarray, degree: int, model: Callable | None, p0, mask: np.ndarray):
    if model is not None:
        params, _ = curve_fit(model, x[mask], y[mask], p0=p0, maxfev=20000)
        return lambda xx: model(xx, *params), f"modello utente, parametri {np.round(params, 6).tolist()}"
    coefs = np.polyfit(x[mask], y[mask], degree)
    return np.poly1d(coefs), f"polinomio di grado {degree}"


def scan_residuals(
    x: Sequence[float],
    y: Sequence[float],
    *,
    sigma: Sequence[float] | float | None = None,
    degree: int = 3,
    model: Callable | None = None,
    p0: Sequence[float] | None = None,
    min_width: int = 3,
    max_width: int | None = None,
    max_candidates: int = 3,
    clip_sigma: float = 3.0,
    min_global_sigma: float = 2.0,
) -> ScanResult:
    """Cerca finestre contigue in cui i residui rispetto al modello atteso sono incompatibili con il rumore.

    Per ogni finestra si calcola chi2 = somma di z^2 con tanti gradi di libertà quanti punti. La correzione
    look-elsewhere usa Šidák sul numero totale di finestre provate: è conservativa, perché finestre
    sovrapposte sono correlate.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.shape != y.shape or x.size < 2 * min_width + degree + 1:
        raise ValueError("Dati insufficienti o x e y di lunghezza diversa.")
    order = np.argsort(x)
    x, y = x[order], y[order]
    if sigma is not None and np.ndim(sigma) > 0:
        sig = np.asarray(sigma, dtype=float)[order]
    else:
        sig = None

    # Fit robusto: si escludono iterativamente i punti più lontani, così l'anomalia non "trascina" il modello.
    mask = np.ones_like(x, dtype=bool)
    for _ in range(3):
        f, desc = _fit_baseline(x, y, degree, model, p0, mask)
        r = y - f(x)
        s = sig if sig is not None else (float(sigma) if sigma is not None else _robust_sigma(r[mask]))
        new_mask = np.abs(r / s) < clip_sigma
        if new_mask.sum() < degree + 2 or (new_mask == mask).all():
            break
        mask = new_mask
    if sig is not None:
        sigma_desc = "incertezze per punto fornite"
    elif sigma is not None:
        sigma_desc = f"incertezza costante {float(sigma):g}"
    else:
        sigma_desc = f"stima robusta dai residui (MAD) = {float(s):.4g}"
    z = r / s

    n = z.size
    max_width = max_width or max(min_width, n // 5)
    cs = np.concatenate([[0.0], np.cumsum(z ** 2)])
    cz = np.concatenate([[0.0], np.cumsum(z)])
    windows = []
    trials = 0
    for w in range(min_width, max_width + 1):
        chi2 = cs[w:] - cs[:-w]
        pvals = stats.chi2.sf(chi2, w)
        trials += chi2.size
        for i in np.argsort(pvals)[:max_candidates * 3]:
            windows.append((float(pvals[i]), int(i), w, float(chi2[i]), float((cz[i + w] - cz[i]) / w)))
    windows.sort(key=lambda t: t[0])

    chosen, used = [], np.zeros(n, dtype=bool)
    for p, i, w, chi2, mz in windows:
        if used[i:i + w].any():
            continue
        used[i:i + w] = True
        p_global = float(-np.expm1(trials * np.log1p(-min(p, 1 - 1e-16))))
        g_sigma = p_to_sigma(p_global)
        if g_sigma < min_global_sigma:
            break  # le finestre sono ordinate per p locale: le successive sono ancora meno significative
        chosen.append(AnomalyCandidate(
            x_start=float(x[i]), x_end=float(x[i + w - 1]), n_points=w, mean_z=round(mz, 3), chi2=round(chi2, 3),
            local_p=p, local_sigma=round(p_to_sigma(p), 3), global_p=p_global, global_sigma=round(g_sigma, 3),
            level=evidence_level(g_sigma),
        ))
        if len(chosen) >= max_candidates:
            break
    return ScanResult(candidates=chosen, trials=trials, sigma_used=sigma_desc, baseline=desc)


def drift_check(residuals: Sequence[float], timestamps: Sequence[float]) -> dict:
    """Correlazione di rango tra residui e tempo: una correlazione forte suggerisce una deriva strumentale."""
    rho, p = stats.spearmanr(residuals, timestamps)
    return {"spearman_rho": float(rho), "p_value": float(p), "drift_suspected": bool(p < 0.01 and abs(rho) > 0.3)}


def detect_outliers(df: pd.DataFrame, columns: Sequence[str] | None = None, *, contamination: float | str = "auto",
                    random_state: int = 0) -> pd.DataFrame:
    """Punti anomali in dati tabellari multivariati (Isolation Forest). Aggiunge 'anomaly_score' e 'is_outlier'."""
    from sklearn.ensemble import IsolationForest

    cols = list(columns) if columns else df.select_dtypes("number").columns.tolist()
    if not cols:
        raise ValueError("Nessuna colonna numerica da analizzare.")
    data = df[cols].to_numpy(dtype=float)
    ok = np.isfinite(data).all(axis=1)
    model = IsolationForest(contamination=contamination, random_state=random_state).fit(data[ok])
    out = df.copy()
    out["anomaly_score"] = np.nan
    out["is_outlier"] = False
    out.loc[ok, "anomaly_score"] = -model.score_samples(data[ok])
    out.loc[ok, "is_outlier"] = model.predict(data[ok]) == -1
    return out
