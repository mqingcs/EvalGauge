from evalgauge.matcher import score_profile


def test_physics_extends_literal_source_units(numeric_contract):
    contract = numeric_contract(units=("mL",), image_type="measuring_cylinder")
    assert not score_profile("0.06 L", contract, profile="core_final").full_match
    assert score_profile("0.06 L", contract, profile="physics_final").full_match
    assert score_profile("0.06 L", contract, profile="strict_final").full_match


def test_strict_adds_multi_value_safety(numeric_contract):
    contract = numeric_contract(units=("mL",), image_type="measuring_cylinder")
    answer = "60 mL or 600 mL"
    assert score_profile(answer, contract, profile="physics_final").full_match
    strict = score_profile(answer, contract, profile="strict_final")
    assert not strict.full_match
    assert strict.invalid_reason == "multiple_inconsistent_quantities"


def test_core_uses_token_safe_declared_unit(numeric_contract):
    contract = numeric_contract(units=("mL",), image_type="measuring_cylinder")
    assert score_profile("60 mL", contract, profile="core_final").full_match
    assert not score_profile("60 mL/s", contract, profile="core_final").full_match
