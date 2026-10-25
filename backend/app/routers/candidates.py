"""Candidate routes (SPEC §8): recruiter decision, identity reveal and retry."""

import logging
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.auth import User, current_user
from app.deps import Services, get_services
from app.routers.jobs import BadUpload, owned_job, read_pdf, upload_error, upload_name
from app.services.firestore import CandidateChange, Mutator, NotFoundError, utcnow
from app.services.pipeline import run_candidate

log = logging.getLogger("fairscreen.candidates")

router = APIRouter(prefix="/jobs/{job_id}/candidates", tags=["candidates"])

DECIDABLE = {"scored", "shortlisted", "rejected"}
REVEALED_FIELDS = ("name", "email", "phone", "links", "location")


class DecisionError(Exception):
    def __init__(self, code: int, detail: str):
        self.code, self.detail = code, detail


class StatusBody(BaseModel):
    status: Literal["shortlisted", "rejected", "scored"]


def change_status(new: str) -> Mutator:
    """Move between scored / shortlisted / rejected; keeps counts.shortlisted in step."""

    def fn(cand: dict[str, Any], _identity: dict[str, Any] | None) -> CandidateChange:
        current = cand.get("status")
        if current not in DECIDABLE:
            raise DecisionError(status.HTTP_409_CONFLICT, f"A {current} candidate can't be shortlisted or rejected.")
        if current == new:
            return CandidateChange(result=new)
        delta = (new == "shortlisted") - (current == "shortlisted")
        return CandidateChange(
            candidate={"status": new, "updatedAt": utcnow()},
            counts={"shortlisted": delta} if delta else {},
            result=new,
        )

    return fn


def reveal_identity(uid: str) -> Mutator:
    """403 unless shortlisted. Once revealed, always revealed: repeat calls return the
    first reveal (keeping its time and user), even after un-shortlisting (SPEC §5)."""

    def fn(cand: dict[str, Any], identity: dict[str, Any] | None) -> CandidateChange:
        if cand.get("revealed"):
            return CandidateChange(result=(cand["revealed"], cand.get("revealedAt"), cand.get("revealedBy"), False))
        if cand.get("status") != "shortlisted":
            raise DecisionError(status.HTTP_403_FORBIDDEN, "Shortlist the candidate before revealing their identity.")
        if identity is None:
            raise DecisionError(status.HTTP_409_CONFLICT, "No identity is stored for this candidate.")
        revealed = {k: identity.get(k) for k in REVEALED_FIELDS}
        now = utcnow()
        return CandidateChange(
            candidate={"revealed": revealed, "revealedAt": now, "revealedBy": uid, "updatedAt": now},
            result=(revealed, now, uid, True),
        )

    return fn


def restart_processing(file_name: str) -> Mutator:
    """failed → processing, for the same file only: fileName must keep naming the PDF that was processed."""

    def fn(cand: dict[str, Any], _identity: dict[str, Any] | None) -> CandidateChange:
        if cand.get("status") != "failed":
            raise DecisionError(status.HTTP_409_CONFLICT, "Only failed candidates can be retried.")
        if cand.get("fileName") and cand["fileName"] != file_name:
            raise DecisionError(status.HTTP_409_CONFLICT, "That isn't the file this candidate was created from.")
        return CandidateChange(
            candidate={"status": "processing", "error": None, "updatedAt": utcnow()},
            counts={"failed": -1, "processing": 1},
            result=True,
        )

    return fn


async def _mutate(services: Services, job_id: str, cand_id: str, fn: Mutator, read_identity: bool = False) -> Any:
    try:
        return await services.store.mutate_candidate(job_id, cand_id, fn, read_identity=read_identity)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found.") from None
    except DecisionError as e:
        raise HTTPException(e.code, e.detail) from None


@router.post("/{cand_id}/status")
async def set_status(
    job_id: str,
    cand_id: str,
    body: StatusBody,
    user: User = Depends(current_user),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    await owned_job(job_id, user, services)
    new = await _mutate(services, job_id, cand_id, change_status(body.status))
    return {"id": cand_id, "status": new}


@router.post("/{cand_id}/reveal")
async def reveal(
    job_id: str,
    cand_id: str,
    user: User = Depends(current_user),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    await owned_job(job_id, user, services)
    identity, revealed_at, revealed_by, first = await _mutate(
        services, job_id, cand_id, reveal_identity(user.uid), read_identity=True
    )
    if first:
        log.info("identity revealed: job %s candidate %s by user %s", job_id, cand_id, user.uid)
    return {"identity": identity, "revealedAt": revealed_at, "revealedBy": revealed_by}


@router.post("/{cand_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry(
    job_id: str,
    cand_id: str,
    background: BackgroundTasks,
    file: UploadFile = File(..., description="The same PDF again (PDFs are never stored)"),
    user: User = Depends(current_user),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    """Re-run a failed candidate with its PDF re-uploaded (P1, SPEC §8)."""
    job = await owned_job(job_id, user, services)
    try:
        data = await read_pdf(file, services.settings.max_file_mb * 1024 * 1024)
    except BadUpload as e:
        raise upload_error(e.code, [e.name], services.settings.max_file_mb) from None
    await _mutate(services, job_id, cand_id, restart_processing(upload_name(file)))
    background.add_task(run_candidate, services, job, cand_id, data)
    log.info("candidate %s/%s queued for retry", job_id, cand_id)
    return {"id": cand_id, "status": "processing"}
