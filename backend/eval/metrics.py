"""Ranking metrics for the offline evaluation (SPEC §11). Relevance is binary: category match."""

import math
from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


def rank(items: Sequence[T], key: Callable[[T], float], tiebreak: Callable[[T], str]) -> list[T]:
    """Highest key first; ties broken by `tiebreak` so results are reproducible."""
    return sorted(items, key=lambda x: (-key(x), tiebreak(x)))


def precision_at_k(relevance: Sequence[bool], k: int) -> float:
    """Share of the top k that are relevant (the denominator is k even if fewer items exist)."""
    return sum(relevance[:k]) / k


def ndcg_at_k(relevance: Sequence[bool], k: int) -> float:
    """Binary nDCG@k: DCG = sum(rel_i / log2(i + 1)) for i = 1..k, divided by the ideal DCG."""
    dcg = sum(1 / math.log2(i + 2) for i, rel in enumerate(relevance[:k]) if rel)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, sum(relevance))))
    return dcg / ideal if ideal else 0.0


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile (same as numpy's default), q in [0, 100]."""
    if not values:
        raise ValueError("no values")
    s = sorted(values)
    pos = (len(s) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)
