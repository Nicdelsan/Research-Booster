import numpy as np
import pandas as pd
import pytest

from rb.discovery.anomalies import detect_outliers, drift_check, evidence_level, scan_residuals


def smooth_curve(n=300, seed=0):
    rng = np.random.default_rng(seed)
    x = np.linspace(10, 300, n)
    y = 2.0 + 0.05 * x + 1e-5 * x ** 2 + rng.normal(0, 0.05, n)
    return x, y


def test_injected_bump_is_found_with_global_significance():
    x, y = smooth_curve()
    bump = (x > 38) & (x < 46)
    y[bump] += 0.35
    result = scan_residuals(x, y, sigma=0.05, degree=2)
    assert result.candidates, "il segnale iniettato deve emergere"
    top = result.candidates[0]
    assert top.x_start <= 46 and top.x_end >= 38
    assert top.global_sigma >= 5 and top.level == "anomalia forte"
    assert top.global_p >= top.local_p  # la correzione look-elsewhere non può aumentare la significatività


def test_pure_noise_gives_no_strong_claims():
    x, y = smooth_curve(seed=1)
    result = scan_residuals(x, y, sigma=0.05, degree=2)
    assert all(c.level in ("nessuna", "indizio") for c in result.candidates)


def test_robust_sigma_when_not_provided():
    x, y = smooth_curve(seed=2)
    y[150:156] += 0.5
    result = scan_residuals(x, y, degree=2)
    assert "MAD" in result.sigma_used
    assert result.candidates and result.candidates[0].global_sigma > 3


def test_evidence_levels():
    assert evidence_level(1.0) == "nessuna"
    assert evidence_level(2.5) == "indizio"
    assert evidence_level(4.0) == "evidenza candidata"
    assert evidence_level(6.0) == "anomalia forte"


def test_drift_check_detects_trend():
    t = np.arange(100.0)
    assert drift_check(0.01 * t + np.random.default_rng(0).normal(0, 0.05, 100), t)["drift_suspected"]


def test_isolation_forest_flags_planted_outlier():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"a": rng.normal(0, 1, 500), "b": rng.normal(0, 1, 500)})
    df.loc[42, ["a", "b"]] = [12.0, -12.0]
    out = detect_outliers(df, contamination=0.01)
    assert bool(out.loc[42, "is_outlier"])
    assert out["anomaly_score"].idxmax() == 42


def test_too_few_points_raises():
    with pytest.raises(ValueError):
        scan_residuals([1, 2, 3], [1, 2, 3])
