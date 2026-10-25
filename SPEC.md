
# SPEC — FairScreen (working title): Blind Resume Screener

> Spec-driven development: this file is the source of truth. Claude Code implements against it, one phase of PLAN.md at a time. Any change to the blind-screening policy (§5), the scoring formula (§7.4) or the data model (§6) must be confirmed with the owner first.

## 1. Overview

**One-liner.** A recruiter pastes a job description and uploads a batch of resume PDFs. FairScreen returns a ranked, **blind** shortlist: each candidate gets a score, a requirement-by-requirement checklist with evidence, and a two-sentence explanation, without the recruiter seeing names or other identity details until they shortlist someone.

**Users.** Recruiters and hiring managers at small companies screening 10–50 applicants per role.

**Problem.** Manual screening is slow, inconsistent, and exposed to bias from names, gender, age and location. Keyword-matching ATS tools miss candidates who describe the same skill differently.

**Positioning for the course.** Job-oriented product built entirely on pretrained models through APIs, with **no model training**. The Kaggle resume dataset is used for sample data and evaluation only.

## 2. Goals and non-goals

**Goals (MVP)**
- G1. Create a job from a pasted JD; the AI extracts structured requirements, which the recruiter can review and edit before screening starts.
- G2. Upload up to 20 PDF resumes at once; each is parsed, anonymised, evaluated and scored in the background, with live progress.
- G3. Ranked blind shortlist, plus a candidate detail view with a requirement checklist, evidence, a score breakdown and an explanation.
- G4. Shortlist and reject actions; **reveal identity only after shortlisting**, logged with timestamp and user.
- G5. Google sign-in; jobs and results saved per recruiter.
- G6. "Try the demo" mode that works with no login and no API calls.
- G7. CSV export of the shortlist.
- G8. Offline evaluation script with precision@k and an ablation, using the Kaggle dataset.

**Non-goals**
- Training or fine-tuning any model.
- DOCX or image resumes (PDF only).
- Emailing candidates, ATS integrations, multi-user teams, billing.
- Storing raw resume files anywhere.

## 3. Stack and services

