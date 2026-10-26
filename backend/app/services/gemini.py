"""Gemini calls (SPEC §7): parse JD, parse resume PDF, evaluate, embed.

Concurrency is capped by a semaphore and transient failures (429 /
RESOURCE_EXHAUSTED / 5xx / network) are retried with exponential backoff and
jitter (SPEC §7.5). Model IDs come from the environment only.
"""

import asyncio
import json
import logging
import random
import re
import time
from datetime import date
from pathlib import Path
from typing import Any, TypeVar

import httpx
import numpy as np
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt

from app.blind import neutralise_pronouns
from app.cache import DiskCache, sha256_hex
from app.config import Settings
from app.models import (
    DEFAULT_TAG_WEIGHT,
    BlindProfile,
    CandidateEvaluation,
    JobRequirements,
    JobRequirementsDraft,
    ParsedResume,
    Requirement,
    RequirementVerdict,
    TagJudgement,
)

log = logging.getLogger("fairscreen.gemini")

# Bump when a prompt changes, so cached outputs made with the old prompt are not reused.
PARSE_PROMPT_VERSION = "resume-v1"
JD_PROMPT_VERSION = "jd-v1"
EVAL_PROMPT_VERSION = "eval-v1"
TAGS_PROMPT_VERSION = "tags-v1"

EMBED_DIM = 768
EMBED_MAX_CHARS = 6000  # the embedding model takes about 2,048 tokens
MAX_WAIT_S = 60.0
MAX_MUST = 8
MAX_NICE = 8
MAX_EVIDENCE_WORDS = 20
VERDICT_FIELDS = {"id", "text", "kind"}  # what the evaluator sees of a requirement

T = TypeVar("T", bound=BaseModel)


def _today() -> str:
    return date.today().strftime("%Y-%m")


def _parse_resume_prompt() -> str:
    return f"""You extract structured data from a resume PDF for a blind (anonymised) screening tool.

Rules:
1. Extract only what is present in the resume. Use null or an empty list when something is absent. Never invent or guess.
2. Identity goes ONLY in the `identity` object: the candidate's name, email, phone, profile and portfolio URLs (LinkedIn, GitHub, personal site, etc.) and where they live (address, city, hometown, country of residence). Never repeat any of these anywhere in `profile`.
3. Never output age, date of birth, gender, marital status, nationality, religion or similar personal details anywhere.
4. Write `profile.headline`, every experience `summary` and every project `title` and `summary` in neutral third person, with no names, no pronouns (he, she, him, her, his, hers), no locations and no contact details. Prefer verb-first phrasing, e.g. "Built a payments API in Go serving 2M requests a day."
5. Keep institution names, degrees, fields of study, grades, graduation years, employers, job titles and dates exactly as written. `organisation` is the employer's name only, without its city or address.
6. Dates: "YYYY-MM" when the month is known, otherwise "YYYY"; "present" for ongoing roles. `months` is the length of the role in whole months (today is {_today()}), or null if the dates are missing. `total_experience_months` is total professional experience without double-counting overlapping roles, or null if it cannot be determined.
7. `experience` lists professional roles, including internships. `skills` lists concrete skills, tools and technologies as short items, without duplicates.
8. `headline` is one neutral line with the role, years of experience and core skills, e.g. "Backend engineer, 4 yrs, Python/Go".
9. `photo_present` is true only if the resume contains a photograph of a person."""


