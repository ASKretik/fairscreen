"""Firestore access (SPEC §6.2). Every write goes through the backend, with the admin SDK.

Business rules live in "mutators": plain functions that take the current
candidate (and optionally its private identity) and return a CandidateChange.
The store applies a change atomically (a Firestore transaction here, a lock in
the in-memory test store), so the rules are the same code in tests and prod.
"""

import base64
import binascii
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

import firebase_admin
from firebase_admin import credentials, firestore_async
from google.cloud.firestore_v1 import AsyncClient, FieldFilter, Increment
from google.cloud.firestore_v1.async_transaction import async_transactional

from app.config import ConfigError, Settings

log = logging.getLogger("fairscreen.firestore")

IDENTITY_DOC = "identity"


class NotFoundError(Exception):
    pass


@dataclass
class CandidateChange:
    candidate: dict[str, Any] = field(default_factory=dict)   # fields to update on the candidate doc
    counts: dict[str, int] = field(default_factory=dict)      # increments on the job's `counts`
    identity: dict[str, Any] | None = None                    # written to private/identity when set
    result: Any = None                                        # returned to the caller


# (candidate doc, identity doc or None) -> change. Must be pure: Firestore may retry it.
Mutator = Callable[[dict[str, Any], dict[str, Any] | None], CandidateChange]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Store(Protocol):
    async def create_job(self, data: dict[str, Any]) -> str: ...
    async def get_job(self, job_id: str) -> dict[str, Any] | None: ...
    async def update_job(self, job_id: str, fields: dict[str, Any]) -> None: ...
    async def list_candidates(self, job_id: str) -> list[dict[str, Any]]: ...
    async def add_candidates(
        self, job_id: str, docs: list[dict[str, Any]], job_fields: dict[str, Any], counts: dict[str, int]
    ) -> list[str]: ...
    async def mutate_candidate(self, job_id: str, cand_id: str, fn: Mutator, read_identity: bool = False) -> Any: ...
    async def processing_candidates(self) -> list[tuple[str, dict[str, Any]]]: ...
    async def update_candidates(self, job_id: str, updates: dict[str, dict[str, Any]], job_fields: dict[str, Any]) -> None: ...
    async def delete_job(self, job_id: str) -> None: ...


def _count_updates(counts: dict[str, int]) -> dict[str, Any]:
    return {f"counts.{k}": Increment(v) for k, v in counts.items() if v}


class FirestoreStore:
    def __init__(self, db: AsyncClient):
        self.db = db

    def _job(self, job_id: str):
        return self.db.collection("jobs").document(job_id)

    def _cand(self, job_id: str, cand_id: str):
        return self._job(job_id).collection("candidates").document(cand_id)

    async def create_job(self, data: dict[str, Any]) -> str:
        ref = self.db.collection("jobs").document()
        await ref.set(data)
        return ref.id

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        snap = await self._job(job_id).get()
        return {**snap.to_dict(), "id": snap.id} if snap.exists else None

    async def update_job(self, job_id: str, fields: dict[str, Any]) -> None:
        await self._job(job_id).update(fields)

    async def list_candidates(self, job_id: str) -> list[dict[str, Any]]:
        return [{**s.to_dict(), "id": s.id} async for s in self._job(job_id).collection("candidates").stream()]

    async def add_candidates(
        self, job_id: str, docs: list[dict[str, Any]], job_fields: dict[str, Any], counts: dict[str, int]
    ) -> list[str]:
        batch = self.db.batch()
        ids = []
        for doc in docs:
            ref = self._job(job_id).collection("candidates").document()
            batch.set(ref, doc)
            ids.append(ref.id)
        batch.update(self._job(job_id), {**job_fields, **_count_updates(counts)})
        await batch.commit()
        return ids

    async def mutate_candidate(self, job_id: str, cand_id: str, fn: Mutator, read_identity: bool = False) -> Any:
        cand_ref = self._cand(job_id, cand_id)
        ident_ref = cand_ref.collection("private").document(IDENTITY_DOC)
        job_ref = self._job(job_id)

        @async_transactional
        async def run(tx):
            snap = await cand_ref.get(transaction=tx)
            if not snap.exists:
                raise NotFoundError(cand_id)
            identity = None
            if read_identity:
                ident_snap = await ident_ref.get(transaction=tx)
                identity = ident_snap.to_dict() if ident_snap.exists else None
            change = fn(snap.to_dict(), identity)
            if change.candidate:
                tx.update(cand_ref, change.candidate)
            if change.identity is not None:
                tx.set(ident_ref, change.identity)
            if change.counts:
                tx.update(job_ref, _count_updates(change.counts))
            return change.result

        return await run(self.db.transaction())

    async def update_candidates(self, job_id: str, updates: dict[str, dict[str, Any]], job_fields: dict[str, Any]) -> None:
        """One batch: per-candidate field updates plus job fields (≤ 51 writes, under Firestore's 500 limit)."""
        batch = self.db.batch()
        for cand_id, fields in updates.items():
            batch.update(self._cand(job_id, cand_id), fields)
        batch.update(self._job(job_id), job_fields)
        await batch.commit()

    async def delete_job(self, job_id: str) -> None:
        """The job, its candidates and their private identity docs."""
        await self.db.recursive_delete(self._job(job_id))

    async def processing_candidates(self) -> list[tuple[str, dict[str, Any]]]:
        # Two single-field queries rather than a collection-group query, so no extra index is needed.
        out = []
        jobs = self.db.collection("jobs").where(filter=FieldFilter("counts.processing", ">", 0))
        async for job in jobs.stream():
            cands = job.reference.collection("candidates").where(filter=FieldFilter("status", "==", "processing"))
            async for c in cands.stream():
                out.append((job.id, {**c.to_dict(), "id": c.id}))
        return out


def init_firestore(settings: Settings) -> FirestoreStore:
    """Admin SDK from FIREBASE_SERVICE_ACCOUNT_B64 (base64 of the service-account JSON)."""
    if not settings.firebase_service_account_b64:
        raise ConfigError("Missing FIREBASE_SERVICE_ACCOUNT_B64.")
    try:
        info = json.loads(base64.b64decode(settings.firebase_service_account_b64))
    except (binascii.Error, ValueError) as e:
        raise ConfigError("FIREBASE_SERVICE_ACCOUNT_B64 is not base64-encoded service-account JSON.") from e
    try:
        app = firebase_admin.get_app()
    except ValueError:
        app = firebase_admin.initialize_app(credentials.Certificate(info))
    return FirestoreStore(firestore_async.client(app))
