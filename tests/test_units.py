from decimal import Decimal

from evalgauge.compiler import compile_contract
from evalgauge.conversions import convert
from evalgauge.matcher import score_typed
from evalgauge.metamorphic import canonical_answer, source_witness_answer
from evalgauge.parser import parse_quantities


def test_volume_aliases_and_typography(numeric_contract):
    contract = numeric_contract(
        interval=(1, 1), units=("cm^3", "cm³"), image_type="measuring_cylinder"
    )
    for answer in ["1 cm^3", "1 cm³", "1 mL", "0.01 dL"]:
        assert score_typed(answer, contract).full_match, answer


def test_token_boundaries_prevent_substring_units(numeric_contract):
    contract = numeric_contract(interval=(60, 60), units=("m",), image_type="ruler")
    assert not score_typed("60 mm", contract).full_match


def test_ambiguous_ounce_resolves_by_contract_dimension(numeric_contract):
    volume = numeric_contract(
        interval=(1, 1), units=("oz", "Ounce"), image_type="measuring_cylinder"
    )
    mass = numeric_contract(interval=(1, 1), units=("oz", "ounce"), image_type="weighing_scale")
    assert score_typed("1 oz", volume).full_match
    assert score_typed("1 oz", mass).full_match


def test_case_equivalent_unit_alias_tie_is_deterministic():
    for aliases in [("mL", "ml"), ("ml", "mL")]:
        parsed, warnings = parse_quantities(
            "Answer: 12 ml",
            expected_dimension="volume",
            contract_aliases=aliases,
        )
        assert not warnings
        assert parsed[0].raw_unit == "mL"


def test_multiplicative_conversions():
    assert convert("1", "dL", "mL") == Decimal(100)
    assert convert("1", "inch", "mm") == Decimal("25.4")
    assert convert("1", "cm^3", "mL") == Decimal(1)


def test_source_witness_and_canonical_unit_are_distinct_valid_renderings():
    contract = compile_contract(
        row_id="volume",
        split="test",
        evaluator="interval_matching",
        evaluator_kwargs={"interval": [1, 1], "units": ["cc"]},
        image_type="measuring_cylinder",
    )
    branch = contract.branches[0]
    assert source_witness_answer(branch) == "1 cc"
    assert canonical_answer(branch) == "1 cm^3"
    assert score_typed(source_witness_answer(branch), contract).full_match
    assert score_typed(canonical_answer(branch), contract).full_match
