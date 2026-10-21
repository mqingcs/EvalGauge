from evalgauge.extraction import extract_official_final
from evalgauge.matcher import score_typed


def test_official_final_matches_released_answer_indicator_behavior():
    raw = "The scale is 0--100 and each division is 5. Final Answer: 60 psi"
    assert extract_official_final(raw) == "60 psi"


def test_typed_final_ignores_intermediate_reasoning_numbers(numeric_contract):
    contract = numeric_contract(interval=(60, 60), units=("psi",))
    raw = "The scale is 0--100 and each division is 5. Final Answer: 60 psi"
    score = score_typed(raw, contract, extraction_policy="official_final")
    assert score.full_match
    assert score.extracted_answer == "60 psi"


def test_typed_global_is_a_stricter_sensitivity_policy(numeric_contract):
    contract = numeric_contract(interval=(60, 60), units=("psi",))
    raw = "The scale is 0--100 and each division is 5. Final Answer: 60 psi"
    score = score_typed(raw, contract, extraction_policy="global")
    assert not score.full_match
    assert score.invalid_reason == "multiple_inconsistent_quantities"


def test_final_segment_still_rejects_contradictory_values(numeric_contract):
    contract = numeric_contract(interval=(60, 60), units=("psi",))
    raw = "The scale has many labels. Final Answer: 60 psi or 600 psi"
    assert not score_typed(raw, contract, extraction_policy="official_final").full_match


def test_official_indicator_precedes_boxed_fallback():
    raw = r"scratch \boxed{55 psi}; Answer: 60 psi"
    assert extract_official_final(raw) == "60 psi"


def test_latex_text_unit_is_presentation_not_semantics(numeric_contract):
    contract = numeric_contract(interval=(560, 560), units=("A",))
    raw = r"The final answer is $\boxed{560\text{ A}}$."
    assert score_typed(raw, contract, extraction_policy="official_final").full_match


def test_latex_unwrap_does_not_hide_compound_wrong_unit(numeric_contract):
    contract = numeric_contract(interval=(7, 7), units=("kWh",))
    raw = r"The final answer is $\boxed{\text{7.00 Pence/kWh}}$."
    score = score_typed(raw, contract, extraction_policy="official_final")
    assert not score.full_match
    assert score.invalid_reason == "missing_unit"
