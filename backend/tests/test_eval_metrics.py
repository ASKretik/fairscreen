import math

import numpy as np
import pytest

from eval.metrics import ndcg_at_k, percentile, precision_at_k, rank


def test_precision_at_k():
    rel = [True, False, True, True, False, False]
    assert precision_at_k(rel, 1) == 1.0
    assert precision_at_k(rel, 5) == pytest.approx(3 / 5)
    assert precision_at_k(rel, 10) == pytest.approx(3 / 10)  # denominator stays k


def test_ndcg_at_k():
    assert ndcg_at_k([True, True, False, False], 10) == pytest.approx(1.0)
    assert ndcg_at_k([False, False, False], 10) == 0.0
    rel = [False, True, False, True]
    dcg = 1 / math.log2(3) + 1 / math.log2(5)
    idcg = 1 / math.log2(2) + 1 / math.log2(3)
    assert ndcg_at_k(rel, 10) == pytest.approx(dcg / idcg)
    assert ndcg_at_k([False] * 10 + [True], 10) == 0.0  # relevant item outside the cut


def test_rank_is_deterministic_on_ties():
    items = [("b", 0.5), ("a", 0.5), ("c", 0.9)]
    assert [x[0] for x in rank(items, key=lambda x: x[1], tiebreak=lambda x: x[0])] == ["c", "a", "b"]


def test_percentile_matches_numpy():
    values = [0.61, 0.72, 0.55, 0.81, 0.66, 0.70, 0.59]
    for q in (0, 10, 50, 90, 100):
        assert percentile(values, q) == pytest.approx(float(np.percentile(values, q)))
    with pytest.raises(ValueError):
        percentile([], 50)
