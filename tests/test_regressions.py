from evalgauge.compiler import compile_contract
from evalgauge.differential import differential_score, score_legacy
from evalgauge.matcher import score_typed


def test_known_numeric_string_regression():
    spec = {"interval": ["60", "60"], "units": [""]}
    assert not score_legacy("60", "interval_matching", spec).full
    assert score_legacy("60", "interval_matching", spec, repair=True).full
    contract = compile_contract(
        row_id="p",
        split="real_world",
        evaluator="interval_matching",
        evaluator_kwargs=spec,
        image_type="protractor",
    )
    assert score_typed("60", contract).full_match


def test_known_clock_alternative_zip_truncation():
    spec = {"intervals": [["01:00:00", "01:00:00"], ["13:00:00", "13:00:00"]], "units": [""]}
    assert not score_legacy("13:00:00", "multi_interval_matching", spec).full
    contract = compile_contract(
        row_id="c",
        split="test",
        evaluator="multi_interval_matching",
        evaluator_kwargs=spec,
        image_type="clock",
    )
    assert score_typed("13:00:00", contract).full_match


def test_legacy_unit_substring_false_acceptance():
    spec = {"interval": [60, 60], "units": ["m"]}
    assert score_legacy("60 mm", "interval_matching", spec).full
    contract = compile_contract(
        row_id="r",
        split="test",
        evaluator="interval_matching",
        evaluator_kwargs=spec,
        image_type="ruler",
    )
    assert not score_typed("60 mm", contract).full_match


def test_schema_audit_records_legacy_exception_instead_of_aborting():
    result = differential_score(
        answer="9.5 mL",
        row_id="schema",
        split="test",
        evaluator="interval_matching",
        evaluator_kwargs={"interval": ["9.5", "9.5"], "units": ["mL"]},
        image_type="measuring_cylinder",
    )
    assert not result["official"]["full"]
    assert result["official"]["exception"].startswith("ValueError:")
    assert result["repaired"]["full"]
    assert result["type_safe"]["full_match"]