| Layer | Choice |
|---|---|
| Frontend | React + Vite + TypeScript, hosted on **Firebase Hosting** |
| Styling | Tailwind CSS (unless the chess repo's conventions say otherwise) |
| Backend | Python 3.11 + **FastAPI**, hosted on **Render** (free web service) |
| Auth | **Firebase Authentication**, Google sign-in |
| Database | **Cloud Firestore** (no Firebase Storage) |
| LLM + embeddings | **Gemini API** via the `google-genai` Python SDK (free tier) |
| Repo | GitHub, monorepo (`frontend/`, `backend/`) |

**Gemini models are configured by environment variable, never hard-coded.** Pick the IDs from the free-tier list in Google AI Studio:
- `GEMINI_PARSE_MODEL`: a Flash-Lite model, used for resume and JD parsing (cheap, high volume).
- `GEMINI_EVAL_MODEL`: a Flash model, used for requirement evaluation (needs better judgement).
- `GEMINI_EMBED_MODEL`: default `gemini-embedding-001`, with `output_dimensionality=768`.

Before writing Gemini code, check the current `google-genai` docs for: PDF input via `types.Part.from_bytes(..., mime_type="application/pdf")`, structured output via `response_mime_type="application/json"` + `response_schema=<Pydantic model>`, async calls via `client.aio`, and `embed_content` with `task_type="SEMANTIC_SIMILARITY"`.

## 4. Architecture

```
Browser (React, Firebase Hosting)
  │  Firebase Auth (Google) → ID token
  │  Firestore onSnapshot (read-only: jobs, candidates)  ◄── live progress
  │
  └─ HTTPS + Bearer ID token ──► FastAPI (Render)
                                   ├─ verifies token (firebase-admin)
                                   ├─ Gemini: parse JD, parse resume PDF, evaluate, embed
                                   ├─ blind.py: redaction safety net
                                   ├─ scoring.py: deterministic score
                                   └─ writes Firestore (admin SDK)
```

- **All writes go through the backend.** The client only reads Firestore, and security rules enforce this.
- Resume PDFs are processed **in memory** and discarded. Render's filesystem is ephemeral, and not storing raw resumes is also a privacy feature.
- Resume processing runs as FastAPI background tasks. Progress is written to Firestore, and the UI listens in real time.

## 5. Blind-screening policy

The scorer (the evaluation LLM call and the embedding) **only ever receives the blind profile**. The recruiter sees the blind profile until they shortlist and then reveal.

| Field | While screening | After reveal (shortlisted only) | Stored? |
|---|---|---|---|
| Name | Hidden; shown as an anon ID like `CAND-7F3A` | Shown | Yes, in the private identity doc |
| Email, phone | Hidden | Shown | Yes, in the private identity doc |
| Profile links (LinkedIn, GitHub, portfolio) | Hidden | Shown | Yes, in the private identity doc |
| Photo | Hidden (only a "photo present" flag is used to warn) | Not shown | No (never extracted) |
| Location / address / hometown | Hidden | Shown (needed for logistics) | Yes, in the private identity doc |
| Age / date of birth | Hidden | **Never shown** | **No** (data minimisation) |
| Gender indicators (pronouns, Mr/Ms, gender field) | Hidden; pronouns are neutralised in all text | **Never shown** | **No** |
| College / university, degree, field, grade (CGPA/%), graduation year | **Visible** | Visible | Yes |
| Employers, job titles, dates, durations | Visible | Visible | Yes |
| Skills, projects, certifications | Visible | Visible | Yes |

Notes:
- **College is visible but not scored.** The score never uses institution name or prestige. Education counts only when the JD states an education requirement (e.g. "B.Tech in CS or equivalent"), and then by degree and field, not by institution.
- Graduation year is visible as part of academics, as the owner chose. This is a known age proxy; mention it as a trade-off in the README.
- Once revealed, a candidate stays revealed. Un-shortlisting does not hide them again.

**Redaction is done in two layers:**
1. **Prompt layer.** The parse prompt puts identity fields only in the `identity` block, and writes every profile text field in neutral third person, with no names, pronouns, locations or contact details.
2. **Safety-net layer (`blind.py`, deterministic, unit-tested).** After parsing, scan every string in the blind profile and:
   - remove email and phone patterns, and URLs;
   - remove name tokens (first, last and full name from `identity`, tokens longer than 2 characters, case-insensitive, whole word);
   - remove the identity location strings;
   - replace gendered pronouns and titles (he, she, him, her, his, hers, himself, herself, Mr., Mrs., Ms., Miss) with neutral forms (they, them, their, theirs, themselves, or drop the title).

   Every replacement is counted and stored as `redaction_count`, for transparency and testing.

## 6. Data model

### 6.1 Pydantic schemas (backend `app/models.py`)

```python
class Requirement(BaseModel):
    id: str                      # "m1", "m2", ... / "n1", ...
    text: str                    # e.g. "3+ years of Python in production"
    kind: Literal["skill", "experience", "education", "certification", "other"]

class JobRequirements(BaseModel):
    role_title: str
    must_have: list[Requirement]         # 3–8 items
    nice_to_have: list[Requirement]      # 0–8 items
    min_years_experience: float | None
    education_requirement: str | None

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

class ScoreBreakdown(BaseModel):
    must_have: float             # 0–1
    nice_to_have: float          # 0–1
    semantic: float              # 0–1 (rescaled cosine)
    semantic_raw: float          # raw cosine, kept for calibration
    total: float                 # 0–100
    missing_must_have: bool
```

### 6.2 Firestore layout

```
jobs/{jobId}
  ownerUid, title, jdText, requirements: JobRequirements,
  requirementsLocked: bool,          # true after the first upload
  weights: {must: 0.5, nice: 0.2, semantic: 0.3},
  jdEmbedding: number[768],
  counts: {total, processing, scored, failed, shortlisted},
  createdAt, updatedAt

jobs/{jobId}/candidates/{candId}
  anonId: "CAND-7F3A",
  fileName: string,                  # never shown in the UI (file names often contain the candidate's name); included in CSV export only after reveal
  status: "processing" | "scored" | "failed" | "shortlisted" | "rejected",
  error: string | null,
  profile: BlindProfile | null,
  evaluation: CandidateEvaluation | null,
  score: ScoreBreakdown | null,
  photoPresent: bool,
  redactionCount: int,
  revealed: {name, email, phone, links, location} | null,
  revealedAt, revealedBy,
  createdAt, updatedAt

jobs/{jobId}/candidates/{candId}/private/identity
  Identity                           # backend-only, never client-readable
```

### 6.3 Firestore security rules (`firestore.rules`)

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /jobs/{jobId} {
      allow read: if request.auth != null && resource.data.ownerUid == request.auth.uid;
      allow write: if false;
      match /candidates/{candId} {
        allow read: if request.auth != null
          && get(/databases/$(database)/documents/jobs/$(jobId)).data.ownerUid == request.auth.uid;
        allow write: if false;
        match /private/{docId} {
          allow read, write: if false;
        }
      }
    }
  }
}
```

The admin SDK on the backend bypasses these rules.

## 7. AI pipeline

### 7.1 Job creation (one call plus one embedding)
1. `parse_jd(jd_text)` → `JobRequirements` (`GEMINI_PARSE_MODEL`, structured output).
2. `embed(jd_embedding_text)`, where the text is the role title, must-haves and nice-to-haves joined. Stored on the job.

### 7.2 Per resume (two calls plus one embedding), run in the background
1. **Parse:** `parse_resume(pdf_bytes)` → `ParsedResume` (`GEMINI_PARSE_MODEL`, PDF sent inline, structured output).
2. **Redact:** `blind.redact(parsed)` → (blind `BlindProfile`, `Identity`, `redaction_count`).
3. **Evaluate:** `evaluate(blind_profile_json, requirements)` → `CandidateEvaluation` (`GEMINI_EVAL_MODEL`). **Input is the blind profile JSON and the requirements only.**
4. **Embed:** `embed(profile_text)`, where `profile_text` is the headline, skills, experience titles and summaries, project summaries, and degree and field, truncated to about 6,000 characters (the embedding model's input limit is about 2,048 tokens).
5. **Score:** `scoring.score(evaluation, jd_embedding, profile_embedding, weights)` → `ScoreBreakdown`.
6. Write the candidate doc (`status="scored"`) and the private identity doc. Update `counts` on the job.

Parsing is JD-independent, so parse results are cached by the SHA-256 of the PDF (in memory on the server; on disk under `.cache/` for scripts and eval).

### 7.3 Prompt rules
- **Parse resume:** extract only what is present, using `null` or empty when absent, and never invent. Put name, email, phone, URLs and location **only** in `identity`. Do not output age, DOB or gender anywhere. Write every summary and the headline in neutral third person with no names, pronouns, locations or contact details. Keep institution names, degrees, grades, graduation years, employers, titles and dates exactly as written.
- **Parse JD:** 3–8 must-haves, 0–8 nice-to-haves, each a single checkable requirement. Do not add requirements that aren't in the JD. Do not turn soft wording ("good communication") into must-haves unless the JD marks it as required.
- **Evaluate:** "You are screening an anonymised candidate profile against the job's requirements." `met` means clear evidence, `partial` means related or weaker evidence, and `not_met` means no evidence. Evidence must point to profile content. Judge only the listed requirements. Do not use institution prestige, and do not infer demographics. Two-sentence summary, neutral.
- Temperature 0 for parsing; temperature 0–0.2 for evaluation.

### 7.4 Scoring (deterministic, in Python)

```
must     = (met + 0.5 * partial) / n_must              (1.0 if n_must == 0)
nice     = (met + 0.5 * partial) / n_nice              (1.0 if n_nice == 0)
semantic = clip((cosine - LO) / (HI - LO), 0, 1)       LO=0.55, HI=0.85 defaults, calibrated in Phase 5
total    = 100 * (w_must * must + w_nice * nice + w_sem * semantic)
missing_must_have = any must-have verdict == "not_met"   → shows a badge; never auto-rejects
```

The LLM judges requirements, but the score is computed in code. That makes it reproducible, explainable, and adjustable by weight without new API calls.

### 7.5 Rate limits and reliability
- `asyncio.Semaphore(GEMINI_CONCURRENCY)`, default 2.
- Retry on 429 / `RESOURCE_EXHAUSTED` / 5xx with exponential backoff and jitter (use `tenacity`, max 5 attempts, capped at about 60 s). After that, set `status="failed"` with a readable `error`.
- On startup, mark candidates stuck in `processing` for more than 10 minutes as `failed` (Render can restart the free instance at any time).
- Limits: PDF only, ≤ 5 MB, ≤ 20 files per upload, ≤ 50 candidates per job. Reject others with clear messages.

## 8. Backend API (FastAPI)

All routes except `/health` require `Authorization: Bearer <Firebase ID token>`, and every job route checks `ownerUid`.

| Method | Path | Body | Does |
|---|---|---|---|
| GET | `/health` | | `{"ok": true}`; used by the frontend to wake Render |
| POST | `/jobs` | `{title, jd_text}` | Parse the JD, embed it, create the job; returns the job |
| PATCH | `/jobs/{jobId}/requirements` | `JobRequirements` | Edit requirements (409 if locked); re-embeds the JD |
| PATCH | `/jobs/{jobId}/weights` | `{must, nice, semantic}` (sum to 1) | Recompute `score` for all scored candidates (no LLM calls) — **P1** |
| POST | `/jobs/{jobId}/resumes` | multipart `files[]` | Validate, create `processing` candidate docs, start background tasks, lock requirements; returns candidate IDs |
| POST | `/jobs/{jobId}/candidates/{candId}/status` | `{status: "shortlisted" \| "rejected" \| "scored"}` | Change the recruiter decision |
| POST | `/jobs/{jobId}/candidates/{candId}/reveal` | | 403 unless shortlisted; copy identity into `revealed`, set `revealedAt` and `revealedBy`; return identity |
| POST | `/jobs/{jobId}/candidates/{candId}/retry` | | Re-run a failed candidate — **P1** (needs the PDF re-uploaded, since PDFs are not stored) |
| DELETE | `/jobs/{jobId}` | | Delete the job and its subcollections — **P1** |

Reads (job list, job, candidates) go straight from the client to Firestore with real-time listeners. There are no GET endpoints for them.

CORS: `ALLOWED_ORIGINS` (the Firebase Hosting URL and `http://localhost:5173`).

