"""Job routes (SPEC §8): create job, edit requirements, upload resumes."""

import logging
import random
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.auth import User, current_user
from app.deps import Services, get_services
from app import scoring
from app.models import JobRequirements, ScoreBreakdown, Weights
from app.services.firestore import utcnow
from app.services.gemini import MAX_MUST, MAX_NICE, GeminiError, normalise_requirements
from app.services.pipeline import is_pdf, jd_embedding_text, new_anon_id, run_batch

log = logging.getLogger("fairscreen.jobs")

router = APIRouter(prefix="/jobs", tags=["jobs"])

EMPTY_COUNTS = {"total": 0, "processing": 0, "scored": 0, "failed": 0, "shortlisted": 0}


class CreateJobBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    jd_text: str = Field(min_length=50, max_length=20_000)


async def owned_job(job_id: str, user: User, services: Services) -> dict[str, Any]:
    """404 both when the job doesn't exist and when it isn't yours, so IDs can't be probed."""
    job = await services.store.get_job(job_id)
    if not job or job.get("ownerUid") != user.uid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    return job


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in job.items() if k != "jdEmbedding"}


def _gemini_failed(e: GeminiError) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))


class BadUpload(Exception):
    """A file that is too large (413) or not a PDF (415)."""

    def __init__(self, code: int, name: str):
        self.code, self.name = code, name


def upload_name(f: UploadFile) -> str:
    return (f.filename or "file").rsplit("/", 1)[-1]


async def read_pdf(f: UploadFile, max_bytes: int) -> bytes:
    """The file's bytes, kept in memory only. Raises BadUpload if it is too large or not a PDF."""
    name = upload_name(f)
    if f.size is not None and f.size > max_bytes:
        raise BadUpload(status.HTTP_413_CONTENT_TOO_LARGE, name)
    data = await f.read()
    if len(data) > max_bytes:
        raise BadUpload(status.HTTP_413_CONTENT_TOO_LARGE, name)
    if not (name.lower().endswith(".pdf") and is_pdf(data)):
        raise BadUpload(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, name)
    return data


def upload_error(code: int, names: list[str], max_file_mb: int) -> HTTPException:
    if code == status.HTTP_413_CONTENT_TOO_LARGE:
        return HTTPException(code, f"Files must be {max_file_mb} MB or smaller: {', '.join(names)}.")
    return HTTPException(code, f"Only PDF resumes are supported: {', '.join(names)}.")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_job(
    body: CreateJobBody, user: User = Depends(current_user), services: Services = Depends(get_services)
) -> dict[str, Any]:
    """Parse the JD, embed it and create the job (SPEC §7.1)."""
    try:
        requirements = await services.gemini.parse_jd(body.jd_text)
        jd_embedding = await services.gemini.embed(jd_embedding_text(requirements))
    except GeminiError as e:
        raise _gemini_failed(e) from e
    now = utcnow()
    job = {
        "ownerUid": user.uid,
        "title": body.title.strip(),
        "jdText": body.jd_text,
        "requirements": requirements.model_dump(),
        "requirementsLocked": False,
        "weights": Weights().model_dump(),
        "jdEmbedding": jd_embedding,
        "counts": dict(EMPTY_COUNTS),
        "createdAt": now,
        "updatedAt": now,
    }
    job_id = await services.store.create_job(job)
    log.info("job %s created", job_id)
    return public_job({**job, "id": job_id})


@router.patch("/{job_id}/requirements")
async def update_requirements(
    job_id: str,
    body: JobRequirements,
    user: User = Depends(current_user),
    services: Services = Depends(get_services),
) -> JobRequirements:
    """Edit requirements before the first upload; re-embeds the JD."""
    job = await owned_job(job_id, user, services)
    if job.get("requirementsLocked"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Requirements are locked once resumes have been uploaded.")
    must = [r for r in body.must_have if r.text.strip()]
    nice = [r for r in body.nice_to_have if r.text.strip()]
    if not 1 <= len(must) <= MAX_MUST or len(nice) > MAX_NICE or not body.role_title.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Give a role title, 1–{MAX_MUST} must-haves and at most {MAX_NICE} nice-to-haves.",
        )
    if any(len(r.text) > 300 for r in must + nice):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Each requirement must be 300 characters or fewer.")
    requirements = normalise_requirements(body)
    try:
        jd_embedding = await services.gemini.embed(jd_embedding_text(requirements))
    except GeminiError as e:
        raise _gemini_failed(e) from e
    await services.store.update_job(
        job_id, {"requirements": requirements.model_dump(), "jdEmbedding": jd_embedding, "updatedAt": utcnow()}
    )
    return requirements


