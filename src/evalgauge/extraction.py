from __future__ import annotations

import re

OFFICIAL_ANSWER_INDICATORS = ("Answer:", "Answer", "答案：", "答案:", "答案")


def extract_official_final(text: str) -> str:
    """Mirror MeasureBench's released final-answer extraction exactly."""
    answer = str(text)
    for indicator in OFFICIAL_ANSWER_INDICATORS:
        if indicator in answer:
            return answer.split(indicator)[-1].strip()
    boxed = re.search(r"\\boxed\{([^}]+)\}", answer)
    return boxed.group(1).strip() if boxed else answer


def extract_typed_final(text: str) -> str:
    """A broader final-segment policy retained only for sensitivity analysis."""
    answer = str(text)
    boxed = list(re.finditer(r"\\boxed\{([^{}]+)\}", answer))
    indicators = ("Final Answer:", "Final answer:", "Answer:", "Reading:", "答案：", "答案:")
    candidates: list[tuple[int, str]] = []
    folded = answer.casefold()
    for indicator in indicators:
        position = folded.rfind(indicator.casefold())
        if position >= 0:
            candidates.append((position, answer[position + len(indicator) :].strip()))
    if boxed:
        candidates.append((boxed[-1].start(), boxed[-1].group(1).strip()))
    return max(candidates, key=lambda item: item[0])[1] if candidates else answer


def extract_segment(text: str, policy: str) -> str:
    if policy == "official_final":
        return extract_official_final(text)
    if policy == "typed_final":
        return extract_typed_final(text)
    if policy == "global":
        return str(text)
    raise ValueError(f"unsupported extraction policy: {policy}")
