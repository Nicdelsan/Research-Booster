import pytest

from rb.ingest.quantities import extract_quantities, parse_unit, unit_from_label


def test_value_uncertainty_symbol_unit():
    (q,) = extract_quantities("Troviamo T_c = 39.2 ± 0.3 K nei film.")
    assert q.symbol == "T_c"
    assert q.value == pytest.approx(39.2)
    assert q.uncertainty == pytest.approx(0.3)
    assert q.dimensionality == "[temperature]"


def test_scientific_notation_and_negative_exponent_units():
    (q,) = extract_quantities("densità di portatori 2.1e21 cm-3")
    assert q.value_si == pytest.approx(2.1e27)
    assert q.dimensionality == "1 / [length] ** 3"


def test_compound_units_with_symbols():
    (q,) = extract_quantities("resistività 12.5 µΩ·cm")
    assert q.value_si == pytest.approx(12.5e-8)  # 12.5 µΩ·cm = 1.25e-7 Ω·m


def test_celsius_converted_to_kelvin():
    (q,) = extract_quantities("a 25 °C")
    assert q.value_si == pytest.approx(298.15)


@pytest.mark.parametrize("text", ["tra 2 and 3", "nel 2020 we saw", "abbiamo 5 points", "figura 3 a destra", "dal 2 al 4 in tabella"])
def test_common_words_are_not_units(text):
    assert extract_quantities(text) == []


def test_unit_from_column_label():
    assert unit_from_label("T (K)") == ("T", "K")
    assert unit_from_label("R [ohm]") == ("R", "ohm")
    assert unit_from_label("indice") == ("indice", None)


def test_parse_unit_rejects_plain_numbers_label():
    assert parse_unit("campioni") is None
