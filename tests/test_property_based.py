from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from evalgauge.compiler import compile_contract
from evalgauge.matcher import score_typed


@settings(max_examples=250, deadline=None)
@given(
    st.decimals(
        min_value=Decimal(-100000),
        max_value=Decimal(100000),
        allow_nan=False,
        allow_infinity=False,
        places=6,
    )
)
def test_trailing_zeros_preserve_exact_numeric_semantics(value):
    contract = compile_contract(
        row_id="fuzz",
        split="test",
        evaluator="interval_matching",
        evaluator_kwargs={"interval": [str(value), str(value)], "units": ["mL"]},
        image_type="measuring_cylinder",
    )
    assert score_typed(f"{value}0 mL", contract).full_match


@settings(max_examples=150, deadline=None)
@given(
    st.integers(min_value=0, max_value=23),
    st.integers(min_value=0, max_value=59),
    st.integers(min_value=0, max_value=59),
)
def test_clock_format_roundtrip(hour, minute, second):
    value = f"{hour:02d}:{minute:02d}:{second:02d}"
    contract = compile_contract(
        row_id="clock-fuzz",
        split="test",
        evaluator="interval_matching",
        evaluator_kwargs={"interval": [value, value], "units": [""]},
        image_type="clock",
    )
    assert score_typed(value, contract).full_match


@settings(max_examples=150, deadline=None)
@given(
    st.decimals(
        min_value=Decimal("0.001"),
        max_value=Decimal(10000),
        allow_nan=False,
        allow_infinity=False,
        places=3,
    )
)
def test_ml_l_conversion_roundtrip(value):
    contract = compile_contract(
        row_id="volume-fuzz",
        split="test",
        evaluator="interval_matching",
        evaluator_kwargs={"interval": [str(value), str(value)], "units": ["mL"]},
        image_type="measuring_cylinder",
    )
    liters = value / Decimal(1000)
    assert score_typed(f"{liters} L", contract).full_match