PARSE_JD_PROMPT = """You turn a job description (JD) into a checklist of requirements for screening resumes.

Rules:
1. `must_have`: 3 to 8 items that the JD states as required (e.g. "required", "must have", "minimum qualifications"). If the JD states fewer than 3 hard requirements, take the rest from its core responsibilities. If it states more than 8, merge closely related ones.
2. `nice_to_have`: 0 to 8 items the JD marks as preferred, a plus, a bonus or nice to have.
3. Each item is a single, checkable requirement: split compound ones ("Python and SQL" becomes two items). Keep the JD's specifics (years, tools, levels).
4. Do not add requirements that are not in the JD. Do not turn soft wording (e.g. "good communication") into a must-have unless the JD marks it as required.
5. Never include requirements about age, gender, nationality, religion, marital status, appearance or other protected characteristics, even if the JD mentions them.
6. `kind` is one of skill, experience, education, certification, other.
7. `id` is "m1", "m2", ... for must-haves and "n1", "n2", ... for nice-to-haves.
8. `role_title` is the job title. `min_years_experience` is the minimum total years of experience the JD asks for, or null. `education_requirement` is the JD's stated education requirement, or null."""


def _evaluate_prompt() -> str:
    return f"""You are screening an anonymised candidate profile against the job's requirements.

For EVERY listed requirement, return exactly one verdict with its `req_id`:
- "met": the profile shows clear evidence.
- "partial": related or weaker evidence (an adjacent tool, fewer years than asked, coursework rather than work).
- "not_met": no evidence in the profile.

Rules:
- `evidence`: at most 20 words pointing to specific profile content (a role, project, skill or education entry). Use an empty string when the verdict is "not_met".
- Judge only the listed requirements, and only from what the profile shows. Do not assume skills that are not shown.
- Do not use institution name or prestige. Education requirements are judged by degree and field only; equivalent degrees count.
- Do not infer or mention age, gender, ethnicity, nationality or any other demographic.
- For years-of-experience requirements, use the experience dates and months. Today is {_today()}.
- `strengths`: up to 3 short phrases. `gaps`: up to 3 short phrases about missing or weak requirements.
- `summary`: exactly two neutral sentences about fit for this role, with no names, no gendered pronouns and no demographics."""


def _judge_tags_prompt() -> str:
    return f"""You are checking an anonymised candidate profile against a library of screening tags.

For EVERY listed tag, return exactly one verdict with its `req_id`:
- "met": the profile shows clear evidence.
- "partial": related or weaker evidence (an adjacent tool, fewer years than asked, coursework rather than work).
- "not_met": no evidence in the profile.

Rules:
- `evidence`: at most 20 words pointing to specific profile content (a role, project, skill or education entry). Use an empty string when the verdict is "not_met".
- Judge each tag on its own, only from what the profile shows. Do not assume skills that are not shown.
- Do not use institution name or prestige. Education tags are judged by degree and field only; equivalent degrees count.
- Do not infer or mention age, gender, ethnicity, nationality or any other demographic.
- For years-of-experience tags, use the experience dates and months. Today is {_today()}.
- `summary`: exactly two neutral sentences describing the candidate's background (not their fit for one role), with no names, no gendered pronouns and no demographics."""


class GeminiError(RuntimeError):
    """A Gemini call failed for good. The message is safe to show in the UI."""


class RateLimiter:
    """Spaces call starts at least 60/rpm seconds apart, to stay under a free-tier RPM cap."""

    def __init__(self, rpm: int):
        self.interval = 60.0 / rpm if rpm > 0 else 0.0
        self._next = 0.0

    async def wait(self) -> None:
        if not self.interval:
            return
        now = time.monotonic()
        start = max(now, self._next)
        self._next = start + self.interval  # no await before this line, so it is atomic
        if start > now:
            await asyncio.sleep(start - now)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, errors.APIError):
        code = exc.code if isinstance(exc.code, int) else 0
        return code == 429 or exc.status == "RESOURCE_EXHAUSTED" or code >= 500
    return isinstance(exc, httpx.TransportError)


def _retry_delay_hint(exc: BaseException | None) -> float:
    """Seconds from the RetryInfo detail Gemini attaches to 429s, or 0."""
    if not isinstance(exc, errors.APIError) or not isinstance(exc.details, dict):
        return 0.0
    error = exc.details.get("error", exc.details)
    for detail in (error.get("details") if isinstance(error, dict) else None) or []:
        if isinstance(detail, dict) and str(detail.get("@type", "")).endswith("RetryInfo"):
            m = re.match(r"([\d.]+)s", str(detail.get("retryDelay", "")))
            if m:
                return float(m.group(1))
    return 0.0


