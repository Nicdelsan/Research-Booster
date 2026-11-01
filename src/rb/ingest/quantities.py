"""Estrazione di grandezze fisiche (valore, incertezza, unità) da testo libero, validate con pint."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache

import pint


@lru_cache(maxsize=1)
def ureg() -> pint.UnitRegistry:
    reg = pint.UnitRegistry()
    reg.formatter.default_format = "~"
    return reg


# Parole comuni (italiano e inglese) che pint interpreterebbe come unità: "in" (pollice), "a" (anno),
# "at" (atmosfera tecnica), "e" (carica elementare), "points" (punto tipografico)...
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "if", "in", "is", "it", "of", "on", "or",
    "than", "that", "the", "this", "to", "we", "with", "times", "point", "points", "pt", "line", "lines",
    "e", "ed", "il", "lo", "la", "i", "gli", "le", "di", "da", "del", "della", "con", "su", "per", "tra", "fra",
    "un", "una", "uno", "al", "che", "non", "o", "sono", "mi", "ti", "si", "ci", "vi",
}
_ALLOWED_DIMENSIONLESS = {"%", "percent", "ppm", "ppb", "rad", "sr"}

_SUPERSCRIPTS = str.maketrans({"⁻": "-", "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
                               "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9"})

_NUM = r"[-+−]?(?:\d+(?:\.\d+)?|\.\d+)"
_PATTERN = re.compile(
    r"(?:(?P<symbol>\b[A-Za-zα-ωΑ-Ω][A-Za-z0-9_{}α-ω]{0,10})\s*(?:=|≈|~|≃)\s*)?"
    rf"(?P<value>{_NUM})"
    r"(?:\s*(?:[eE](?P<exp1>[-+−]?\d+)|\s*[×x]\s*10\^?\{?(?P<exp2>[-+−]?\d+)\}?))?"
    rf"(?:\s*(?:±|\+/-|\+-)\s*(?P<unc>{_NUM}))?"
    r"\s?(?P<unit>[A-Za-zµμΩΩÅ°%][A-Za-zµμΩΩÅ°%·*/^\-⁻⁰¹²³⁴⁵⁶⁷⁸⁹0-9]{0,15})"
)


@dataclass
class Quantity:
    value: float
    unit: str
    unit_normalized: str
    dimensionality: str
    value_si: float
    unit_si: str
    uncertainty: float | None = None
    symbol: str | None = None
    start: int = 0
    end: int = 0
    context: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _to_float(s: str) -> float:
    return float(s.replace("−", "-"))


def normalize_unit(raw: str) -> str:
    u = raw.translate(_SUPERSCRIPTS)
    for a, b in (("°C", "degC"), ("°F", "degF"), ("Ω", "ohm"), ("Ω", "ohm"), ("µ", "u"), ("μ", "u"),
                 ("·", "*"), ("Å", "angstrom"), ("°", "degree")):
        u = u.replace(a, b)
    u = re.sub(r"([A-Za-z])(-?\d+)\b", r"\1^\2", u)  # cm-3 -> cm^-3, m2 -> m^2
    return u.rstrip("-*/^")


def parse_unit(raw: str) -> pint.Unit | None:
    """Restituisce l'unità pint, oppure None se la stringa non è un'unità plausibile."""
    if not raw or raw.lower() in _STOPWORDS:
        return None
    candidates = [raw, raw.split("-")[0]]
    m = re.match(r"[A-Za-zµμΩΩÅ°%]+", raw)
    if m:
        candidates.append(m.group())
    for cand in dict.fromkeys(candidates):
        if not cand or cand.lower() in _STOPWORDS:
            continue
        try:
            unit = ureg().parse_units(normalize_unit(cand))
        except Exception:  # pint solleva diversi tipi di errore
            continue
        if unit.dimensionless and cand not in _ALLOWED_DIMENSIONLESS:
            continue
        return unit
    return None


def extract_quantities(text: str, context_chars: int = 60) -> list[Quantity]:
    out: list[Quantity] = []
    for m in _PATTERN.finditer(text):
        unit = parse_unit(m.group("unit"))
        if unit is None:
            continue
        value = _to_float(m.group("value"))
        exp = m.group("exp1") or m.group("exp2")
        if exp:
            value *= 10 ** int(exp.replace("−", "-"))
        unc = _to_float(m.group("unc")) if m.group("unc") else None
        if unc is not None and exp:
            unc *= 10 ** int(exp.replace("−", "-"))
        q = ureg().Quantity(value, unit)
        try:
            base = q.to_base_units()
        except Exception:
            continue
        start, end = m.start(), m.end()
        out.append(Quantity(
            value=value,
            uncertainty=unc,
            unit=m.group("unit"),
            unit_normalized=f"{unit:~}" or str(unit),
            dimensionality=str(q.dimensionality),
            value_si=float(base.magnitude),
            unit_si=f"{base.units:~}",
            symbol=m.group("symbol"),
            start=start,
            end=end,
            context=text[max(0, start - context_chars): end + context_chars].replace("\n", " ").strip(),
        ))
    return out


def unit_from_label(label: str) -> tuple[str, str | None]:
    """'T (K)' -> ('T', 'K'); 'R [ohm]' -> ('R', 'ohm'); 'x' -> ('x', None)."""
    m = re.match(r"^(?P<name>.*?)\s*[\(\[](?P<unit>[^\)\]]+)[\)\]]\s*$", label.strip())
    if not m:
        return label.strip(), None
    unit = m.group("unit").strip()
    return m.group("name").strip(), unit if parse_unit(unit) is not None else None


def dimensionality_of(unit_str: str | None) -> str | None:
    if not unit_str:
        return None
    unit = parse_unit(unit_str)
    return str(ureg().Quantity(1, unit).dimensionality) if unit is not None else None
