"""Pydantic schemas (SPEC §6.1). Also used as Gemini structured-output schemas."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

DEFAULT_TAG_WEIGHT = 3
MIN_TAG_WEIGHT, MAX_TAG_WEIGHT = 1, 5


class RequirementBase(BaseModel):
    id: str                      # "m1", "m2", ... / "n1", ...
    text: str                    # e.g. "3+ years of Python in production"
    kind: Literal["skill", "experience", "education", "certification", "other"]


class Requirement(RequirementBase):
    """One screening tag. `weight` (1–5) is its importance within its group (must-have or
    nice-to-have); it is set by the recruiter and never sent to the evaluator."""

    weight: int = Field(default=DEFAULT_TAG_WEIGHT, ge=MIN_TAG_WEIGHT, le=MAX_TAG_WEIGHT)


class JobRequirementsDraft(BaseModel):
    """Gemini's output schema for JD parsing: tags without weights."""

    role_title: str
    must_have: list[RequirementBase]     # 3–8 items
    nice_to_have: list[RequirementBase]  # 0–8 items
    min_years_experience: float | None
    education_requirement: str | None


class JobRequirements(JobRequirementsDraft):
    must_have: list[Requirement]
    nice_to_have: list[Requirement]


class Identity(BaseModel):               # NEVER sent to the evaluator or the embedding
    name: str | None
    email: str | None
    phone: str | None
    links: list[str]
    location: str | None
    # age/DOB and gender are deliberately NOT fields here: they are detected only so they can be stripped


class Education(BaseModel):
    institution: str | None
    degree: str | None
    field: str | None
    grade: str | None            # as written: "8.7/10 CGPA", "First Class", "78%"
    start_year: int | None
    end_year: int | None


class Experience(BaseModel):
    title: str | None
    organisation: str | None
    start: str | None            # "2021-06" or "2021"
    end: str | None              # or "present"
    months: int | None
    summary: str                 # neutral, third person, no identity


class Project(BaseModel):
    title: str
    summary: str


class BlindProfile(BaseModel):
    headline: str                # one neutral line, e.g. "Backend engineer, 4 yrs, Python/Go"
    education: list[Education]
    experience: list[Experience]
    total_experience_months: int | None
    skills: list[str]
    projects: list[Project]
    certifications: list[str]


class ParsedResume(BaseModel):
    identity: Identity
    profile: BlindProfile
    photo_present: bool


class RequirementVerdict(BaseModel):
    req_id: str
    verdict: Literal["met", "partial", "not_met"]
    evidence: str                # at most 20 words, refers to profile content; "" if not_met


class CandidateEvaluation(BaseModel):
    must_have: list[RequirementVerdict]
    nice_to_have: list[RequirementVerdict]
    strengths: list[str]         # at most 3
    gaps: list[str]              # at most 3
    summary: str                 # 2 sentences, no identity, no demographics


class TagJudgement(BaseModel):
    """Demo builder only: one profile judged against the whole tag library in one call."""

    verdicts: list[RequirementVerdict]
    summary: str                 # 2 neutral sentences describing the profile, not a fit for one role


class ScoreBreakdown(BaseModel):
    must_have: float             # 0–1
    nice_to_have: float          # 0–1
    semantic: float              # 0–1 (rescaled cosine)
    semantic_raw: float          # raw cosine, kept for calibration
    total: float                 # 0–100
    missing_must_have: bool


class Weights(BaseModel):
    """Score weights, stored on the job as `weights` (SPEC §6.2). Must sum to 1."""

    must: float = 0.5
    nice: float = 0.2
    semantic: float = 0.3

    @model_validator(mode="after")
    def _check(self) -> "Weights":
        values = (self.must, self.nice, self.semantic)
        if any(v < 0 or v > 1 for v in values):
            raise ValueError("each weight must be between 0 and 1")
        if abs(sum(values) - 1.0) > 1e-6:
            raise ValueError(f"weights must sum to 1 (got {sum(values):.4f})")
        return self


class WeightsUpdate(Weights):
    """PATCH /weights body: the group weights plus, optionally, new tag weights by requirement ID."""

    tag_weights: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_tags(self) -> "WeightsUpdate":
        if any(not MIN_TAG_WEIGHT <= w <= MAX_TAG_WEIGHT for w in self.tag_weights.values()):
            raise ValueError(f"tag weights must be between {MIN_TAG_WEIGHT} and {MAX_TAG_WEIGHT}")
        return self

    def group_weights(self) -> Weights:
        return Weights(must=self.must, nice=self.nice, semantic=self.semantic)