## 9. Frontend

**Routes**
- `/`: landing page with the product pitch (problem, how it works in 3 steps, the blind-screening promise), and two buttons, **Try the demo** and **Sign in with Google**.
- `/demo`: read-only demo job loaded from `public/demo/demo_job.json`. No login, no API calls. All UI below works except uploads; reveal works on demo data.
- `/jobs`: the recruiter's jobs (title, created date, candidate counts) plus **New job**.
- `/jobs/new`: title and JD textarea → **Extract requirements** → editable must-have and nice-to-have lists → **Save job**.
- `/jobs/:jobId`: the main screen:
  - Header: job title, requirement chips, counts.
  - Upload dropzone (multi-file, PDF only), with per-file progress (`processing` → `scored`/`failed`) via Firestore listeners.
  - **Ranked table:** rank, anon ID, score bar (0–100), must-have coverage (e.g. "4/5"), "missing must-have" badge, top 2 matched skills, top gap, institution, degree, grade, status chip. Sortable by score. Filter by status.
  - Weight sliders with a live re-rank — **P1**.
  - **Export CSV**: anon ID, score, breakdown, coverage, institution, degree, status, and name/email **only for revealed candidates**.
- **Candidate drawer** (opens from a row):
  - Score breakdown (three bars plus total).
  - Requirement checklist: ✓ / ◐ / ✗ for each requirement, with evidence.
  - Strengths, gaps, two-sentence summary.
  - Blind profile: education (institution, degree, grade, years), experience timeline, skills, projects.
  - Indicators: "N identity details redacted", "Photo detected and hidden" (if applicable).
  - Actions: **Shortlist**, **Reject**, and **Reveal identity**. Reveal is disabled unless shortlisted, with a tooltip explaining why. It shows a confirm dialog ("This is logged"), then the identity card with "Revealed by you at <time>".