def _wait(state: RetryCallState) -> float:
    exc = state.outcome.exception() if state.outcome else None
    backoff = 2.0 ** state.attempt_number  # 2, 4, 8, 16 s
    return min(MAX_WAIT_S, max(backoff, _retry_delay_hint(exc)) + random.uniform(0, 1.5))


def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    code = getattr(exc, "code", type(exc).__name__)
    wait = state.next_action.sleep if state.next_action else 0
    log.warning("Gemini call failed (%s); attempt %d, retrying in %.1fs", code, state.attempt_number, wait)


def _describe(exc: errors.APIError) -> str:
    code, msg = exc.code, (exc.message or "").strip()
    if code == 429 or exc.status == "RESOURCE_EXHAUSTED":
        return "Gemini rate limit or free-tier quota reached. Wait a minute and retry."
    if code in (401, 403) or "API key" in msg:
        return "Gemini rejected the API key. Check GEMINI_API_KEY."
    if code == 404:
        return f"Gemini model not found. Check the GEMINI_*_MODEL settings. ({msg})"
    if isinstance(code, int) and code >= 500:
        return f"Gemini service error ({code}). Try again later."
    return f"Gemini API error {code}: {msg}"


def _clip_words(text: str, limit: int) -> str:
    words = text.split()
    return text.strip() if len(words) <= limit else " ".join(words[:limit]) + "…"


def _neutral(text: str) -> str:
    return neutralise_pronouns(text)[0].strip()


def normalise_requirements(req: JobRequirements, reset_weights: bool = False) -> JobRequirements:
    """Enforce the SPEC's limits and give IDs m1.. / n1.. in order, whatever the model returned.
    Tag weights are kept, or set to the default with `reset_weights` (fresh AI extraction)."""

    def renumber(items: list[Requirement], prefix: str, limit: int) -> list[Requirement]:
        kept = [r for r in items if r.text.strip()][:limit]
        return [
            Requirement(
                id=f"{prefix}{i}",
                text=r.text.strip(),
                kind=r.kind,
                weight=DEFAULT_TAG_WEIGHT if reset_weights else r.weight,
            )
            for i, r in enumerate(kept, 1)
        ]

    return req.model_copy(
        update={
            "role_title": req.role_title.strip(),
            "must_have": renumber(req.must_have, "m", MAX_MUST),
            "nice_to_have": renumber(req.nice_to_have, "n", MAX_NICE),
        }
    )


def align_evaluation(ev: CandidateEvaluation, req: JobRequirements) -> CandidateEvaluation:
    """One verdict per requirement, in requirement order.

    A requirement the model skipped counts as not_met; verdicts for unknown IDs
    are dropped. Evidence is clipped to 20 words and emptied for not_met;
    strengths and gaps are capped at 3. Gendered pronouns are neutralised.
    """

    def align(verdicts: list[RequirementVerdict], reqs: list[Requirement]) -> list[RequirementVerdict]:
        by_id: dict[str, RequirementVerdict] = {}
        for v in verdicts:
            by_id.setdefault(v.req_id.strip(), v)
        out = []
        for r in reqs:
            v = by_id.get(r.id)
            if v is None:
                out.append(RequirementVerdict(req_id=r.id, verdict="not_met", evidence=""))
            else:
                evidence = "" if v.verdict == "not_met" else _clip_words(_neutral(v.evidence), MAX_EVIDENCE_WORDS)
                out.append(RequirementVerdict(req_id=r.id, verdict=v.verdict, evidence=evidence))
        return out

    return CandidateEvaluation(
        must_have=align(ev.must_have, req.must_have),
        nice_to_have=align(ev.nice_to_have, req.nice_to_have),
        strengths=[_neutral(s) for s in ev.strengths if s.strip()][:3],
        gaps=[_neutral(g) for g in ev.gaps if g.strip()][:3],
        summary=_neutral(ev.summary),
    )


