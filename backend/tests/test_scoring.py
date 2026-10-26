import math

import pytest
from pydantic import ValidationError

from app.models import CandidateEvaluation, RequirementVerdict, Weights
from app.scoring import SEMANTIC_HI, SEMANTIC_LO, cosine_similarity, coverage, rescale_cosine, score


def v(verdict: str, i: int = 1) -> RequirementVerdict:
    return RequirementVerdict(req_id=f"m{i}", verdict=verdict, evidence="" if verdict == "not_met" else "x")


def evaluation(must: list[str], nice: list[str]) -> CandidateEvaluation:
    return CandidateEvaluation(
        must_have=[v(x, i) for i, x in enumerate(must, 1)],
        nice_to_have=[v(x, i) for i, x in enumerate(nice, 1)],
        strengths=[], gaps=[], summary="",
    )


def vectors_with_cosine(c: float) -> tuple[list[float], list[float]]:
    return [1.0, 0.0], [c, math.sqrt(1 - c * c)]


MID = (SEMANTIC_LO + SEMANTIC_HI) / 2  # a cosine that rescales to exactly 0.5


def test_coverage_formula():
    assert coverage([v("met"), v("partial"), v("not_met"), v("met")]) == pytest.approx(2.5 / 4)
    assert coverage([v("partial"), v("partial")]) == pytest.approx(0.5)
    assert coverage([v("not_met")]) == 0.0


def test_coverage_is_one_with_no_requirements():
    assert coverage([]) == 1.0


def test_full_formula_with_default_weights():
    jd, prof = vectors_with_cosine(MID)  # semantic = 0.5
    s = score(evaluation(["met", "partial", "not_met", "met"], ["partial"]), jd, prof, Weights())
    assert s.must_have == pytest.approx(0.625)
    assert s.nice_to_have == pytest.approx(0.5)
    assert s.semantic_raw == pytest.approx(MID)
    assert s.semantic == pytest.approx(0.5)
    assert s.total == pytest.approx(100 * (0.5 * 0.625 + 0.2 * 0.5 + 0.3 * 0.5))
    assert s.missing_must_have is True


def test_zero_requirements_score_full_coverage():
    jd, prof = vectors_with_cosine(SEMANTIC_HI)
    s = score(evaluation([], []), jd, prof, Weights())
    assert (s.must_have, s.nice_to_have, s.semantic) == (1.0, 1.0, pytest.approx(1.0))
    assert s.total == pytest.approx(100.0)
    assert s.missing_must_have is False


@pytest.mark.parametrize("cos, expected", [
    (0.95, 1.0), (SEMANTIC_HI, 1.0), (MID, 0.5), (SEMANTIC_LO, 0.0), (0.30, 0.0), (-0.5, 0.0),
])
def test_cosine_is_rescaled_and_clipped(cos, expected):
    assert rescale_cosine(cos) == pytest.approx(expected)


def test_raw_cosine_is_kept_even_when_clipped():
    jd, prof = vectors_with_cosine(0.2)
    s = score(evaluation(["met"], []), jd, prof, Weights())
    assert s.semantic == 0.0
    assert s.semantic_raw == pytest.approx(0.2)


def test_rescale_rejects_bad_bounds():
    with pytest.raises(ValueError):
        rescale_cosine(0.7, lo=0.8, hi=0.8)


def test_cosine_similarity():
    assert cosine_similarity([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine_similarity([0, 0], [1, 1]) == 0.0
    with pytest.raises(ValueError):
        cosine_similarity([1, 0], [1, 0, 0])


@pytest.mark.parametrize("must, flag", [
    (["met", "met"], False), (["met", "partial"], False), (["met", "not_met"], True), ([], False),
])
def test_missing_must_have_flag(must, flag):
    jd, prof = vectors_with_cosine(0.7)
    assert score(evaluation(must, []), jd, prof, Weights()).missing_must_have is flag


def test_missing_must_have_does_not_zero_the_score():
    jd, prof = vectors_with_cosine(0.85)
    s = score(evaluation(["met", "met", "not_met"], []), jd, prof, Weights())
    assert s.missing_must_have and s.total > 0


def test_weights_default_and_custom():
    assert Weights().model_dump() == {"must": 0.5, "nice": 0.2, "semantic": 0.3}
    jd, prof = vectors_with_cosine(MID)
    ev = evaluation(["met", "not_met"], ["met"])
    s = score(ev, jd, prof, {"must": 1.0, "nice": 0.0, "semantic": 0.0})
    assert s.total == pytest.approx(50.0)
    s = score(ev, jd, prof, Weights(must=0.0, nice=0.0, semantic=1.0))
    assert s.total == pytest.approx(50.0)


@pytest.mark.parametrize("w", [
    dict(must=0.5, nice=0.5, semantic=0.5),
    dict(must=0.2, nice=0.2, semantic=0.2),
    dict(must=1.2, nice=-0.1, semantic=-0.1),
])
def test_weights_must_sum_to_one(w):
    with pytest.raises(ValidationError):
        Weights(**w)


def test_weights_tolerate_float_rounding():
    Weights(must=0.1 + 0.2, nice=0.4, semantic=0.3)


# --- tag weights ---------------------------------------------------------------------

def test_equal_tag_weights_give_the_spec_formula():
    verdicts = [v("met", 1), v("partial", 2), v("not_met", 3), v("met", 4)]
    assert coverage(verdicts, {f"m{i}": 5 for i in range(1, 5)}) == pytest.approx(2.5 / 4)
    assert coverage(verdicts, {}) == pytest.approx(2.5 / 4)


def test_tag_weights_shift_coverage():
    verdicts = [v("met", 1), v("not_met", 2)]
    assert coverage(verdicts, {"m1": 5, "m2": 1}) == pytest.approx(5 / 6)
    assert coverage(verdicts, {"m1": 1, "m2": 5}) == pytest.approx(1 / 6)
    assert coverage(verdicts, {"m1": 1}) == pytest.approx(1 / 4)  # missing IDs count as the default, 3


def test_score_and_rescore_use_tag_weights_without_touching_semantic():
    from app.scoring import rescore

    jd, prof = vectors_with_cosine(MID)
    ev = evaluation(["met", "not_met"], ["met"])
    s = score(ev, jd, prof, Weights(), {"m1": 4, "m2": 1})
    assert s.must_have == pytest.approx(0.8)
    assert s.total == pytest.approx(100 * (0.5 * 0.8 + 0.2 * 1.0 + 0.3 * 0.5))
    again = rescore(s, ev, Weights(must=1.0, nice=0.0, semantic=0.0), {"m1": 1, "m2": 4})
    assert again.must_have == pytest.approx(0.2) and again.total == pytest.approx(20.0)
    assert (again.semantic, again.semantic_raw, again.missing_must_have) == (s.semantic, s.semantic_raw, True)


def test_tag_weights_are_validated():
    from app.models import Requirement, WeightsUpdate

    assert Requirement(id="m1", text="SQL", kind="skill").weight == 3
    for bad in (0, 6):
        with pytest.raises(ValidationError):
            Requirement(id="m1", text="SQL", kind="skill", weight=bad)
        with pytest.raises(ValidationError):
            WeightsUpdate(tag_weights={"m1": bad})
    assert WeightsUpdate(tag_weights={"m1": 5}).group_weights() == Weights()
