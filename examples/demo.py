"""Dimostrazione end-to-end delle fondamenta di Research Booster (dati sintetici).

Esegui dalla radice del repository:  python examples/demo.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rb import provenance  # noqa: E402
from rb.config import Settings  # noqa: E402
from rb.db import init_db, make_engine, make_session_factory  # noqa: E402
from rb.discovery.anomalies import scan_residuals  # noqa: E402
from rb.graph import export_graph  # noqa: E402
from rb.hypotheses.card import Evidence, Falsification, HypothesisCard, Prediction  # noqa: E402
from rb.hypotheses.falsifiability import lint  # noqa: E402
from rb.hypotheses.ranking import Experiment, HypothesisPrediction, rank_experiments, samples_for_discrimination  # noqa: E402
from rb.ingest.pipeline import ingest_file  # noqa: E402
from rb.llm.gateway import PolicyViolation, default_gateway  # noqa: E402
from rb.models import Project  # noqa: E402


def title(text: str) -> None:
    print(f"\n=== {text} ===")


def make_dataset(folder: Path) -> Path:
    rng = np.random.default_rng(7)
    T = np.linspace(10, 300, 400)
    rho = 1.5 + 0.045 * T + 2e-5 * T ** 2 + rng.normal(0, 0.03, T.size)
    rho[(T > 37) & (T < 44)] += 0.18  # anomalia iniettata intorno a 40 K
    path = folder / "trasporto_campione_A.csv"
    pd.DataFrame({"T (K)": T, "rho [uohm*cm]": rho}).to_csv(path, index=False)
    return path


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        settings = Settings(database_url=f"sqlite:///{tmp / 'demo.db'}", storage_dir=str(tmp / "storage"))
        engine = make_engine(settings.database_url)
        init_db(engine)
        with make_session_factory(engine)() as session:
            project = Project(name="Film sottili, campione A")
            session.add(project)
            session.flush()

            title("1. Ingestione")
            data_path = make_dataset(tmp)
            summary = ingest_file(session, project.id, data_path, storage_dir=settings.storage_dir,
                                  classification="confidential")
            print(f"{summary['filename']}: {summary['created']}")
            g = export_graph(session, project.id)
            for n in g["nodes"]:
                if n["type"] == "variable":
                    print(f"  variabile {n['label']!r}: unità {n['props']['unit']}, dimensione {n['props']['dimensionality']}")

            title("2. Motore delle anomalie")
            df = pd.read_csv(data_path)
            result = scan_residuals(df["T (K)"], df["rho [uohm*cm]"], degree=2)
            print(f"Modello atteso: {result.baseline}; incertezza: {result.sigma_used}; finestre provate: {result.trials}")
            for c in result.candidates:
                print(f"  {c.level.upper()}: T tra {c.x_start:.1f} e {c.x_end:.1f} K, "
                      f"locale {c.local_sigma:.1f}σ, globale {c.global_sigma:.1f}σ")
            print("  Prima di salire di livello:", "; ".join(result.candidates[0].checks[:3]) if result.candidates else "-")

            title("3. Laboratorio delle ipotesi: controllo di falsificabilità")
            vague = HypothesisCard(statement="La temperatura potrebbe influenzare la resistività del campione.",
                                   prior=0.7)
            good = HypothesisCard(
                statement="L'eccesso di resistività tra 37 e 44 K è dovuto a una transizione strutturale del substrato.",
                mechanism="Cambio di fase del substrato che modifica lo strain nel film.",
                predictions=[Prediction(quantity="ampiezza dell'eccesso", unit="uohm*cm", expected_value=0.18,
                                        lower=0.12, upper=0.24, model_sigma=0.02)],
                falsification=Falsification(observable="eccesso su film cresciuto su substrato diverso",
                                            criterion="Eccesso sotto 0.05 µΩ·cm su substrato di controllo con 3σ",
                                            min_samples=60),
                minimal_test="Ripetere la misura su un film identico cresciuto su un substrato senza transizioni",
                rivals=["Artefatto di calibrazione del termometro", "Transizione elettronica intrinseca del film"],
                evidence=[Evidence(stance="supports", source="artifact:" + summary["artifact_id"]),
                          Evidence(stance="contradicts", source="doi:10.0000/esempio-contrario")],
                prior=0.35,
            )
            for name, card in (("Vaga", vague), ("Strutturata", good)):
                rep = lint(card)
                print(f"  {name}: punteggio {rep.score}, superata: {rep.passed}")
                for i in rep.issues[:4]:
                    print(f"    - [{i.severity}] {i.message}")

            title("4. Quale esperimento fare dopo")
            priors = {"substrato": 0.35, "calibrazione": 0.30, "intrinseca": 0.35}
            experiments = [
                Experiment(name="Substrato di controllo", cost=5, measurement_sigma=0.04, n_samples=20, predictions={
                    "substrato": HypothesisPrediction(mu=0.0, model_sigma=0.02),
                    "calibrazione": HypothesisPrediction(mu=0.18, model_sigma=0.02),
                    "intrinseca": HypothesisPrediction(mu=0.18, model_sigma=0.03)}),
                Experiment(name="Secondo termometro", cost=1, measurement_sigma=0.04, n_samples=20, predictions={
                    "substrato": HypothesisPrediction(mu=0.18, model_sigma=0.02),
                    "calibrazione": HypothesisPrediction(mu=0.0, model_sigma=0.02),
                    "intrinseca": HypothesisPrediction(mu=0.18, model_sigma=0.03)}),
                Experiment(name="Campo magnetico 1 T", cost=3, measurement_sigma=0.04, n_samples=20, predictions={
                    "substrato": HypothesisPrediction(mu=0.18, model_sigma=0.02),
                    "calibrazione": HypothesisPrediction(mu=0.18, model_sigma=0.02),
                    "intrinseca": HypothesisPrediction(mu=0.05, model_sigma=0.04)}),
            ]
            for r in rank_experiments(priors, experiments):
                print(f"  {r.name}: {r.eig_bits:.2f} bit su {r.max_bits:.2f}, costo {r.cost:g}, priorità {r.priority:.3f}")
            n = samples_for_discrimination(priors, experiments[2], target_fraction=0.5)
            print(f"  Misure in campo magnetico necessarie per dimezzare l'incertezza: {n}")

            title("5. Policy sui dati")
            gw = default_gateway(Settings(llm_providers="anthropic"))
            try:
                gw.route_for("controlled")
            except PolicyViolation as exc:
                print(f"  Dato 'controlled' bloccato: {exc}")

            session.commit()
            ok, _ = provenance.verify_chain(session, project.id)
            title("6. Provenienza")
            print(f"  Catena dei record integra: {ok}")


if __name__ == "__main__":
    main()