**Render cold start.** On app load, call `/health`. If it takes more than 2 s, show a banner: "Waking up the screening server (can take up to a minute)…".

**Look.** A clean SaaS look: neutral background, one accent colour, cards, plenty of whitespace. It should look like a product, not a notebook.

## 10. Demo mode

`backend/scripts/build_demo.py` runs the real pipeline (with the cache) on a sample JD and about 10 sample resumes, and writes `frontend/public/demo/demo_job.json`, with the same shape as the Firestore job plus candidates (including `revealed` identity for the shortlisted ones). The demo therefore shows real model output, never fails in the viva, and costs zero API calls at view time.

If the Kaggle resumes have no names or contact details, add 3–4 **synthetic** resumes for fictional people so blind mode and reveal can be demonstrated. Label them synthetic in the README.

## 11. Evaluation (offline, `backend/eval/`)

**Data.** Kaggle "Resume Dataset" by Snehaan Bhawal: about 2,400 resumes in 24 job categories, with PDFs in one folder per category. Raw data goes in `backend/eval/data/`, which is gitignored.

**Setup.**
- Choose 3 target categories (e.g. Information Technology, Finance, HR; check the exact folder names), and write one realistic JD for each (`eval/jds/*.txt`).
- Pool of 30 resumes: 8 from each target category and 6 from other categories. The pool is fixed with a random seed, and the IDs are saved to `eval/pool.json`.
- Parse each resume once (cached). For each JD, evaluate and score all 30. That's about 30 parse calls, 90 evaluation calls and 33 embeddings, so check the free-tier limits in AI Studio and run it slowly.
- A resume counts as relevant to a JD if its category matches.

