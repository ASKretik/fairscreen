"""API tests (SPEC §14): auth, owner checks, reveal gate, upload validation. Gemini and Firestore are fakes."""

import asyncio
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.cache import ParseCache
from app.config import Settings
from app.deps import Services
from app.main import create_app
from app.services.firestore import utcnow
from app.services.pipeline import STALE_ERROR
from tests.fakes import FakeGemini, InMemoryStore

TOKENS = {"token-alice": {"uid": "alice", "email": "alice@corp.example"}, "token-bob": {"uid": "bob"}}
ALICE = {"Authorization": "Bearer token-alice"}
BOB = {"Authorization": "Bearer token-bob"}
JD = "We are hiring a backend engineer with 3+ years of Python, SQL and REST API experience. Go is a plus."
PDF = b"%PDF-1.7\n" + b"x" * 200


def verify(token: str) -> dict:
    if token not in TOKENS:
        raise ValueError("bad token")
    return TOKENS[token]


@pytest.fixture
def env():
    store, gemini = InMemoryStore(), FakeGemini()
    settings = Settings(
        gemini_api_key="k", gemini_parse_model="p", gemini_eval_model="e",
        max_file_mb=1, max_files_per_upload=3, max_candidates_per_job=5,
        allowed_origins=["http://localhost:5173"],
    )
    services = Services(settings=settings, store=store, gemini=gemini,
                        parse_cache=ParseCache("fake"), verify_token=verify)
    with TestClient(create_app(services)) as client:
        yield client, store, gemini


def new_job(client) -> str:
    r = client.post("/jobs", json={"title": "Backend Engineer", "jd_text": JD}, headers=ALICE)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def upload(client, job_id, files, headers=ALICE):
    return client.post(f"/jobs/{job_id}/resumes", files=[("files", f) for f in files], headers=headers)


def scored_candidate(client, store) -> tuple[str, str]:
    job_id = new_job(client)
    r = upload(client, job_id, [("priya.pdf", PDF, "application/pdf")])
    assert r.status_code == 202, r.text
    return job_id, r.json()["candidate_ids"][0]


# --- health, auth ---------------------------------------------------------------

def test_health_needs_no_auth(env):
    client, *_ = env
    assert client.get("/health").json() == {"ok": True}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic abc"}])
def test_routes_require_a_valid_token(env, headers):
    client, store, _ = env
    assert client.post("/jobs", json={"title": "t", "jd_text": JD}, headers=headers).status_code == 401
    assert client.post("/jobs/x/candidates/y/reveal", headers=headers).status_code == 401
    assert store.jobs == {}


