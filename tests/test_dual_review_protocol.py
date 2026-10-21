from scripts.review_public_transitions_dual import FORBIDDEN_PUBLIC_KEYS, public_case


def test_reviewer_payload_contains_only_declared_material() -> None:
    case = {
        "case_id": "transition-01",
        "row_id": "real_world::hidden",
        "model": "hidden-model",
        "question": "What is the reading?",
        "raw_annotation": {"intervals": [[1, 2]], "units": ["V"]},
        "benchmark_instruction": "Return the final answer and unit.",
        "model_response": "Final Answer: 1.5 V",
        "image_url": "/image?case_id=transition-01",
        "official": False,
        "strict": True,
        "automatic_profile": "hidden",
    }
    visible = public_case(case)
    assert set(visible) == {
        "case_id",
        "question",
        "raw_annotation",
        "benchmark_instruction",
        "model_response",
        "image_url",
    }
    assert not FORBIDDEN_PUBLIC_KEYS.intersection(visible)
