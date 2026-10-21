from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .compiler import compile_contract
from .extraction import extract_official_final
from .matcher import score_typed

LEGACY_NUMBER_RE = re.compile(
    r"(?P<fraction>[+\-−]?\d+\s*/\s*[+\-−]?\d+)"
    r"|(?P<decimal>[+\-−]?(?:\d*\.\d+|\d+\.\d*))"
    r"|(?P<integer>[+\-−]?\d+)"
)
LEGACY_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b")


@dataclass(frozen=True)
class LegacyScore:
    value: bool
    unit: bool | None
    full: bool
    number_error_rate: float | None = None
    exception: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "unit": self.unit,
            "full": self.full,
            "number_error_rate": self.number_error_rate,
            "exception": self.exception,
        }


def _extract_answer(text: str) -> str:
    return extract_official_final(text)


def _normalize(text: str) -> str:
    for old, new in {"′": "'", " ": " ", "‐": "-", "−": "-", "–": "-", "⋅": "·"}.items():
        text = text.replace(old, new)
    return text


def _numbers(text: str) -> list[float]:
    result: list[float] = []
    for match in LEGACY_NUMBER_RE.finditer(text):
        token = match.group(0).replace("−", "-").strip()
        try:
            if match.lastgroup == "fraction":
                left, right = re.split(r"\s*/\s*", token, maxsplit=1)
                if int(right) != 0:
                    result.append(int(left) / int(right))
            else:
                result.append(float(token))
        except ValueError:
            continue
    return result


def _time_to_seconds(parts: list[str] | tuple[str, ...]) -> int:
    return sum(scale * int(part) for scale, part in zip([3600, 60, 1], parts) if part != "")


def _interval_score(answer: str, interval: list[Any], units: Any, repair: bool) -> LegacyScore:
    if (
        repair
        and interval
        and all(isinstance(value, str) and ":" not in value for value in interval)
    ):
        try:
            interval = [float(value) for value in interval]
        except ValueError:
            pass
    normalized = unicodedata.normalize("NFKC", answer.lower()).replace("µ", "μ")
    unit_correct: bool | None = None if len(units) == 0 else False
    for unit in units:
        needle = unicodedata.normalize("NFKC", str(unit).lower()).replace("µ", "μ")
        if needle in normalized:
            unit_correct = True
    if isinstance(interval[0], str):
        left = _time_to_seconds(interval[0].split(":"))
        right = _time_to_seconds(interval[1].split(":"))
        matches = LEGACY_TIME_RE.findall(answer)
        if not matches:
            return LegacyScore(False, unit_correct, False)
        predicted = float(_time_to_seconds(matches[0]))
    else:
        left, right = float(interval[0]), float(interval[1])
        values = _numbers(answer)
        if not values or math.isinf(values[-1]) or math.isnan(values[-1]):
            return LegacyScore(False, unit_correct, False)
        predicted = values[-1]
    if predicted < left or predicted > right:
        epsilon = 1e-6
        error = min(
            abs((predicted - left) / (left + epsilon)), abs((predicted - right) / (right + epsilon))
        )
        return LegacyScore(False, unit_correct, False, error)
    full = unit_correct is None or bool(unit_correct)
    return LegacyScore(True, unit_correct, full, 0.0)


def _better(candidate: LegacyScore, incumbent: LegacyScore | None) -> bool:
    if incumbent is None:
        return True
    candidate_unit = True if candidate.unit is None else candidate.unit
    incumbent_unit = True if incumbent.unit is None else incumbent.unit
    if int(candidate.value) + int(candidate_unit) > int(incumbent.value) + int(incumbent_unit):
        return True
    return (
        candidate.number_error_rate is not None
        and incumbent.number_error_rate is not None
        and candidate.number_error_rate < incumbent.number_error_rate
    )


def score_legacy(
    answer: str, evaluator: str, spec: dict[str, Any], *, repair: bool = False
) -> LegacyScore:
    answer = _normalize(_extract_answer(str(answer)))
    if evaluator == "interval_matching":
        return _interval_score(answer, spec["interval"], spec.get("units", []), repair)
    if evaluator != "multi_interval_matching":
        raise ValueError(f"unsupported evaluator: {evaluator}")
    intervals = spec["intervals"]
    units = spec.get("units", [])
    if len(units) == 0:
        units = [[]] * len(intervals)
    best: LegacyScore | None = None
    for interval, accepted_units in zip(intervals, units):
        candidate = _interval_score(answer, interval, accepted_units, repair)
        if candidate.full:
            return candidate
        if _better(candidate, best):
            best = candidate
    return best or LegacyScore(False, False, False)


def differential_score(
    *,
    answer: str,
    row_id: str,
    split: str,
    evaluator: str,
    evaluator_kwargs: dict[str, Any],
    image_type: str = "",
    design: str = "",
) -> dict[str, Any]:
    try:
        official = score_legacy(answer, evaluator, evaluator_kwargs, repair=False)
    except (ArithmeticError, IndexError, TypeError, ValueError) as exc:
        official = LegacyScore(False, False, False, exception=f"{type(exc).__name__}: {exc}")
    try:
        repaired = score_legacy(answer, evaluator, evaluator_kwargs, repair=True)
    except (ArithmeticError, IndexError, TypeError, ValueError) as exc:
        repaired = LegacyScore(False, False, False, exception=f"{type(exc).__name__}: {exc}")
    contract = compile_contract(
        row_id=row_id,
        split=split,
        evaluator=evaluator,
        evaluator_kwargs=evaluator_kwargs,
        image_type=image_type,
        design=design,
    )
    typed = score_typed(answer, contract, extraction_policy="official_final")
    transition = f"{int(official.full)}{int(repaired.full)}{int(typed.full_match)}"
    labels = {
        "011": "official_false_rejection",
        "100": "official_false_acceptance",
        "110": "shared_false_acceptance",
        "001": "both_legacy_false_rejection",
        "101": "repaired_regression",
        "010": "repaired_over_acceptance",
        "000": "stable_rejection",
        "111": "stable_acceptance",
    }
    return {
        "official": official.to_dict(),
        "repaired": repaired.to_dict(),
        "type_safe": typed.to_dict(),
        "score_transition": transition,
        "transition_class": labels[transition],
    }