class GeminiService:
    """Thin async wrapper over google-genai.

    `disk_cache_dir` (scripts and eval only) also caches JD parses,
    evaluations and embeddings on disk, to save free-tier quota and make long
    runs resumable. Resume parses are cached by app.cache.ParseCache.
    """

    def __init__(self, settings: Settings, client: genai.Client | None = None, disk_cache_dir: Path | None = None):
        settings.require_gemini()
        self.settings = settings
        self._client = client or genai.Client(api_key=settings.gemini_api_key)
        self._sem = asyncio.Semaphore(settings.gemini_concurrency)
        self._jd_cache = DiskCache(disk_cache_dir, "jd") if disk_cache_dir else None
        self._embed_cache = DiskCache(disk_cache_dir, "embed") if disk_cache_dir else None
        self._eval_cache = DiskCache(disk_cache_dir, "eval") if disk_cache_dir else None
        self._parse_limit = RateLimiter(settings.gemini_parse_rpm)
        self._eval_limit = RateLimiter(settings.gemini_eval_rpm)
        self._embed_limit = RateLimiter(settings.gemini_embed_rpm)

    @property
    def parse_cache_tag(self) -> str:
        return f"{self.settings.gemini_parse_model}|{PARSE_PROMPT_VERSION}"

    async def _call(self, fn: Any, limiter: RateLimiter, **kwargs: Any) -> Any:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.settings.gemini_max_attempts),
                wait=_wait,
                retry=retry_if_exception(_is_retryable),
                before_sleep=_log_retry,
                reraise=True,
            ):
                with attempt:
                    await limiter.wait()
                    async with self._sem:
                        return await fn(**kwargs)
        except errors.APIError as e:
            raise GeminiError(_describe(e)) from e
        except httpx.TransportError as e:
            raise GeminiError("Could not reach the Gemini API (network error). Try again.") from e
        raise AssertionError("unreachable")

    async def _generate(
        self, *, model: str, contents: Any, schema: type[T], system: str, temperature: float, limiter: RateLimiter
    ) -> T:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )
        resp = await self._call(
            self._client.aio.models.generate_content, limiter, model=model, contents=contents, config=config
        )
        if isinstance(resp.parsed, schema):
            return resp.parsed
        if resp.text:
            try:
                return schema.model_validate_json(resp.text)
            except ValidationError:
                pass
        reason = resp.candidates[0].finish_reason if resp.candidates else None
        if reason is None and resp.prompt_feedback:
            reason = resp.prompt_feedback.block_reason
        raise GeminiError(
            f"Gemini returned no usable {schema.__name__} (reason: {getattr(reason, 'name', reason) or 'unknown'})."
        )

    async def parse_jd(self, jd_text: str) -> JobRequirements:
        model = self.settings.gemini_parse_model
        key = sha256_hex(f"{model}|{JD_PROMPT_VERSION}|{jd_text}")
        if self._jd_cache and (hit := self._jd_cache.get(key)):
            return JobRequirements.model_validate(hit)
        draft = await self._generate(
            model=model,
            contents=f"Job description:\n\n{jd_text}",
            schema=JobRequirementsDraft,
            system=PARSE_JD_PROMPT,
            temperature=0.0,
            limiter=self._parse_limit,
        )
        req = normalise_requirements(JobRequirements.model_validate(draft.model_dump()), reset_weights=True)
        if self._jd_cache:
            self._jd_cache.put(key, req.model_dump())
        return req

    async def parse_resume(self, pdf_bytes: bytes) -> ParsedResume:
        """The PDF is sent inline and never written anywhere by this function."""
        return await self._generate(
            model=self.settings.gemini_parse_model,
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                "Extract this resume into the schema.",
            ],
            schema=ParsedResume,
            system=_parse_resume_prompt(),
            temperature=0.0,
            limiter=self._parse_limit,
        )

    async def evaluate(self, profile: BlindProfile, requirements: JobRequirements) -> CandidateEvaluation:
        """Takes a BlindProfile, which has no identity fields, so identity cannot reach the evaluator.
        Tag weights are left out: they change the score, never the verdicts."""
        reqs = {
            "role_title": requirements.role_title,
            "must_have": [r.model_dump(include=VERDICT_FIELDS) for r in requirements.must_have],
            "nice_to_have": [r.model_dump(include=VERDICT_FIELDS) for r in requirements.nice_to_have],
        }
        contents = (
            f"Job requirements (JSON):\n{json.dumps(reqs, indent=1, ensure_ascii=False)}\n\n"
            f"Anonymised candidate profile (JSON):\n{profile.model_dump_json(indent=1)}"
        )
        model = self.settings.gemini_eval_model
        key = sha256_hex(f"{model}|{EVAL_PROMPT_VERSION}|{contents}")
        if self._eval_cache and (hit := self._eval_cache.get(key)):
            return align_evaluation(CandidateEvaluation.model_validate(hit), requirements)
        ev = await self._generate(
            model=model,
            contents=contents,
            schema=CandidateEvaluation,
            system=_evaluate_prompt(),
            temperature=0.0,
            limiter=self._eval_limit,
        )
        if self._eval_cache:
            self._eval_cache.put(key, ev.model_dump())
        return align_evaluation(ev, requirements)

    async def judge_tags(self, profile: BlindProfile, tags: list[Requirement]) -> TagJudgement:
        """Demo builder only: one call judges the profile against every tag in the library.
        Verdicts come back aligned to `tags` (missing ones count as not_met)."""
        listed = [t.model_dump(include=VERDICT_FIELDS) for t in tags]
        contents = (
            f"Screening tags (JSON):\n{json.dumps(listed, indent=1, ensure_ascii=False)}\n\n"
            f"Anonymised candidate profile (JSON):\n{profile.model_dump_json(indent=1)}"
        )
        model = self.settings.gemini_eval_model
        key = sha256_hex(f"{model}|{TAGS_PROMPT_VERSION}|{contents}")
        if self._eval_cache and (hit := self._eval_cache.get(key)):
            out = TagJudgement.model_validate(hit)
        else:
            out = await self._generate(
                model=model,
                contents=contents,
                schema=TagJudgement,
                system=_judge_tags_prompt(),
                temperature=0.0,
                limiter=self._eval_limit,
            )
            if self._eval_cache:
                self._eval_cache.put(key, out.model_dump())
        aligned = align_evaluation(
            CandidateEvaluation(must_have=out.verdicts, nice_to_have=[], strengths=[], gaps=[], summary=out.summary),
            JobRequirements(role_title="tags", must_have=tags, nice_to_have=[],
                            min_years_experience=None, education_requirement=None),
        )
        return TagJudgement(verdicts=aligned.must_have, summary=aligned.summary)

    async def embed(self, text: str) -> list[float]:
        """Unit-length embedding (output_dimensionality=768 vectors are not normalised by the API)."""
        text = text[:EMBED_MAX_CHARS]
        model = self.settings.gemini_embed_model
        key = sha256_hex(f"{model}|{EMBED_DIM}|SEMANTIC_SIMILARITY|{text}")
        if self._embed_cache and (hit := self._embed_cache.get(key)):
            return hit
        resp = await self._call(
            self._client.aio.models.embed_content,
            self._embed_limit,
            model=model,
            contents=text,
            config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY", output_dimensionality=EMBED_DIM),
        )
        if not resp.embeddings or not resp.embeddings[0].values:
            raise GeminiError("Gemini returned an empty embedding.")
        v = np.asarray(resp.embeddings[0].values, dtype=float)
        norm = np.linalg.norm(v)
        values = (v / norm if norm else v).tolist()
        if self._embed_cache:
            self._embed_cache.put(key, values)
        return values
