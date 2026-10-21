from decimal import Decimal

from evalgauge.conversions import convert


def test_affine_temperature_conversion():
    assert convert("25", "°C", "°F").quantize(Decimal("0.000001")) == Decimal("77.000000")
    assert convert("77", "°F", "°C").quantize(Decimal("0.000001")) == Decimal("25.000000")


def test_dimension_mismatch_rejected():
    try:
        convert("1", "mL", "mm")
    except ValueError as error:
        assert "incompatible dimensions" in str(error)
    else:
        raise AssertionError("dimension mismatch was accepted")
