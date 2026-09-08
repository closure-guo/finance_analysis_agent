"""__init__ for evals.hallucination（幻觉率度量 v1）。"""

from evals.hallucination.measure import (
    Claim,
    HallucinationResult,
    Verdict,
    extract_claims,
    hallucination_rate,
    run_offline,
    verify_claims,
)

__all__ = [
    "Claim",
    "HallucinationResult",
    "Verdict",
    "extract_claims",
    "hallucination_rate",
    "run_offline",
    "verify_claims",
]
