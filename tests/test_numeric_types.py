from decimal import Decimal

from evalgauge.compiler import compile_contract
from evalgauge.matcher import score_typed


def test_numeric_string_is_numeric_not_clock():
    contract = compile_contract(
        row_id="real_world::protractor_3",
        split="real_world",
        evaluator="interval_matching",
        evaluator_kwargs={"interval": ["60", "60"], "units": [""]},
        image_type="protractor",
    )
    assert contract.semantic_types == ("numeric_quantity",)
    assert score_typed("60", contract).full_match


def test_decimal_renderings_are_equivalent(numeric_contract):
    contract = numeric_contract()
    for answer in ["60 °C", "60.0 °C", "60.000 °C", "+60 °C", "6E1 °C"]:
        assert score_typed(answer, contract).full_match, answer


def test_decimal_internal_values_are_exact():
    assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")


def test_structured_quantity_answer(numeric_contract):
    contract = numeric_contract(interval=(20, 20))
    assert score_typed('{"value": 20, "unit": "°C"}', contract).full_match


def test_separate_unit_field_applies_to_reading(numeric_contract):
    contract = numeric_contract(interval=(35, 35), units=("mL",))
    answer = "**Reading:** 35\n**Unit:** ml (or mL)"
    assert score_typed(answer, contract).full_match


def test_typographic_mixed_fraction_is_one_quantity():
    contract = compile_contract(
        row_id="ruler",
        split="test",
        evaluator="interval_matching",
        evaluator_kwargs={"interval": [3.375, 3.375], "units": ["in"]},
        image_type="ruler",
    )
    trace = score_typed("**Reading:** 3 ³/₈ inches / 3.375 in", contract)
    assert trace.full_match
    assert [quantity["value"] for quantity in trace.parsed_quantities] == ["3.375", "3.375"]