**Metrics** (for each JD, then averaged): precision@5, precision@10, nDCG@10.

**Ablation.** Rank by (a) semantic only, (b) LLM requirements only (`must`/`nice` with weights renormalised), and (c) the combined score. Report a table in the README.

**Calibration.** Use the raw cosine distribution from the pool to set `LO`/`HI` in §7.4 (e.g. the 10th and 90th percentiles), and record the values.

**Honest caveat for the README.** Category labels are only a proxy for relevance; an "IT" resume is not necessarily a fit for a specific IT JD.

Outputs: `eval/results/metrics.json`, `eval/results/ablation.md`, and one chart (precision@k bars), all referenced in the README.

## 12. Configuration

**Backend (Render env vars)**
```
GEMINI_API_KEY=
GEMINI_PARSE_MODEL=        # Flash-Lite ID from AI Studio
GEMINI_EVAL_MODEL=         # Flash ID from AI Studio
GEMINI_EMBED_MODEL=gemini-embedding-001
GEMINI_CONCURRENCY=2
FIREBASE_SERVICE_ACCOUNT_B64=   # base64 of the service-account JSON
ALLOWED_ORIGINS=https://<project>.web.app,http://localhost:5173
MAX_FILES_PER_UPLOAD=20
MAX_FILE_MB=5
MAX_CANDIDATES_PER_JOB=50
```

