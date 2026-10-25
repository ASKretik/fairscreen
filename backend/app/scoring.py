"""Deterministic score (SPEC §7.4). The LLM judges requirements; the number is computed here."""

from collections.abc import Sequence

import numpy as np

from app.models import CandidateEvaluation, RequirementVerdict, ScoreBreakdown, Weights

# Bounds for rescaling raw cosine similarity to 0–1. SPEC §7.4 defaults; recalibrate
# in Phase 5 from the 10th/90th percentiles of the eval pool's raw cosines.
SEMANTIC_LO = 0.55
SEMANTIC_HI = 0.85


def coverage(verdicts: Sequence[RequirementVerdict]) -> float:
    """(met + 0.5 * partial) / n, or 1.0 when there are no requirements."""
    if not verdicts:
        return 1.0
    met = sum(1 for v in verdicts if v.verdict == "met")
    partial = sum(1 for v in verdicts if v.verdict == "partial")
    return (met + 0.5 * partial) / len(verdicts)


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    va = np.asarray(a, dtype=float)
    vb = np.asarray(b, dtype=float)
    if va.shape != vb.shape:
        raise ValueError(f"embedding shapes differ: {va.shape} vs {vb.shape}")
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def rescale_cosine(cosine: float, lo: float = SEMANTIC_LO, hi: float = SEMANTIC_HI) -> float:
    if hi <= lo:
        raise ValueError("HI must be greater than LO")
    return min(1.0, max(0.0, (cosine - lo) / (hi - lo)))


def combine(must: float, nice: float, semantic: float, weights: Weights) -> float:
    total = 100 * (weights.must * must + weights.nice * nice + weights.semantic * semantic)
    return min(100.0, max(0.0, total))


def score(
    evaluation: CandidateEvaluation,
    jd_embedding: Sequence[float],
    profile_embedding: Sequence[float],
    weights: Weights | dict,
) -> ScoreBreakdown:
    w = weights if isinstance(weights, Weights) else Weights.model_validate(weights)
    must = coverage(evaluation.must_have)
    nice = coverage(evaluation.nice_to_have)
    raw = cosine_similarity(jd_embedding, profile_embedding)
    semantic = rescale_cosine(raw)
    return ScoreBreakdown(
        must_have=must,
        nice_to_have=nice,
        semantic=semantic,
        semantic_raw=raw,
        total=combine(must, nice, semantic, w),
        missing_must_have=any(v.verdict == "not_met" for v in evaluation.must_have),
    )