@router.post("/{job_id}/resumes", status_code=status.HTTP_202_ACCEPTED)
async def upload_resumes(
    job_id: str,
    background: BackgroundTasks,
    files: list[UploadFile] = File(..., description="PDF resumes"),
    user: User = Depends(current_user),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    """Validate, create `processing` candidates, lock requirements and start background processing."""
    s = services.settings
    job = await owned_job(job_id, user, services)
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose at least one PDF.")
    if len(files) > s.max_files_per_upload:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Upload at most {s.max_files_per_upload} files at a time.")
    existing = await services.store.list_candidates(job_id)
    if len(existing) + len(files) > s.max_candidates_per_job:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A job can have at most {s.max_candidates_per_job} candidates "
            f"({len(existing)} already uploaded).",
        )

    max_bytes = s.max_file_mb * 1024 * 1024
    items: list[tuple[str, bytes]] = []
    bad: dict[int, list[str]] = {}
    for f in files:
        try:
            items.append((upload_name(f), await read_pdf(f, max_bytes)))
        except BadUpload as e:
            bad.setdefault(e.code, []).append(e.name)
    # All-or-nothing: the recruiter fixes the batch and uploads it again.
    for code in (status.HTTP_413_CONTENT_TOO_LARGE, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE):
        if code in bad:
            raise upload_error(code, bad[code], s.max_file_mb)

    # Candidates are created and processed in shuffled order, so creation order doesn't follow
    # file order (file names often contain the candidate's name).
    order = list(range(len(items)))
    random.shuffle(order)
    now = utcnow()
    taken = {c.get("anonId") for c in existing}
    docs = []
    for i in order:
        anon = new_anon_id(taken)
        taken.add(anon)
        docs.append({
            "anonId": anon,
            "fileName": items[i][0],
            "status": "processing",
            "error": None,
            "profile": None,
            "evaluation": None,
            "score": None,
            "photoPresent": False,
            "redactionCount": 0,
            "revealed": None,
            "revealedAt": None,
            "revealedBy": None,
            "createdAt": now,
            "updatedAt": now,
        })
    n = len(docs)
    ids = await services.store.add_candidates(
        job_id, docs, {"requirementsLocked": True, "updatedAt": now}, {"total": n, "processing": n}
    )
    background.add_task(
        run_batch, services, {**job, "requirementsLocked": True}, [(cid, items[i][1]) for cid, i in zip(ids, order)]
    )
    log.info("job %s: %d resume(s) queued", job_id, n)
    # In upload order, so the uploading tab can offer retry for a failed file without storing it.
    by_file = [""] * n
    for cid, i in zip(ids, order):
        by_file[i] = cid
    return {"candidate_ids": by_file}


@router.patch("/{job_id}/weights")
async def update_weights(
    job_id: str,
    body: Weights,
    user: User = Depends(current_user),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    """Recompute every score's total with new weights; no LLM calls (P1, SPEC §8)."""
    await owned_job(job_id, user, services)
    candidates = await services.store.list_candidates(job_id)
    if any(c.get("status") == "processing" for c in candidates):
        # In-flight candidates are scored with the weights from upload time.
        raise HTTPException(status.HTTP_409_CONFLICT, "Wait until all resumes have finished processing.")
    now = utcnow()
    updates = {}
    for c in candidates:
        if c.get("score"):
            s = ScoreBreakdown.model_validate(c["score"])
            total = scoring.combine(s.must_have, s.nice_to_have, s.semantic, body)
            updates[c["id"]] = {"score": s.model_copy(update={"total": total}).model_dump(), "updatedAt": now}
    await services.store.update_candidates(job_id, updates, {"weights": body.model_dump(), "updatedAt": now})
    return {"weights": body.model_dump(), "rescored": len(updates)}


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str, user: User = Depends(current_user), services: Services = Depends(get_services)
) -> Response:
    """Delete the job with its candidates and private identity docs (P1, SPEC §8)."""
    await owned_job(job_id, user, services)
    await services.store.delete_job(job_id)
    log.info("job %s deleted", job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
