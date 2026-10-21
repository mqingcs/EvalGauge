"""EvalGauge: executable typed quantity contracts for scientific VQA."""

from .compiler import compile_contract
from .matcher import score_profile, score_typed
from .schema import AuditScore, QuantityContract

__all__ = [
    "AuditScore",
    "QuantityContract",
    "compile_contract",
    "score_profile",
    "score_typed",
]
__version__ = "0.1.0"
