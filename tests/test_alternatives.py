from evalgauge.compiler import compile_contract
from evalgauge.matcher import score_typed
from evalgauge.metamorphic import schema_positive_cases


def test_multi_unit_alternatives():
    contract = compile_contract(
        row_id="temperature",
        split="test",
        evaluator="multi_interval_matching",
        evaluator_kwargs={"intervals": [[25, 25], [77, 77]], "units": [["°C"], ["°F"]]},
        image_type="thermometer",
    )
    assert score_typed("25 °C", contract).full_match
    assert score_typed("77 °F", contract).full_match


def test_repeated_equivalent_answers_are_not_injections():
    contract = compile_contract(
        row_id="temperature",
        split="test",
        evaluator="interval_matching",
        evaluator_kwargs={"interval": [24, 24], "units": ["°C"]},
        image_type="thermometer",
    )
    assert score_typed("24 °C (or 24 degrees Celsius)", contract).full_match


def test_schema_relations_are_executable_not_answer_placeholders():
    contract = compile_contract(
        row_id="multi",
        split="test",
        evaluator="multi_interval_matching",
        evaluator_kwargs={
            "intervals": [[10, 10], [20, 20]],
            "units": [["mL"], ["mL"]],
        },
        image_type="measuring_cylinder",
    )
    cases = schema_positive_cases(contract)
    assert {case.relation_id for case in cases} == {"MR-10", "MR-12"}
    reversed_cases = [case for case in cases if case.relation_id == "MR-12"]
    assert reversed_cases[0].evaluator_kwargs["intervals"] == [[20, 20], [10, 10]]
    for case in cases:
        variant = compile_contract(
            row_id="variant",
            split="test",
            evaluator="multi_interval_matching",
            evaluator_kwargs=case.evaluator_kwargs,
            image_type="measuring_cylinder",
        )
        assert score_typed(case.answer, variant).full_match
