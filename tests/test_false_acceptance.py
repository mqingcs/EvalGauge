from evalgauge.matcher import score_typed


def test_wrong_dimension_rejected(numeric_contract):
    contract = numeric_contract()
    assert not score_typed("60 mm", contract).full_match


def test_correct_plus_wrong_value_rejected(numeric_contract):
    contract = numeric_contract()
    assert not score_typed("60 °C or 600 °C", contract).full_match


def test_nonfinite_and_abstention_rejected(numeric_contract):
    contract = numeric_contract()
    for answer in ["NaN °C", "Inf °C", "N/A", "cannot determine"]:
        assert not score_typed(answer, contract).full_match
