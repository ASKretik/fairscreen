"""Pipeline wiring with a fake Gemini: the evaluator and embedding only ever see the blind profile."""

import asyncio

import pytest

from app.cache import ParseCache
from app.models import (
    CandidateEvaluation,
    JobRequirements,
    Requirement,
    RequirementVerdict,
    Weights,
)
from app.services.gemini import align_evaluation, normalise_requirements
from app.services.pipeline import jd_embedding_text, new_anon_id, process_resume, profile_embedding_text
from tests.test_blind import make_parsed

PDF = b"%PDF-1.7 fake resume bytes"

REQS = JobRequirements(
    role_title="Backend Engineer",
    must_have=[Requirement(id="m1", text="3+ years Python", kind="experience"),
               Requirement(id="m2", text="SQL", kind="skill")],
    nice_to_have=[Requirement(id="n1", text="Go", kind="skill")],
    min_years_experience=3,
    education_requirement=None,
)


class FakeGemini:
    def __init__(self):
        self.parse_calls = 0
        self.eval_inputs: list[str] = []
        self.embed_inputs: list[str] = []

    async def parse_resume(self, pdf_bytes):
        self.parse_calls += 1
        return make_parsed()

    async def evaluate(self, profile, requirements):
        self.eval_inputs.append(profile.model_dump_json())
        return CandidateEvaluation(
            must_have=[RequirementVerdict(req_id="m1", verdict="met", evidence="4 yrs Python at Infosys"),
                       RequirementVerdict(req_id="m2", verdict="partial", evidence="SQL listed in skills")],
            nice_to_have=[RequirementVerdict(req_id="n1", verdict="met", evidence="Go payment APIs")],
            strengths=["Python"], gaps=["SQL depth"], summary="Strong backend fit. Some SQL gaps.",
        )

    async def embed(self, text):
        self.embed_inputs.append(text)
        return [1.0, 0.0]


def run(coro):
    return asyncio.run(coro)


def test_scorer_inputs_contain_no_identity():
    gemini = FakeGemini()
    res = run(process_resume(PDF, REQS, [1.0, 0.0], Weights(), gemini, ParseCache("t")))
    for blob in gemini.eval_inputs + gemini.embed_inputs:
        low = blob.lower()
        for leak in ("priya", "sharma", "@", "98765", "github.com", "maharashtra"):
            assert leak not in low
    assert res.identity.name == "Priya Sharma"
    assert res.redaction_count > 0
    assert res.score.must_have == pytest.approx(0.75)
    assert res.score.semantic == pytest.approx(1.0)


def test_parse_is_cached_by_pdf_hash(tmp_path):
    gemini = FakeGemini()
    cache = ParseCache("tag-a", disk_root=tmp_path)
    run(process_resume(PDF, REQS, [1.0, 0.0], Weights(), gemini, cache))
    run(process_resume(PDF, REQS, [1.0, 0.0], Weights(), gemini, cache))
    assert gemini.parse_calls == 1
    # The disk copy survives a restart, but only for the same model/prompt tag.
    assert ParseCache("tag-a", disk_root=tmp_path).get(res_sha(cache)) is not None
    assert ParseCache("tag-b", disk_root=tmp_path).get(res_sha(cache)) is None


def res_sha(cache: ParseCache) -> str:
    return next(iter(cache._memory))


def test_non_pdf_is_rejected():
    with pytest.raises(ValueError):
        run(process_resume(b"hello", REQS, [1.0, 0.0], Weights(), FakeGemini(), ParseCache("t")))


def test_embedding_texts():
    text = jd_embedding_text(REQS)
    assert "Backend Engineer" in text and "Must have: SQL" in text and "Nice to have: Go" in text
    profile_text = profile_embedding_text(make_parsed().profile)
    assert "B.Tech in Computer Science" in profile_text
    # institution and employer names are not part of the semantic signal
    assert "College of Engineering" not in profile_text and "Infosys" not in profile_text


def test_anon_ids_are_unique_and_well_formed():
    taken: set[str] = set()
    for _ in range(200):
        a = new_anon_id(taken)
        assert a.startswith("CAND-") and len(a) == 9
        assert a not in taken
        taken.add(a)


def test_align_evaluation_fills_gaps_and_enforces_limits():
    ev = CandidateEvaluation(
        must_have=[
            RequirementVerdict(req_id="m2", verdict="met", evidence=" ".join(["word"] * 30)),
            RequirementVerdict(req_id="zz", verdict="met", evidence="unknown id"),
        ],
        nice_to_have=[RequirementVerdict(req_id="n1", verdict="not_met", evidence="should be cleared")],
        strengths=["a", "b", "c", "d"], gaps=["x", "", "y", "z", "w"],
        summary="She is a good fit. Her SQL is weak.",
    )
    out = align_evaluation(ev, REQS)
    assert [v.req_id for v in out.must_have] == ["m1", "m2"]
    assert out.must_have[0].verdict == "not_met" and out.must_have[0].evidence == ""
    assert len(out.must_have[1].evidence.split()) == 20
    assert out.nice_to_have[0].evidence == ""
    assert out.strengths == ["a", "b", "c"] and out.gaps == ["x", "y", "z"]
    assert out.summary == "They are a good fit. Their SQL is weak."


def test_normalise_requirements_renumbers_and_caps():
    raw = JobRequirements(
        role_title=" Analyst ",
        must_have=[Requirement(id="x", text=f"req {i}", kind="skill") for i in range(10)]
        + [Requirement(id="y", text="  ", kind="other")],
        nice_to_have=[Requirement(id="m1", text="SQL", kind="skill")],
        min_years_experience=None,
        education_requirement=None,
    )
    req = normalise_requirements(raw)
    assert req.role_title == "Analyst"
    assert [r.id for r in req.must_have] == [f"m{i}" for i in range(1, 9)]
    assert [r.id for r in req.nice_to_have] == ["n1"]