def test_cors_allows_configured_origin_only(env):
    client, *_ = env
    ok = client.options("/jobs", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/jobs", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


# --- jobs ------------------------------------------------------------------------

def test_create_job(env):
    client, store, _ = env
    r = client.post("/jobs", json={"title": " Backend Engineer ", "jd_text": JD}, headers=ALICE)
    assert r.status_code == 201
    body = r.json()
    assert "jdEmbedding" not in body
    stored = store.jobs[body["id"]]
    assert stored["ownerUid"] == "alice" and stored["title"] == "Backend Engineer"
    assert [m["id"] for m in stored["requirements"]["must_have"]] == ["m1", "m2", "m3"]
    assert stored["weights"] == {"must": 0.5, "nice": 0.2, "semantic": 0.3}
    assert stored["counts"] == {"total": 0, "processing": 0, "scored": 0, "failed": 0, "shortlisted": 0}
    assert stored["requirementsLocked"] is False and len(stored["jdEmbedding"]) == 2


def test_create_job_validates_body(env):
    client, *_ = env
    assert client.post("/jobs", json={"title": "", "jd_text": JD}, headers=ALICE).status_code == 422
    assert client.post("/jobs", json={"title": "t", "jd_text": "too short"}, headers=ALICE).status_code == 422
    assert client.post("/jobs", json={"title": "t"}, headers=ALICE).status_code == 422


OWN_TAGS = {
    "role_title": "Data Analyst",
    "must_have": [{"id": "x", "text": "SQL", "kind": "skill", "weight": 5}, {"id": "y", "text": " ", "kind": "skill"}],
    "nice_to_have": [{"id": "z", "text": "Tableau", "kind": "skill", "weight": 1}],
    "min_years_experience": None,
    "education_requirement": None,
}


def test_create_job_from_own_tags_skips_jd_parsing(env):
    client, store, _ = env
    r = client.post("/jobs", json={"title": "Analyst", "requirements": OWN_TAGS}, headers=ALICE)
    assert r.status_code == 201, r.text
    stored = store.jobs[r.json()["id"]]
    assert stored["jdText"] == ""
    assert [(t["id"], t["text"], t["weight"]) for t in stored["requirements"]["must_have"]] == [("m1", "SQL", 5)]
    assert [(t["id"], t["weight"]) for t in stored["requirements"]["nice_to_have"]] == [("n1", 1)]
    no_must = {**OWN_TAGS, "must_have": []}
    assert client.post("/jobs", json={"title": "A", "requirements": no_must}, headers=ALICE).status_code == 422
    heavy = {**OWN_TAGS, "must_have": [{"id": "x", "text": "SQL", "kind": "skill", "weight": 9}]}
    assert client.post("/jobs", json={"title": "A", "requirements": heavy}, headers=ALICE).status_code == 422


def test_edit_requirements_then_locked_after_upload(env):
    client, store, _ = env
    job_id = new_job(client)
    reqs = store.jobs[job_id]["requirements"]
    reqs["must_have"] = reqs["must_have"][:2] + [{"id": "zz", "text": "Docker", "kind": "skill"}]
    r = client.patch(f"/jobs/{job_id}/requirements", json=reqs, headers=ALICE)
    assert r.status_code == 200
    assert [(m["id"], m["text"]) for m in r.json()["must_have"]][-1] == ("m3", "Docker")
    assert store.jobs[job_id]["requirements"]["must_have"][2]["text"] == "Docker"

    assert upload(client, job_id, [("a.pdf", PDF, "application/pdf")]).status_code == 202
    assert store.jobs[job_id]["requirementsLocked"] is True
    assert client.patch(f"/jobs/{job_id}/requirements", json=reqs, headers=ALICE).status_code == 409


def test_edit_requirements_rejects_empty_or_too_many(env):
    client, store, _ = env
    job_id = new_job(client)
    reqs = store.jobs[job_id]["requirements"]
    empty = {**reqs, "must_have": []}
    too_many = {**reqs, "must_have": [{"id": "x", "text": f"r{i}", "kind": "skill"} for i in range(9)]}
    assert client.patch(f"/jobs/{job_id}/requirements", json=empty, headers=ALICE).status_code == 422
    assert client.patch(f"/jobs/{job_id}/requirements", json=too_many, headers=ALICE).status_code == 422


def test_other_users_cannot_touch_a_job(env):
    client, store, _ = env
    job_id, cand_id = scored_candidate(client, store)
    reqs = store.jobs[job_id]["requirements"]
    assert client.patch(f"/jobs/{job_id}/requirements", json=reqs, headers=BOB).status_code == 404
    assert upload(client, job_id, [("b.pdf", PDF, "application/pdf")], headers=BOB).status_code == 404
    base = f"/jobs/{job_id}/candidates/{cand_id}"
    assert client.post(f"{base}/status", json={"status": "shortlisted"}, headers=BOB).status_code == 404
    assert client.post(f"{base}/reveal", headers=BOB).status_code == 404
    assert store.candidates[job_id][cand_id]["status"] == "scored"


# --- upload + processing -------------------------------------------------------------

def test_upload_processes_in_background_and_keeps_identity_private(env):
    client, store, gemini = env
    job_id = new_job(client)
    r = upload(client, job_id, [("priya_sharma.pdf", PDF, "application/pdf"),
                                ("other.pdf", PDF + b"2", "application/pdf")])
    assert r.status_code == 202
    ids = r.json()["candidate_ids"]
    assert len(ids) == 2
    job = store.jobs[job_id]
    assert job["counts"] == {"total": 2, "processing": 0, "scored": 2, "failed": 0, "shortlisted": 0}
    for cid in ids:
        cand = store.candidates[job_id][cid]
        assert cand["status"] == "scored" and cand["error"] is None
        assert cand["anonId"].startswith("CAND-") and cand["revealed"] is None
        assert cand["score"]["must_have"] == 1.0 and cand["redactionCount"] > 0
        assert store.identities[(job_id, cid)]["email"] == "priya.sharma@gmail.com"
        public = json.dumps({k: v for k, v in cand.items() if k != "fileName"}, default=str).lower()
        for leak in ("priya", "sharma", "@", "98765", "github.com"):
            assert leak not in public
    for blob in gemini.eval_inputs:
        assert "priya" not in blob.lower()


def test_failed_resume_gets_a_readable_error(env):
    client, store, _ = env
    job_id = new_job(client)
    r = upload(client, job_id, [("ok.pdf", PDF, "application/pdf"), ("bad.pdf", PDF + b"FAIL", "application/pdf")])
    assert r.status_code == 202
    cands = list(store.candidates[job_id].values())
    failed = [c for c in cands if c["status"] == "failed"]
    assert len(failed) == 1 and "quota" in failed[0]["error"]
    assert store.jobs[job_id]["counts"] == {"total": 2, "processing": 0, "scored": 1, "failed": 1, "shortlisted": 0}


def test_upload_returns_candidate_ids_in_file_order(env):
    client, store, _ = env
    job_id = new_job(client)
    names = ["a.pdf", "b.pdf", "c.pdf"]
    r = upload(client, job_id, [(n, PDF + n.encode(), "application/pdf") for n in names])
    ids = r.json()["candidate_ids"]
    assert [store.candidates[job_id][cid]["fileName"] for cid in ids] == names


def test_retry_reprocesses_a_failed_candidate(env):
    client, store, _ = env
    job_id = new_job(client)
    flaky = ("flaky.pdf", PDF + b"FLAKY", "application/pdf")
    cid = upload(client, job_id, [flaky]).json()["candidate_ids"][0]
    assert store.candidates[job_id][cid]["status"] == "failed"
    anon = store.candidates[job_id][cid]["anonId"]

    r = client.post(f"/jobs/{job_id}/candidates/{cid}/retry", files={"file": flaky}, headers=ALICE)
    assert r.status_code == 202, r.text
    cand = store.candidates[job_id][cid]
    assert cand["status"] == "scored" and cand["error"] is None and cand["anonId"] == anon
    assert store.identities[(job_id, cid)]["email"] == "priya.sharma@gmail.com"
    assert store.jobs[job_id]["counts"] == {"total": 1, "processing": 0, "scored": 1, "failed": 0, "shortlisted": 0}


def test_retry_validation(env):
    client, store, _ = env
    job_id = new_job(client)
    ids = upload(client, job_id, [("ok.pdf", PDF, "application/pdf"),
                                  ("bad.pdf", PDF + b"FAIL", "application/pdf")]).json()["candidate_ids"]
    ok, bad = ids
    retry = lambda cid, f, h=ALICE: client.post(f"/jobs/{job_id}/candidates/{cid}/retry", files={"file": f}, headers=h)
    assert retry(ok, ("ok.pdf", PDF, "application/pdf")).status_code == 409  # not failed
    assert retry(bad, ("other.pdf", PDF, "application/pdf")).status_code == 409  # different file
    assert retry(bad, ("bad.pdf", b"nope", "application/pdf")).status_code == 415
    assert retry(bad, ("bad.pdf", PDF, "application/pdf"), BOB).status_code == 404
    assert retry("missing", ("bad.pdf", PDF, "application/pdf")).status_code == 404
    r = retry(bad, ("bad.pdf", PDF + b"FAIL", "application/pdf"))  # fails again, readable error again
    assert r.status_code == 202
    assert store.candidates[job_id][bad]["status"] == "failed"
    assert store.jobs[job_id]["counts"] == {"total": 2, "processing": 0, "scored": 1, "failed": 1, "shortlisted": 0}


@pytest.mark.parametrize("files, code", [
    ([("notes.txt", b"hello", "text/plain")], 415),
    ([("fake.pdf", b"not really a pdf", "application/pdf")], 415),
    ([("big.pdf", b"%PDF-" + b"0" * (1024 * 1024), "application/pdf")], 413),
    ([(f"r{i}.pdf", PDF, "application/pdf") for i in range(4)], 400),
])
def test_upload_validation(env, files, code):
    client, store, _ = env
    job_id = new_job(client)
    r = upload(client, job_id, files)
    assert r.status_code == code, r.text
    assert store.candidates[job_id] == {}
    assert store.jobs[job_id]["requirementsLocked"] is False


def test_upload_respects_candidates_per_job_limit(env):
    client, store, _ = env
    job_id = new_job(client)
    three = [(f"r{i}.pdf", PDF + bytes([i]), "application/pdf") for i in range(3)]
    assert upload(client, job_id, three).status_code == 202
    r = upload(client, job_id, three)
    assert r.status_code == 409 and "at most 5" in r.json()["detail"]


def test_oversized_request_is_rejected_before_parsing(env):
    client, store, _ = env
    job_id = new_job(client)
    r = client.post(f"/jobs/{job_id}/resumes", content=b"x", headers={**ALICE, "Content-Length": str(10**9),
                                                                         "Content-Type": "multipart/form-data"})
    assert r.status_code == 413


# --- decisions and reveal ---------------------------------------------------------

def test_status_changes_keep_shortlist_count(env):
    client, store, _ = env
    job_id, cid = scored_candidate(client, store)
    base = f"/jobs/{job_id}/candidates/{cid}/status"
    assert client.post(base, json={"status": "shortlisted"}, headers=ALICE).json()["status"] == "shortlisted"
    assert store.jobs[job_id]["counts"]["shortlisted"] == 1
    client.post(base, json={"status": "shortlisted"}, headers=ALICE)  # repeat is a no-op
    assert store.jobs[job_id]["counts"]["shortlisted"] == 1
    client.post(base, json={"status": "rejected"}, headers=ALICE)
    assert store.jobs[job_id]["counts"]["shortlisted"] == 0
    client.post(base, json={"status": "scored"}, headers=ALICE)
    assert store.candidates[job_id][cid]["status"] == "scored"
    assert client.post(base, json={"status": "processing"}, headers=ALICE).status_code == 422


def test_cannot_decide_on_processing_or_failed_candidates(env):
    client, store, _ = env
    job_id, cid = scored_candidate(client, store)
    store.candidates[job_id][cid]["status"] = "failed"
    r = client.post(f"/jobs/{job_id}/candidates/{cid}/status", json={"status": "shortlisted"}, headers=ALICE)
    assert r.status_code == 409
    assert client.post(f"/jobs/{job_id}/candidates/missing/status", json={"status": "rejected"},
                       headers=ALICE).status_code == 404


def test_reveal_requires_shortlist_and_is_logged(env):
    client, store, _ = env
    job_id, cid = scored_candidate(client, store)
    base = f"/jobs/{job_id}/candidates/{cid}"
    r = client.post(f"{base}/reveal", headers=ALICE)
    assert r.status_code == 403
    assert store.candidates[job_id][cid]["revealed"] is None

    client.post(f"{base}/status", json={"status": "shortlisted"}, headers=ALICE)
    r = client.post(f"{base}/reveal", headers=ALICE)
    assert r.status_code == 200
    body = r.json()
    assert body["identity"]["name"] == "Priya Sharma"
    assert body["identity"]["links"] and body["revealedBy"] == "alice"
    cand = store.candidates[job_id][cid]
    assert cand["revealed"]["email"] == "priya.sharma@gmail.com"
    assert cand["revealedAt"] is not None and cand["revealedBy"] == "alice"


def test_revealed_stays_revealed(env):
    client, store, _ = env
    job_id, cid = scored_candidate(client, store)
    base = f"/jobs/{job_id}/candidates/{cid}"
    client.post(f"{base}/status", json={"status": "shortlisted"}, headers=ALICE)
    first = client.post(f"{base}/reveal", headers=ALICE).json()
    client.post(f"{base}/status", json={"status": "rejected"}, headers=ALICE)
    assert store.candidates[job_id][cid]["revealed"]["name"] == "Priya Sharma"
    again = client.post(f"{base}/reveal", headers=ALICE)
    assert again.status_code == 200 and again.json()["revealedAt"] == first["revealedAt"]


# --- stale sweep -----------------------------------------------------------------

def test_startup_sweep_fails_only_stale_processing_candidates():
    store = InMemoryStore()
    job_id = asyncio.run(store.create_job({"ownerUid": "alice", "counts": {"total": 2, "processing": 2,
                                                                            "scored": 0, "failed": 0, "shortlisted": 0}}))
    now = utcnow()
    store.candidates[job_id] = {
        "old": {"status": "processing", "createdAt": now - timedelta(minutes=30), "updatedAt": now - timedelta(minutes=11)},
        "new": {"status": "processing", "createdAt": now - timedelta(minutes=2), "updatedAt": now - timedelta(minutes=2)},
    }
    settings = Settings(gemini_api_key="k", gemini_parse_model="p", gemini_eval_model="e")
    services = Services(settings=settings, store=store, gemini=FakeGemini(),
                        parse_cache=ParseCache("fake"), verify_token=verify)
    with TestClient(create_app(services)):
        pass
    assert store.candidates[job_id]["old"]["status"] == "failed"
    assert store.candidates[job_id]["old"]["error"] == STALE_ERROR
    assert store.candidates[job_id]["new"]["status"] == "processing"
    assert store.jobs[job_id]["counts"]["processing"] == 1 and store.jobs[job_id]["counts"]["failed"] == 1


# --- P1: weights and delete ------------------------------------------------------------

def test_weights_recompute_totals_without_llm_calls(env):
    client, store, gemini = env
    job_id, cid = scored_candidate(client, store)
    before = store.candidates[job_id][cid]["score"]
    evals_before = len(gemini.eval_inputs)
    r = client.patch(f"/jobs/{job_id}/weights", json={"must": 0.0, "nice": 0.0, "semantic": 1.0}, headers=ALICE)
    assert r.status_code == 200 and r.json()["rescored"] == 1
    after = store.candidates[job_id][cid]["score"]
    assert after["total"] == pytest.approx(100 * before["semantic"])
    assert {k: after[k] for k in ("must_have", "nice_to_have", "semantic")} == {
        k: before[k] for k in ("must_have", "nice_to_have", "semantic")}
    assert store.jobs[job_id]["weights"] == {"must": 0.0, "nice": 0.0, "semantic": 1.0}
    assert len(gemini.eval_inputs) == evals_before


def test_weights_must_sum_to_one_and_wait_for_processing(env):
    client, store, _ = env
    job_id, cid = scored_candidate(client, store)
    assert client.patch(f"/jobs/{job_id}/weights", json={"must": 0.5, "nice": 0.5, "semantic": 0.5},
                        headers=ALICE).status_code == 422
    store.candidates[job_id][cid]["status"] = "processing"
    assert client.patch(f"/jobs/{job_id}/weights", json={"must": 0.4, "nice": 0.3, "semantic": 0.3},
                        headers=ALICE).status_code == 409
    assert client.patch(f"/jobs/{job_id}/weights", json={"must": 0.4, "nice": 0.3, "semantic": 0.3},
                        headers=BOB).status_code == 404


def test_tag_weights_rescore_from_the_checklist(env):
    client, store, gemini = env
    job_id, cid = scored_candidate(client, store)
    store.candidates[job_id][cid]["evaluation"]["must_have"][0]["verdict"] = "not_met"  # m1 missing, m2 and m3 met
    evals_before = len(gemini.eval_inputs)
    body = {"must": 1.0, "nice": 0.0, "semantic": 0.0, "tag_weights": {"m1": 5, "m2": 1, "m3": 1}}
    r = client.patch(f"/jobs/{job_id}/weights", json=body, headers=ALICE)
    assert r.status_code == 200, r.text
    assert r.json()["tag_weights"] == {"m1": 5, "m2": 1, "m3": 1, "n1": 3}
    score = store.candidates[job_id][cid]["score"]
    assert score["must_have"] == pytest.approx(2 / 7) and score["total"] == pytest.approx(100 * 2 / 7)
    assert [t["weight"] for t in store.jobs[job_id]["requirements"]["must_have"]] == [5, 1, 1]
    assert store.jobs[job_id]["requirementsLocked"] is True  # tags stay locked; only weights changed
    assert len(gemini.eval_inputs) == evals_before


def test_tag_weights_validation(env):
    client, store, _ = env
    job_id, _ = scored_candidate(client, store)
    base = {"must": 0.5, "nice": 0.2, "semantic": 0.3}
    assert client.patch(f"/jobs/{job_id}/weights", json={**base, "tag_weights": {"zz": 2}},
                        headers=ALICE).status_code == 422
    assert client.patch(f"/jobs/{job_id}/weights", json={**base, "tag_weights": {"m1": 0}},
                        headers=ALICE).status_code == 422


def test_delete_job_removes_candidates_and_identity(env):
    client, store, _ = env
    job_id, cid = scored_candidate(client, store)
    assert client.delete(f"/jobs/{job_id}", headers=BOB).status_code == 404
    assert client.delete(f"/jobs/{job_id}", headers=ALICE).status_code == 204
    assert job_id not in store.jobs and job_id not in store.candidates
    assert (job_id, cid) not in store.identities
    assert client.delete(f"/jobs/{job_id}", headers=ALICE).status_code == 404
