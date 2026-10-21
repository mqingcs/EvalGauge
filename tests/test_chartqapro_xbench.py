from evalgauge.xbench.chartqapro import (
    compile_chartqapro_contract,
    generate_chartqapro_cases,
    official_chartqapro_score,
    reference_chartqapro_score,
)


def row(answer, question_type="Factoid", year=None):
    return {
        "Answer": [answer],
        "Question Type": question_type,
        "Year": year or ["NO"],
    }


def test_numeric_representation_and_boundary():
    contract = compile_chartqapro_contract(row("60"), 0)
    assert official_chartqapro_score(contract, "60.0") == 1.0
    assert reference_chartqapro_score(contract, "60.0")
    assert official_chartqapro_score(contract, "63.06") == 0.0
    assert not reference_chartqapro_score(contract, "63.06")


def test_numeric_parse_failure_falls_back_to_anls():
    contract = compile_chartqapro_contract(row("100"), 0)
    assert official_chartqapro_score(contract, "100x") > 0
    assert not reference_chartqapro_score(contract, "100x")


def test_exact_question_type_exposes_unforwarded_flag():
    contract = compile_chartqapro_contract(row("False", "Fact Checking"), 0)
    assert contract.semantic_type == "exact"
    assert official_chartqapro_score(contract, "Falsex") > 0
    assert not reference_chartqapro_score(contract, "Falsex")


def test_year_flag_remains_exact():
    contract = compile_chartqapro_contract(row("2010", year=["YES"]), 0)
    assert official_chartqapro_score(contract, "2010") == 1.0
    assert official_chartqapro_score(contract, "2010x") == 0.0


def test_ordered_list_contract():
    contract = compile_chartqapro_contract(row("['10', '20']"), 0)
    assert reference_chartqapro_score(contract, "['10', '20']")
    assert not reference_chartqapro_score(contract, "['20', '10']")


def test_unquoted_source_list_is_a_valid_contract_witness():
    contract = compile_chartqapro_contract(row("[Andy, Hunter]"), 0)
    assert contract.target_items == ("Andy", "Hunter")
    assert reference_chartqapro_score(contract, "[Andy, Hunter]")
    assert official_chartqapro_score(contract, "[Andy, Hunter]") == 0.0


def test_nonfinite_source_token_is_not_coerced_to_numeric():
    contract = compile_chartqapro_contract(row("nan"), 0)
    assert contract.semantic_type == "text_anls"
    assert reference_chartqapro_score(contract, "nan")
    assert official_chartqapro_score(contract, "nan") == 0.0


def test_generated_suite_matches_reference_contract():
    examples = [
        compile_chartqapro_contract(row("60"), 0),
        compile_chartqapro_contract(row("False", "Fact Checking"), 1),
        compile_chartqapro_contract(row("['10', '20']"), 2),
    ]
    for contract in examples:
        for case in generate_chartqapro_cases(contract):
            assert reference_chartqapro_score(contract, case.answer) == case.expected_label
