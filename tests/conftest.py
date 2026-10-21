from __future__ import annotations

import pytest

from evalgauge.compiler import compile_contract


@pytest.fixture
def numeric_contract():
    def factory(interval=(60, 60), units=("°C", "Celsius"), image_type="thermometer"):
        return compile_contract(
            row_id="test::numeric",
            split="test",
            evaluator="interval_matching",
            evaluator_kwargs={"interval": list(interval), "units": list(units)},
            image_type=image_type,
        )

    return factory
