"""In-memory stand-ins for Firestore and Gemini, used by the API tests."""

import copy
import uuid
from typing import Any

from app.models import (
    CandidateEvaluation,
    JobRequirements,
    Requirement,
    RequirementVerdict,
)
from app.services.firestore import Mutator, NotFoundError
from app.services.gemini import GeminiError
from tests.test_blind import make_parsed


def _apply(doc: dict[str, Any], fields: dict[str, Any]) -> None:
    """Firestore-style update: "a.b" keys set nested fields."""
    for key, value in fields.items():
        target = doc
        *parents, leaf = key.split(".")
        for p in parents:
            target = target.setdefault(p, {})
        target[leaf] = copy.deepcopy(value)


class InMemoryStore:
    def __init__(self):
        self.jobs: dict[str, dict[str, Any]] = {}
        self.candidates: dict[str, dict[str, dict[str, Any]]] = {}
        self.identities: dict[tuple[str, str], dict[str, Any]] = {}

    def _bump(self, job_id: str, counts: dict[str, int]) -> None:
        job_counts = self.jobs[job_id].setdefault("counts", {})
        for k, v in counts.items():
            job_counts[k] = job_counts.get(k, 0) + v

    async def create_job(self, data):
        job_id = uuid.uuid4().hex[:20]
        self.jobs[job_id] = copy.deepcopy(data)
        self.candidates[job_id] = {}
        return job_id

    async def get_job(self, job_id):
        job = self.jobs.get(job_id)
        return {**copy.deepcopy(job), "id": job_id} if job else None

    async def update_job(self, job_id, fields):
        if job_id not in self.jobs:
            raise NotFoundError(job_id)
        _apply(self.jobs[job_id], fields)

    async def list_candidates(self, job_id):
        return [{**copy.deepcopy(c), "id": cid} for cid, c in self.candidates.get(job_id, {}).items()]

    async def add_candidates(self, job_id, docs, job_fields, counts):
        ids = []
        for doc in docs:
            cid = uuid.uuid4().hex[:20]
            self.candidates[job_id][cid] = copy.deepcopy(doc)
            ids.append(cid)
        _apply(self.jobs[job_id], job_fields)
        self._bump(job_id, counts)
        return ids

    async def mutate_candidate(self, job_id, cand_id, fn: Mutator, read_identity=False):
        cand = self.candidates.get(job_id, {}).get(cand_id)
        if cand is None:
            raise NotFoundError(cand_id)
        identity = copy.deepcopy(self.identities.get((job_id, cand_id))) if read_identity else None
        change = fn(copy.deepcopy(cand), identity)  # no await between read and write: atomic
        _apply(cand, change.candidate)
        if change.identity is not None:
            self.identities[(job_id, cand_id)] = copy.deepcopy(change.identity)
        self._bump(job_id, change.counts)
        return change.result

    async def update_candidates(self, job_id, updates, job_fields):
        for cid, fields in updates.items():
            _apply(self.candidates[job_id][cid], fields)
        _apply(self.jobs[job_id], job_fields)

    async def delete_job(self, job_id):
        self.jobs.pop(job_id, None)
        self.candidates.pop(job_id, None)
        for key in [k for k in self.identities if k[0] == job_id]:
            del self.identities[key]

    async def processing_candidates(self):
        return [
            (jid, {**copy.deepcopy(c), "id": cid})
            for jid, job in self.jobs.items()
            if job.get("counts", {}).get("processing", 0) > 0
            for cid, c in self.candidates[jid].items()
            if c.get("status") == "processing"
        ]


FAKE_REQS = JobRequirements(
    role_title="Backend Engineer",
    must_have=[
        Requirement(id="m1", text="3+ years Python", kind="experience"),
        Requirement(id="m2", text="SQL", kind="skill"),
        Requirement(id="m3", text="REST APIs", kind="skill"),
    ],
    nice_to_have=[Requirement(id="n1", text="Go", kind="skill")],
    min_years_experience=3,
    education_requirement=None,
)


class FakeGemini:
    """PDFs containing b"FAIL" fail like an exhausted quota; b"FLAKY" ones fail the first time only."""

    parse_cache_tag = "fake"

    def __init__(self):
        self.eval_inputs: list[str] = []
        self.flaky_failed: set[bytes] = set()

    async def parse_jd(self, jd_text):
        return FAKE_REQS

    async def embed(self, text):
        return [1.0, 0.0]

    async def parse_resume(self, pdf_bytes):
        if b"FAIL" in pdf_bytes or (b"FLAKY" in pdf_bytes and pdf_bytes not in self.flaky_failed):
            self.flaky_failed.add(pdf_bytes)
            raise GeminiError("Gemini rate limit or free-tier quota reached. Wait a minute and retry.")
        return make_parsed()

    async def evaluate(self, profile, requirements):
        self.eval_inputs.append(profile.model_dump_json())
        return CandidateEvaluation(
            must_have=[RequirementVerdict(req_id=r.id, verdict="met", evidence="shown in experience")
                       for r in requirements.must_have],
            nice_to_have=[RequirementVerdict(req_id=r.id, verdict="partial", evidence="related project")
                          for r in requirements.nice_to_have],
            strengths=["Python"], gaps=["Kubernetes"], summary="Strong fit. Minor gaps.",
        )
