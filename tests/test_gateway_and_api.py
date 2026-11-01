import io

import numpy as np
import pandas as pd
import pytest

from rb.config import Settings
from rb.llm.gateway import Classification, Gateway, OfflineProvider, PolicyViolation, Route, default_gateway


class FakeCloud:
    name = "cloud"

    def complete(self, system, prompt, *, max_tokens=1024):
        return "cloud"


def test_controlled_data_never_reaches_cloud_model():
    gw = Gateway([Route(FakeCloud(), Classification.INTERNAL, "us", True)])
    assert gw.complete("public", "s", "p")[0] == "cloud"
    with pytest.raises(PolicyViolation):
        gw.complete("controlled", "s", "p")


def test_controlled_data_routed_to_local_model():
    gw = Gateway([Route(FakeCloud(), Classification.INTERNAL, "us", True),
                  Route(OfflineProvider(), Classification.CONTROLLED, "local", True)])
    text, info = gw.complete(Classification.CONTROLLED, "s", "p")
    assert info["location"] == "local" and text.startswith("[offline]")


def test_default_gateway_without_offline_refuses_controlled(monkeypatch):
    gw = default_gateway(Settings(llm_providers="anthropic"))
    with pytest.raises(PolicyViolation):
        gw.route_for("controlled")


def test_api_end_to_end(client):
    assert client.get("/health").json()["status"] == "ok"
    pid = client.post("/projects", json={"name": "Film di MgB2"}).json()["id"]

    buf = io.StringIO()
    pd.DataFrame({"T (K)": [10, 20, 30], "R [ohm]": [1.0, 1.1, 1.3]}).to_csv(buf, index=False)
    up = client.post(f"/projects/{pid}/artifacts", files={"file": ("misure.csv", buf.getvalue(), "text/csv")},
                     data={"classification": "confidential"})
    assert up.status_code == 201, up.text
    assert any(n["type"] == "variable" for n in client.get(f"/projects/{pid}/graph").json()["nodes"])

    card = {
        "statement": "La pendenza dρ/dT sopra 40 K vale 0,05 µΩ·cm/K per scattering elettrone-fonone.",
        "predictions": [{"quantity": "dρ/dT", "unit": "uohm*cm/K", "expected_value": 0.05, "lower": 0.04, "upper": 0.06}],
        "falsification": {"criterion": "Pendenza fuori da [0.04, 0.06] con 3σ", "min_samples": 40},
        "minimal_test": "Quattro punte tra 50 e 150 K",
        "rivals": ["T^2 elettrone-elettrone", "contributo magnetico"],
        "evidence": [{"stance": "supports", "source": "doi:10.1000/x"}, {"stance": "contradicts", "source": "node:y"}],
        "prior": 0.4,
    }
    created = client.post(f"/projects/{pid}/hypotheses", json=card).json()
    assert created["lint"]["passed"]
    client.post(f"/projects/{pid}/hypotheses/{created['id']}/outcome", json={"corroborated": True})
    cal = client.get(f"/projects/{pid}/calibration").json()
    assert cal["n_resolved"] == 1 and cal["brier"] == pytest.approx(0.36)

    assert client.get(f"/projects/{pid}/provenance/verify").json()["intact"] is True


def test_api_rank_and_anomalies(client):
    body = {"priors": {"a": 0.5, "b": 0.5}, "experiments": [
        {"name": "e1", "cost": 1, "measurement_sigma": 0.5, "predictions": {"a": {"mu": 0}, "b": {"mu": 1}}}]}
    r = client.post("/experiments/rank", json=body).json()
    assert r["prior_entropy_bits"] == pytest.approx(1.0) and r["ranking"][0]["name"] == "e1"

    x = np.linspace(0, 10, 200)
    y = 1 + 0.5 * x + np.random.default_rng(0).normal(0, 0.05, 200)
    y[100:108] += 0.4
    res = client.post("/analysis/anomalies", json={"x": x.tolist(), "y": y.tolist(), "sigma": 0.05, "degree": 1}).json()
    assert res["candidates"][0]["level"] == "anomalia forte"


def test_api_errors(client):
    assert client.get("/projects/inesistente/graph").status_code == 404
    pid = client.post("/projects", json={"name": "x"}).json()["id"]
    bad = client.post(f"/projects/{pid}/artifacts", files={"file": ("a.csv", "x,y\n1,2\n", "text/csv")},
                      data={"classification": "segretissimo"})
    assert bad.status_code == 422