**Frontend (`.env`)**
```
VITE_API_URL=https://<service>.onrender.com
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=
VITE_FIREBASE_PROJECT_ID=
VITE_FIREBASE_APP_ID=
```

Never commit secrets. Provide `.env.example` files.

## 13. Privacy and security
- Raw PDFs are never stored, and they are never logged.
- Do not log identity fields. Log candidate IDs only.
- Identity is in a backend-only document; reveal is gated on shortlisting and logged.
- Age, DOB and gender are never stored.
- **Free-tier data note (README):** on the Gemini free tier, Google may use prompts and responses to improve its products. Demo and eval use public or synthetic resumes only. A production deployment would use the paid tier, which excludes this.

## 14. Testing
- `tests/test_blind.py`: redacts names (full, first and last; case-insensitive), emails, phones, URLs and location strings; neutralises pronouns and titles; **keeps** institution, degree, grade, graduation year and employer; `redaction_count` is correct.
- `tests/test_scoring.py`: the formula, zero-requirement edge cases, cosine clipping, the `missing_must_have` flag, and that weights must sum to 1.
- `tests/test_api.py`: auth required, owner checks, reveal returns 403 unless shortlisted, upload validation (type, size, count). Gemini and Firestore are mocked.
- `scripts/run_local.py --jd jd.txt --resumes <folder>`: runs the real pipeline without Firestore and prints a ranked table (the Phase 1 checkpoint).

## 15. Repository layout

```
fairscreen/
  SPEC.md  PLAN.md  README.md  CLAUDE.md
  firebase.json  firestore.rules  .firebaserc
  backend/
    app/
      main.py  config.py  auth.py  models.py
      routers/jobs.py  routers/candidates.py
      services/gemini.py  services/pipeline.py  services/firestore.py
      blind.py  scoring.py  cache.py
    scripts/run_local.py  scripts/build_demo.py
    eval/run_eval.py  eval/jds/  eval/data/ (gitignored)  eval/results/
    tests/
    requirements.txt  .env.example
  frontend/
    src/pages/  src/components/  src/lib/firebase.ts  src/lib/api.ts  src/types.ts
    public/demo/demo_job.json
    .env.example
```

Backend dependencies: `fastapi`, `uvicorn[standard]`, `python-multipart`, `google-genai`, `firebase-admin`, `pydantic>=2`, `tenacity`, `numpy`, `pytest`, `httpx`.
Render start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (root directory `backend`).

## 16. MVP acceptance criteria
- [ ] Sign in with Google; create a job from a JD; requirements extracted and editable before the first upload.
- [ ] Upload 10 PDFs; all reach `scored` (or `failed` with a reason) with live progress; no page refresh needed.
- [ ] The ranked table shows no name, email, phone, link, location, age or gender anywhere, including file names.
- [ ] The candidate drawer shows the checklist with evidence, the score breakdown and the summary.
- [ ] Reveal is blocked until shortlisted; after reveal, the identity shows and `revealedAt` is set.
- [ ] CSV export works and includes identity only for revealed candidates.
- [ ] `/demo` works logged out, with the backend asleep.
- [ ] `pytest` passes; eval produces `metrics.json` and the ablation table.
- [ ] Deployed: frontend on Firebase Hosting, backend on Render, CORS correct.

## 17. Stretch (only after MVP, in order)
1. P1: weight sliders with live re-rank (`PATCH /weights`).
2. P1: retry failed candidates; delete job.
3. P2: AI-suggested interview questions per shortlisted candidate (one Gemini call, blind profile plus gaps).
4. P2: bias spot-check — run the evaluator on a few resumes with and without identity, and compare scores (README section).
