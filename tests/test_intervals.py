from evalgauge.matcher import score_typed


def test_closed_boundaries(numeric_contract):
    contract = numeric_contract(interval=(10, 20), units=("mL",), image_type="measuring_cylinder")
    assert score_typed("10 mL", contract).full_match
    assert score_typed("20 mL", contract).full_match
    assert not score_typed("9.999999 mL", contract).full_match
    assert not score_typed("20.000001 mL", contract).full_match


def test_reversed_annotation_bounds_are_traced(numeric_contract):
    contract = numeric_contract(interval=(20, 10), units=("mL",), image_type="measuring_cylinder")
    assert "reversed_interval_bounds" in contract.branches[0].warnings
    assert score_typed("15 mL", contract).full_match
