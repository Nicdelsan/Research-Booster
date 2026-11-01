"""Controllo di falsificabilità: una scheda ipotesi deve poter essere smentita da un risultato preciso.

Regola di prodotto "falsificabilità prima della plausibilità": le schede con errori non vengono mostrate
al ricercatore come proposte, ma restituite al generatore con l'elenco dei problemi.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Literal

from rb.hypotheses.card import HypothesisCard
from rb.ingest.quantities import parse_unit

Severity = Literal["error", "warning"]

_VAGUE = [
    r"\bmay\b", r"\bmight\b", r"\bcould\b", r"\bpossibly\b", r"\bin some cases\b", r"\bplays? a role\b",
    r"\bis (?:related|linked) to\b", r"\baffects?\b", r"\binfluences?\b",
    r"\bpotrebbe\b", r"\bpotrebbero\b", r"\bforse\b", r"\bin alcuni casi\b", r"\bha un ruolo\b",
    r"\bè (?:correlat[oa]|legat[oa]) a\b", r"\binfluenz\w*", r"\bincide su\b",
]
_ESCAPE = [r"\bunless\b", r"\bexcept (?:when|if)\b", r"\ba meno che\b", r"\btranne (?:se|quando)\b",
           r"\bin alcuni casi\b", r"\bsalvo\b"]
_HAS_THRESHOLD = re.compile(r"\d|σ|sigma|[<>≤≥]|fuori|outside|exceeds?|supera|below|above|sotto|sopra")


@dataclass
class Issue:
    code: str
    severity: Severity
    message: str


@dataclass
class LintReport:
    score: int
    passed: bool
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _matches(patterns: list[str], text: str) -> list[str]:
    low = text.lower()
    return [re.search(p, low).group(0) for p in patterns if re.search(p, low)]


def lint(card: HypothesisCard) -> LintReport:
    issues: list[Issue] = []

    def add(code: str, sev: Severity, msg: str) -> None:
        issues.append(Issue(code, sev, msg))

    vague = _matches(_VAGUE, card.statement)
    if vague:
        add("VAGUE_LANGUAGE", "warning",
            f"Enunciato vago ({', '.join(sorted(set(vague)))}): riformulare con una relazione precisa tra grandezze.")

    numeric = [p for p in card.predictions if p.expected_value is not None or p.lower is not None or p.upper is not None]
    if not numeric:
        add("NO_QUANTITATIVE_PREDICTION", "error",
            "Nessuna previsione quantitativa: indicare grandezza, valore o intervallo atteso e unità.")
    for p in card.predictions:
        if p.unit and parse_unit(p.unit) is None:
            add("UNIT_INVALID", "error", f"Unità non riconosciuta per '{p.quantity}': '{p.unit}'.")
        if p.lower is not None and p.upper is not None:
            if p.lower > p.upper:
                add("INTERVAL_INVALID", "error", f"Intervallo invertito per '{p.quantity}': {p.lower} > {p.upper}.")
            elif p.expected_value not in (None, 0):
                rel = (p.upper - p.lower) / abs(p.expected_value)
                if rel > 1.0:
                    add("LOW_RISK_PREDICTION", "warning",
                        f"Intervallo di '{p.quantity}' ampio quanto il valore atteso ({rel:.0%}): "
                        "una previsione che rischia poco dice poco.")

    crit = card.falsification.criterion.strip()
    if not crit:
        add("NO_FALSIFICATION_CRITERION", "error", "Manca la condizione di falsificazione.")
    elif not _HAS_THRESHOLD.search(crit.lower()):
        add("CRITERION_NOT_OPERATIONAL", "error",
            "La condizione di falsificazione non contiene una soglia o un confronto misurabile.")
    escapes = _matches(_ESCAPE, crit)
    if escapes:
        add("ESCAPE_CLAUSE", "warning",
            f"Clausola di fuga nella condizione ({', '.join(sorted(set(escapes)))}): l'ipotesi diventa difficile da smentire.")
    if card.falsification.min_samples is None:
        add("NO_SAMPLE_PLAN", "warning", "Non è indicato quanti dati servono: usare il calcolo del numero di misure.")

    if not card.minimal_test.strip():
        add("NO_MINIMAL_TEST", "warning", "Manca il test minimo che distingue l'ipotesi dalle rivali.")
    if len(card.rivals) < 2:
        add("FEW_RIVALS", "warning", "Servono almeno due ipotesi rivali per evitare il bias di conferma.")

    if not card.evidence:
        add("NO_EVIDENCE", "warning", "Nessuna evidenza collegata.")
    for i, ev in enumerate(card.evidence, 1):
        if not ev.source.strip():
            add("EVIDENCE_WITHOUT_SOURCE", "error", f"Evidenza n. {i} senza fonte: evidenza o silenzio.")
    if card.evidence and all(ev.stance == "supports" for ev in card.evidence):
        add("ONE_SIDED_EVIDENCE", "warning", "Solo evidenze a favore: cercare attivamente quelle contrarie.")

    if card.prior < 0.02 or card.prior > 0.98:
        add("EXTREME_PRIOR", "warning", f"Probabilità iniziale estrema ({card.prior}): giustificarla o moderarla.")

    errors = sum(i.severity == "error" for i in issues)
    warnings = len(issues) - errors
    score = max(0, 100 - 25 * errors - 8 * warnings)
    return LintReport(score=score, passed=errors == 0, issues=issues)
