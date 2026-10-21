from evalgauge.compiler import compile_contract
from evalgauge.matcher import score_typed


def test_clock_and_number_are_separate_types():
    clock = compile_contract(
        row_id="clock",
        split="test",
        evaluator="interval_matching",
        evaluator_kwargs={"interval": ["01:00", "01:00"], "units": [""]},
        image_type="clock",
    )
    assert score_typed("1:00", clock).full_match
    assert not score_typed("60", clock).full_match


def test_flat_clock_units_are_broadcast_to_all_alternatives():
    clock = compile_contract(
        row_id="clock",
        split="test",
        evaluator="multi_interval_matching",
        evaluator_kwargs={
            "intervals": [["01:00:00", "01:00:00"], ["13:00:00", "13:00:00"]],
            "units": [""],
        },
        image_type="clock",
    )
    assert len(clock.branches) == 2
    assert score_typed("13:00:00", clock).full_match
