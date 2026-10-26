"""Per-resume pipeline (SPEC §7.2).

`process_resume` is the Firestore-free core, shared by run_local.py,
build_demo.py and eval. `run_batch` wraps it for the API: it runs as a
background task and writes progress to Firestore, which the UI listens to.
"""

import asyncio
import logging
import secrets
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from app import blind, scoring
from app.cache import ParseCache, sha256_hex
from app.models import (
    BlindProfile,
    CandidateEvaluation,
    Identity,
    JobRequirements,
    ScoreBreakdown,
    Weights,
)
from app.services.firestore import CandidateChange, Mutator, utcnow
from app.services.gemini import EMBED_MAX_CHARS, GeminiError, GeminiService

if TYPE_CHECKING:
    from app.deps import Services

log = logging.getLogger("fairscreen.pipeline")

STALE_AFTER = timedelta(minutes=10)
STALE_ERROR = "Processing was interrupted (the server restarted). Upload this PDF again to retry."
UNEXPECTED_ERROR = "Unexpected error while processing this resume."


@dataclass
class ResumeResult:
    sha256: str
    profile: BlindProfile
    identity: Identity
    photo_present: bool
    redaction_count: int
    evaluation: CandidateEvaluation
    score: ScoreBreakdown


def is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def new_anon_id(taken: Collection[str] = ()) -> str:
    """Random "CAND-7F3A"-style ID, unique among `taken`."""
    while True:
        anon = f"CAND-{secrets.token_hex(2).upper()}"
        if anon not in taken:
            return anon


def jd_embedding_text(req: JobRequirements) -> str:
    lines = [req.role_title]
    lines += [f"Must have: {r.text}" for r in req.must_have]
    lines += [f"Nice to have: {r.text}" for r in req.nice_to_have]
    return "\n".join(lines)[:EMBED_MAX_CHARS]


def profile_embedding_text(profile: BlindProfile) -> str:
    """Headline, skills, experience titles and summaries, project summaries, degree and field.

    Institution and employer names are left out, so prestige cannot move the semantic score.
    """
    parts = [profile.headline]
    if profile.skills:
        parts.append("Skills: " + ", ".join(profile.skills))
    for e in profile.experience:
        parts.append(": ".join(x for x in (e.title, e.summary) if x))
    parts += [p.summary for p in profile.projects]
    for ed in profile.education:
        parts.append(" in ".join(x for x in (ed.degree, ed.field) if x))
    return "\n".join(p for p in parts if p)[:EMBED_MAX_CHARS]


async def process_resume(
    pdf_bytes: bytes,
    requirements: JobRequirements,
    jd_embedding: Sequence[float],
    weights: Weights,
    gemini: GeminiService,
    cache: ParseCache,
) -> ResumeResult:
    """Parse (cached by PDF SHA-256) → redact → evaluate + embed → score."""
    if not is_pdf(pdf_bytes):
        raise ValueError("File is not a PDF.")
    sha = sha256_hex(pdf_bytes)
    parsed = cache.get(sha)
    if parsed is None:
        parsed = await gemini.parse_resume(pdf_bytes)
        cache.put(sha, parsed)

    profile, identity, redaction_count = blind.redact(parsed)
    # Only the blind profile goes past this point (SPEC §5).
    evaluation, profile_embedding = await asyncio.gather(
        gemini.evaluate(profile, requirements),
        gemini.embed(profile_embedding_text(profile)),
    )
    breakdown = scoring.score(evaluation, jd_embedding, profile_embedding, weights, scoring.tag_weights(requirements))
    return ResumeResult(
        sha256=sha,
        profile=profile,
        identity=identity,
        photo_present=parsed.photo_present,
        redaction_count=redaction_count,
        evaluation=evaluation,
        score=breakdown,
    )


def finish_processing(fields: dict[str, Any], counts: dict[str, int], identity: dict[str, Any] | None = None) -> Mutator:
    """Leave `processing` exactly once: if the candidate already left it (e.g. the
    stale sweep failed it), do nothing, so counts are never applied twice."""

    def fn(cand: dict[str, Any], _identity: dict[str, Any] | None) -> CandidateChange:
        if cand.get("status") != "processing":
            return CandidateChange(result=False)
        return CandidateChange(
            candidate={**fields, "updatedAt": utcnow()}, counts=counts, identity=identity, result=True
        )

    return fn


async def run_candidate(services: "Services", job: dict[str, Any], cand_id: str, pdf_bytes: bytes) -> None:
    job_id = job["id"]
    store = services.store
    try:
        res = await process_resume(
            pdf_bytes,
            JobRequirements.model_validate(job["requirements"]),
            job["jdEmbedding"],
            Weights.model_validate(job["weights"]),
            services.gemini,
            services.parse_cache,
        )
    except Exception as e:
        # GeminiError / ValueError messages are written for users; anything else gets a generic message.
        message = str(e) if isinstance(e, (GeminiError, ValueError)) else UNEXPECTED_ERROR
        log.warning("candidate %s/%s failed: %s", job_id, cand_id, type(e).__name__)
        fn = finish_processing({"status": "failed", "error": message}, {"processing": -1, "failed": 1})
    else:
        fn = finish_processing(
            {
                "status": "scored",
                "error": None,
                "profile": res.profile.model_dump(),
                "evaluation": res.evaluation.model_dump(),
                "score": res.score.model_dump(),
                "photoPresent": res.photo_present,
                "redactionCount": res.redaction_count,
            },
            {"processing": -1, "scored": 1},
            identity=res.identity.model_dump(),
        )
    try:
        await store.mutate_candidate(job_id, cand_id, fn)
    except Exception:
        # Left in `processing`; the startup sweep will fail it later.
        log.exception("could not save result for candidate %s/%s", job_id, cand_id)


async def run_batch(services: "Services", job: dict[str, Any], items: list[tuple[str, bytes]]) -> None:
    """Background task for one upload. The PDF bytes live only in memory, until this returns."""
    await asyncio.gather(*(run_candidate(services, job, cand_id, data) for cand_id, data in items))


async def sweep_stale(services: "Services", now: Any = None) -> int:
    """Fail candidates stuck in `processing` for more than 10 minutes (SPEC §7.5).

    Background tasks die with the process, and Render can restart the free
    instance at any time. Returns how many candidates were failed.
    """
    cutoff = (now or utcnow()) - STALE_AFTER
    failed = 0
    for job_id, cand in await services.store.processing_candidates():
        last = cand.get("updatedAt") or cand.get("createdAt")
        if last is not None and last < cutoff:
            fn = finish_processing({"status": "failed", "error": STALE_ERROR}, {"processing": -1, "failed": 1})
            if await services.store.mutate_candidate(job_id, cand["id"], fn):
                failed += 1
    if failed:
        log.warning("marked %d stale processing candidate(s) as failed", failed)
    return failed
