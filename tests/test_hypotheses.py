import pytest

from rb.hypotheses.calibration import brier_score, reliability_bins
from rb.hypotheses.card import Evidence, Falsification, HypothesisCard, Prediction
from rb.hypotheses.falsifiability import lint
from rb.hypotheses.ranking import (
    Experiment,
    HypothesisPrediction,
    entropy_bits,
    expected_information_gain,
    rank_experiments,
    samples_for_discrimination,
)


def good_card(**overrides) -> HypothesisCard:
    data = dict(
        statement="La resistività sopra 40 K cresce linearmente con T per scattering elettrone-fonone.",
        mechanism="Regime di Bloch-Grüneisen sopra la temperatura di Debye ridotta.",
        predictions=[Prediction(quantity="dρ/dT", unit="uohm*cm/K", expected_value=0.05, lower=0.04, upper=0.06)],
        falsification=Falsification(observable="dρ/dT tra 50 e 150 K",
                                    criterion="Pendenza fuori da [0.04, 0.06] µΩ·cm/K con 3σ", min_samples=40),
        minimal_test="Misura a quattro punte tra 50 e 150 K a passi di 2 K",
        rivals=["Scattering elettrone-elettrone (andamento T^2)", "Contributo magnetico"],
        evidence=[Evidence(stance="supports", source="doi:10.1000/xyz123"),
                  Evidence(stance="contradicts", source="node:abc")],
        prior=0.4,
    )
    data.update(overrides)
    return HypothesisCard(**data)


def codes(report):
    return {i.code for i in report.issues}


def test_good_card_passes():
    report = lint(good_card())
    assert report.passed and report.score == 100, report.issues


def test_missing_prediction_and_criterion_fail():
    report = lint(good_card(predictions=[], falsification=Falsification()))
    assert not report.passed
    assert {"NO_QUANTITATIVE_PREDICTION", "NO_FALSIFICATION_CRITERION"} <= codes(report)


def test_vague_language_and_escape_clause_flagged():
    card = good_card(statement="La temperatura potrebbe influenzare la resistività in alcuni casi.",
                     falsification=Falsification(criterion="Pendenza sotto 0.04, a meno che il campione sia drogato",
                                                 min_samples=10))
    assert {"VAGUE_LANGUAGE", "ESCAPE_CLAUSE"} <= codes(lint(card))


def test_evidence_without_source_is_error():
    card = good_card(evidence=[Evidence(stance="supports", source="")])
    assert "EVIDENCE_WITHOUT_SOURCE" in codes(lint(card))


def test_invalid_unit_and_inverted_interval():
    card = good_card(predictions=[Prediction(quantity="x", unit="banane", lower=2, upper=1)])
    assert {"UNIT_INVALID", "INTERVAL_INVALID"} <= codes(lint(card))


def test_eig_bounds():
    priors = {"a": 0.5, "b": 0.5}
    assert entropy_bits(priors) == pytest.approx(1.0)
    # previsioni identiche: nessuna informazione
    assert expected_information_gain(priors, {"a": 0, "b": 0}, {"a": 1, "b": 1}) == pytest.approx(0, abs=1e-6)
    # previsioni lontanissime: si impara tutto (1 bit)
    assert expected_information_gain(priors, {"a": 0, "b": 100}, {"a": 1, "b": 1}) == pytest.approx(1, abs=1e-3)


def test_rank_prefers_informative_per_cost():
    priors = {"h1": 0.5, "h2": 0.5}
    cheap_weak = Experiment(name="rapido", cost=1, measurement_sigma=5.0,
                            predictions={"h1": HypothesisPrediction(mu=0), "h2": HypothesisPrediction(mu=1)})
    costly_strong = Experiment(name="costoso", cost=10, measurement_sigma=0.1,
                               predictions={"h1": HypothesisPrediction(mu=0), "h2": HypothesisPrediction(mu=1)})
    balanced = Experiment(name="bilanciato", cost=2, measurement_sigma=0.3,
                          predictions={"h1": HypothesisPrediction(mu=0), "h2": HypothesisPrediction(mu=1)})
    ranking = rank_experiments(priors, [cheap_weak, costly_strong, balanced])
    assert ranking[0].name == "bilanciato"
    assert ranking[0].eig_bits <= ranking[0].max_bits


def test_samples_needed_grow_with_noise():
    priors = {"h1": 0.5, "h2": 0.5}
    preds = {"h1": HypothesisPrediction(mu=0), "h2": HypothesisPrediction(mu=1)}
    quiet = samples_for_discrimination(priors, Experiment(name="q", cost=1, measurement_sigma=1, predictions=preds))
    noisy = samples_for_discrimination(priors, Experiment(name="n", cost=1, measurement_sigma=3, predictions=preds))
    assert quiet is not None and noisy is not None and noisy > quiet


def test_samples_none_when_theory_uncertainty_dominates():
    priors = {"h1": 0.5, "h2": 0.5}
    preds = {"h1": HypothesisPrediction(mu=0, model_sigma=10), "h2": HypothesisPrediction(mu=1, model_sigma=10)}
    exp = Experiment(name="x", cost=1, measurement_sigma=1, predictions=preds)
    assert samples_for_discrimination(priors, exp) is None


def test_missing_prediction_for_hypothesis_raises():
    with pytest.raises(ValueError):
        rank_experiments({"h1": 0.5, "h2": 0.5},
                         [Experiment(name="x", cost=1, measurement_sigma=1, predictions={"h1": HypothesisPrediction(mu=0)})])


def test_brier_and_bins():
    assert brier_score([1.0, 0.0], [1, 0]) == 0
    assert brier_score([0.5, 0.5], [1, 0]) == pytest.approx(0.25)
    bins = reliability_bins([0.1, 0.15, 0.9, 0.95], [0, 0, 1, 1], n_bins=5)
    assert [b["count"] for b in bins] == [2, 2]
