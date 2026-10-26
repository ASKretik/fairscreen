"""Deterministic score (SPEC §7.4). The LLM judges requirements; the number is computed here.

Each requirement (tag) has a weight from 1 to 5 within its group, so coverage is a weighted
mean of verdict values (met 1, partial 0.5, not met 0). With equal tag weights this is the
SPEC formula exactly: (met + 0.5 * partial) / n.
"""

from collections.abc import Mapping, Sequence

import numpy as np

from app.models import (
    DEFAULT_TAG_WEIGHT,
    CandidateEvaluation,
    JobRequirements,
    RequirementVerdict,
    ScoreBreakdown,
    Weights,
)

# Bounds for rescaling raw cosine similarity to 0–1. SPEC §7.4 defaults; recalibrate
# in Phase 5 from the 10th/90th percentiles of the eval pool's raw cosines.
SEMANTIC_LO = 0.55
SEMANTIC_HI = 0.85


VERDICT_VALUE = {"met": 1.0, "partial": 0.5, "not_met": 0.0}


def tag_weights(requirements: JobRequirements) -> dict[str, int]:
    return {r.id: r.weight for r in [*requirements.must_have, *requirements.nice_to_have]}


def coverage(verdicts: Sequence[RequirementVerdict], weights: Mapping[str, float] | None = None) -> float:
    """Weighted mean of verdict values (tag weights by req_id, default 3), or 1.0 when there are
    no requirements. Equal weights give (met + 0.5 * partial) / n."""
    if not verdicts:
        return 1.0
    weights = weights or {}
    total = sum(weights.get(v.req_id, DEFAULT_TAG_WEIGHT) for v in verdicts)
    if total <= 0:
        return 1.0
    return sum(weights.get(v.req_id, DEFAULT_TAG_WEIGHT) * VERDICT_VALUE[v.verdict] for v in verdicts) / total


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
    tags: Mapping[str, float] | None = None,
) -> ScoreBreakdown:
    """`tags` holds tag weights by requirement ID (see tag_weights); missing ones count as 3."""
    w = weights if isinstance(weights, Weights) else Weights.model_validate(weights)
    must = coverage(evaluation.must_have, tags)
    nice = coverage(evaluation.nice_to_have, tags)
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


def rescore(
    breakdown: ScoreBreakdown, evaluation: CandidateEvaluation, weights: Weights, tags: Mapping[str, float] | None
) -> ScoreBreakdown:
    """New group and tag weights applied to a stored score: no LLM or embedding calls."""
    must = coverage(evaluation.must_have, tags)
    nice = coverage(evaluation.nice_to_have, tags)
    return breakdown.model_copy(
        update={
            "must_have": must,
            "nice_to_have": nice,
            "total": combine(must, nice, breakdown.semantic, weights),
        }
    )
