# decisionsp4 — assumptions and decisions log (FairScreen)

Every assumption or design decision made during implementation that SPEC.md / PLAN.md does not settle.
Append new entries and keep the numbering. **⚠ CONFIRM** marks items that touch the blind-screening policy (SPEC §5), the data model (§6) or scoring (§7.4), or that could reasonably go the other way; please confirm or overrule them.

---

## Session 1: Sun 25 Oct 2026, Phase 0 (automatable parts) + Phase 1

### Scope and process
- **D1. "Start the implementation" = Phase 0 (what can be automated) + Phase 1 only.** PLAN.md and CLAUDE.md say to work one phase at a time and stop at the checkpoint; the schedule puts Phase 0 + 1 on Sun 25. No FastAPI routes, Firestore or frontend yet.
- **D2. Repo root = this `Project 4/` folder**, not a new `fairscreen/` subfolder, because SPEC.md and PLAN.md already live here. The GitHub repo can still be named `fairscreen`.
- **D3. No outward-facing Phase 0 steps were done**: no `git init`, GitHub repo, Firebase project, Gemini key or Kaggle download. These are yours (PLAN Phase 0).
- **D4. Assumptions are logged here instead of asked about one by one**, as you asked. I added a line to `CLAUDE.md` so future sessions keep appending to this file.
- **D5. `CLAUDE.md` = the plan's exact text + the decisions-log line + one "Local dev" line** with the test and run_local commands.

### Environment and dependencies
- **D6. Local venv uses Python 3.12** (`backend/.venv`) because 3.11 isn't installed on this machine. The code is 3.11-compatible (checked with `vermin`). Render must run 3.11 (set `PYTHON_VERSION` in Phase 4).
- **D7. `requirements.txt` pins exact versions, resolved for Python 3.11 on Linux** (what Render runs). numpy is pinned to **2.4.6** because numpy 2.5+ requires Python 3.12. The local venv uses the same pins.
- **D8. Added `python-dotenv`** (not in SPEC §15's list) to load `backend/.env` locally. On Render it does nothing. It is already a transitive dependency of `uvicorn[standard]`.
- **D9. `backend/pytest.ini` sets `pythonpath = .`**. Run the tests from `backend/` with `.venv/bin/python -m pytest`.

### Data model (SPEC §6)
- **D10. ⚠ CONFIRM: added a `Weights` Pydantic model** to `models.py` (must 0.5, nice 0.2, semantic 0.3; each 0–1; must sum to 1 within 1e-6). It mirrors the Firestore `weights` field without changing it, and is needed for the "weights must sum to 1" test.
- **D11. SPEC schemas are copied verbatim, with no default values**, so every field is *required* in Gemini's structured output (`X | None` becomes `nullable`). I checked that the installed SDK converts them cleanly (nullable, enums, field order kept).
- **D12. Limits the schema can't express are enforced in post-processing, not in Pydantic validators**: 3–8 must-haves, ≤ 8 nice-to-haves, evidence ≤ 20 words, ≤ 3 strengths/gaps. A slightly-off model reply is then trimmed instead of failing the whole candidate.

### Blind redaction, `blind.py` (SPEC §5, layer 2)
- **D13. ⚠ CONFIRM: removed text is replaced with a visible `[redacted]` marker** (adjacent ones merged), not deleted silently. Sentences stay readable, and the recruiter can see that something was removed.
- **D14. List items (skills, certifications) that become only `[redacted]` are dropped** (e.g. a skill that was just a GitHub URL).
- **D15. ⚠ CONFIRM: location handling.** The *full* identity location string (e.g. "Pune, Maharashtra") is removed from every field. Its *components* (city/state/country, split on `, / | ;`) are removed only from **free-text** fields (headline, experience summaries, project titles and summaries), not from structured fields (institution, employer, job title, skills, certifications). Reason: "College of Engineering Pune" or "University of Mumbai" would otherwise be mangled, and college is visible by policy. Trade-off: an employer written as "Infosys Pune" keeps the city.
- **D16. ⚠ CONFIRM: name tokens are applied literally as SPEC §5 says**: every string, whole word, case-insensitive, tokens longer than 2 characters, plus the parts of hyphenated names. Honorific tokens (Mr, Mrs, Ms, Miss, Dr, Prof) are skipped. Known side effect: if a name token is also an ordinary word, employer or institution word (e.g. a candidate named "Grant", or "Nehru" vs "Jawaharlal Nehru University"), it is redacted there too. A hyphen counts as a word boundary, so "smith-tools" loses "smith".
- **D17. Phones are detected by phone *shapes*, not "any long digit run"**: `+cc …`, `(555) 123-4567`, `555-123-4567`, `98765 43210`, 10–13-digit runs, **plus the identity's own number in any formatting**. This avoids eating year ranges ("2019-2023"), versions ("3.11") and grades ("8.7/10"). Trade-off: an unusual format (e.g. a 7-digit local number) that is *not* the identity's number could slip through.
- **D18. URLs**: anything with `http(s)://` or `www.`; bare domains only when followed by a path; known profile hosts (linkedin.com, github.com, etc.); and the identity's links with or without the scheme. The bare-domain TLD list deliberately leaves out `.net` and `.tech`, so "ASP.NET/C#" and "B.Tech/M.Tech" survive. A bare "mysite.com" with no path is caught only if it's in `identity.links`.
- **D19. Titles are matched case-sensitively**: "Mr./Mrs./Ms." (with the dot) anywhere; "Mr/Mrs/Ms/Miss" without a dot only before a capitalised word. This keeps the degree "MS" and the verb "miss".
- **D20. Pronouns**: only lowercase and Capitalised forms are replaced, so acronyms such as "HIS" (Hospital Information System) and "HE" are kept. "her" becomes "them" before a preposition, determiner or punctuation, and "their" otherwise. After a he/she swap, "they is/was/has/does" becomes "are/were/have/do"; other verbs are not fixed ("They codes" can happen).
- **D21. `redaction_count` counts every substitution**, including dropped titles and swapped pronouns (SPEC: "every replacement is counted"). The grammar fixes are not counted.
- **D22. Strings with nothing to redact are returned exactly as written.** Whitespace and punctuation tidy-up happens only on strings that changed.
- **D23. Extra safety net, not required by the spec:** the evaluator's output (evidence, strengths, gaps, summary) also gets pronoun neutralisation. It is not added to `redaction_count`.

### Prompts (SPEC §7.3)
- **D24. Parse-resume prompt additions**: `organisation` is the employer name *without* its city or address; project *titles* are also written neutrally; `months` uses today's year-month for "present"; experience includes internships; also forbids marital status, nationality and religion; `photo_present` only for a photograph of a person.
- **D25. Parse-JD prompt additions**: split compound requirements ("Python and SQL" becomes two items); with fewer than 3 hard requirements, take the rest from core responsibilities; with more than 8, merge related ones; **never include protected-characteristic requirements** (age, gender, nationality and so on), even if the JD lists them.
- **D26. Evaluator input** = role title + must/nice lists (id, text, kind) + blind-profile JSON, plus today's date for "present" durations. `min_years_experience` and `education_requirement` are not sent separately (they normally appear as listed requirements).
- **D27. Evaluation temperature = 0** (SPEC allows 0–0.2), for reproducibility.
- **D28. No `thinking_config` is set**: each model's default is used, because supported values differ between the model IDs you'll pick.
- **D29. JD requirement IDs are renumbered `m1..`/`n1..` in order** after parsing, whatever the model returned. Empty items are dropped and each list is capped at 8. If the model returns fewer than 3 must-haves they are kept as they are; the recruiter can edit them (Phase 2/3).
- **D30. Evaluation is aligned to the requirements**: exactly one verdict per requirement, in order. A requirement the model skipped becomes **`not_met`** (conservative); verdicts for unknown IDs are dropped; evidence is forced to "" for not_met and clipped to 20 words (with "…").
- **D31. Prompt version constants** (`resume-v1`, `jd-v1` in `services/gemini.py`). Bump them when a prompt changes, so cached outputs from the old prompt aren't reused.

### Gemini reliability (SPEC §7.5)
- **D32. Retry policy**: tenacity, 5 attempts, wait = max(2^n s, Gemini's own `retryDelay` hint) + 0–1.5 s jitter, capped at 60 s. Network transport errors are also retried, not just 429 / `RESOURCE_EXHAUSTED` / 5xx.
- **D33. The semaphore is held per attempt**, not during backoff sleeps.
- **D34. The SDK's built-in retry is left off** (its default), so retries aren't doubled.
- **D35. After the last retry, a `GeminiError` with a UI-safe message** is raised (rate limit / bad API key / model not found / service error). Invalid or empty structured output is **not** retried; it fails with the finish reason.
- **D36. Embeddings are L2-normalised** (the API doesn't normalise 768-dim output). Cosine is unaffected; this keeps stored vectors consistent.

### Caching (SPEC §7.2)
- **D37. The parse cache stores the *raw* parse (before redaction, so it includes identity)**, so a fix to `blind.py` applies without new API calls. On disk: `backend/.cache/parse/<pdf-sha256>.json` (gitignored). On the server: in memory, with an LRU cap of 1,000 entries.
- **D38. ⚠ CONFIRM: cache entries are tagged with the parse model + prompt version, and a mismatch counts as a miss.** SPEC says the key is the PDF's SHA-256; that is still the file name. The tag is added so that fixing the prompt at Checkpoint 1 actually re-parses.
- **D39. Scripts also cache JD parses and embeddings on disk** (`.cache/jd/`, `.cache/embed/`) to save free-tier quota. Evaluations are not cached in Phase 1 (eval resumability is Phase 5).

### Pipeline and scripts
- **D40. `services/pipeline.py` was created in Phase 1** (it is in the SPEC §15 layout). It holds the Firestore-free per-resume pipeline, so the API, `build_demo.py` and eval will reuse exactly what `run_local.py` runs.
- **D41. Embedding texts.** JD: role title + "Must have: …" + "Nice to have: …" lines. Profile: headline, skills, "title: summary" per role, project summaries, "degree in field". **No institution or employer names**, so prestige can't move the semantic score. Truncated to 6,000 characters.
- **D42. Anon IDs are random `CAND-XXXX` (4 hex digits), retried on collision** within a job, and not derived from the PDF.
- **D43. The pipeline checks PDFs by magic bytes (`%PDF-`)**; `run_local.py` applies the size limit. Full upload validation is Phase 2.
- **D44. `run_local.py` shows file names in its table**, because it is a local developer tool and you need to map results back to files. It never prints identity. Full results, including identity, go to `backend/.cache/run_local/<jd-name>.json` (gitignored). It uses the default weights; I added a `--limit N` option.

### Phase 0 artefacts
- **D45. ⚠ CONFIRM: drafted 3 eval JDs** in `backend/eval/jds/`: `information-technology.txt` (IT Systems Administrator), `finance.txt` (Financial Analyst), `hr.txt` (HR Generalist). They assume the Kaggle folder names `INFORMATION-TECHNOLOGY`, `FINANCE` and `HR`; check them after downloading. The IT JD is sysadmin/support rather than software engineering because, as far as I know, the Kaggle IT category is mostly IT support and IT management resumes. Each JD ends with a soft-skill sentence, to test the "don't promote soft wording to a must-have" rule.
- **D46. I expect the Kaggle resumes to contain no names or contact details**, so synthetic resumes will be needed in Phase 4. Check this at Phase 0 step 4.
- **D47. `.gitignore` covers** `.env*` (except `.env.example`), service-account JSON, `.venv`, `.cache/` (it holds identity from real resumes), `backend/eval/data/`, `node_modules`, `frontend/dist` and `.firebase`.
- **D48. `frontend/.env.example` was created now**, since Phase 0 step 2 asks you to fill in `frontend/.env`. The rest of `frontend/` is Phase 3.
- **D49. No Render config or `.python-version` yet** (Phase 4).

### Testing
- **D50. Tests beyond SPEC §14**: `tests/test_pipeline.py` (the evaluator and embedding never receive identity; parse caching; post-processing) and `tests/test_gemini.py` (retry, semaphore and error messages against a fake client). No test touches the network.

### Not yet verified
- The real Gemini calls have **not** been run: there is no API key or model IDs on this machine yet. `run_local.py` was dry-run end to end with a stubbed Gemini. Checkpoint 1's live run is the first real test of the prompts and structured output.

---

## Session 2: Sun 25 Oct 2026, Phase 2 (API, Firestore, auth)

Started at your request before Checkpoint 1 was verified live (D1's "stop at the checkpoint" was overridden by you).

### Structure
- **D51. Firestore access goes through a small `Store` interface.** Business rules (status changes, the reveal gate, finishing processing) are pure "mutator" functions that the store applies atomically: a Firestore transaction in `FirestoreStore`, a single synchronous step in the in-memory test store. **The real `FirestoreStore` has not been run against Firestore** (the emulator needs Java, which isn't installed); the tests run the same mutators against `tests/fakes.py::InMemoryStore`.
- **D52. Async Firestore client** (`firebase_admin.firestore_async`), so routes don't block the event loop.
- **D53. Added `app/deps.py`** (a `Services` container + `build_services`). It isn't in the SPEC §15 layout. `create_app(services)` lets tests inject fakes.
- **D54. The API refuses to start without both the Firebase and Gemini settings**, so a misconfigured Render deploy fails loudly instead of half-working.

### Data and counts
- **D55. ⚠ CONFIRM: `counts` semantics.** `total` = all uploaded; `processing` / `failed` = current status; **`scored` = successfully evaluated, and is not decremented when a candidate is later shortlisted or rejected**; `shortlisted` = currently shortlisted. There is no `rejected` count (not in §6.2). Upload progress = (scored + failed) / total.
- **D56. Timestamps are written as Python UTC datetimes**, not `SERVER_TIMESTAMP`, so fakes and tests behave the same. Firestore stores them as Timestamps.
- **D57. ⚠ CONFIRM: `fileName` sits in the client-readable candidate doc, as §6.2 specifies**, so it reaches the browser even though the UI never shows it. Moving it into `private/identity` would be stricter, but it changes §6.2.

### Endpoints
- **D58. Ownership failures return 404 "Job not found"**, the same as a job that doesn't exist, so job IDs can't be probed. (SPEC says "checks ownerUid" without naming a code.)
- **D59. `POST /jobs`**: title 1–200 characters, `jd_text` 50–20,000 characters. Returns 201 with the job, minus `jdEmbedding`. A Gemini failure gives 502 with the readable message.
- **D60. `PATCH /requirements`**: 1–8 must-haves (the spec's minimum of 3 applies to AI extraction; a recruiter may want fewer), ≤ 8 nice-to-haves, a non-empty role title, ≤ 300 characters each, IDs renumbered. Anything else is 422; locked is 409.
- **D61. Upload**: the multipart field is named `files` (SPEC writes `files[]`). Validation is all-or-nothing: too many files → 400; the job would exceed 50 → 409; any file over `MAX_FILE_MB` → 413; any non-PDF → 415. A PDF needs the `.pdf` extension **and** the `%PDF-` magic bytes; the browser's content-type is ignored. Error messages list the offending file names; they go back only to the uploader and are never logged. Success is 202 with `{"candidate_ids": [...]}`.
- **D62. Uploads stay in memory**: Starlette's spool-to-disk threshold is raised to `MAX_FILE_MB + 1`, and oversized requests are rejected from `Content-Length` before parsing (limit = files × MB + 1 MB). PDF bytes are handed to the background task as plain bytes.
- **D63. Candidates are created in shuffled order**, so the returned IDs and creation order don't map back to file order (file names often contain the candidate's name).
- **D64. Status rules**: decisions only between scored / shortlisted / rejected; processing or failed → 409; setting the same status again is a no-op 200. Response: `{"id", "status"}`.
- **D65. Reveal**: an already-revealed candidate returns the *first* reveal (same `revealedAt` / `revealedBy`) whatever its current status, consistent with "stays revealed". Not shortlisted and not revealed → 403; missing identity doc → 409. `revealedBy` = the recruiter's Firebase uid. The first reveal logs a server line with the job, candidate and uid (no identity). Response: `{"identity": {name, email, phone, links, location}, "revealedAt", "revealedBy"}`.
- **D66. Auth**: `verify_id_token` with 10 s clock-skew tolerance. Missing or invalid token → 401. An HTTPBearer scheme is registered, so Swagger's **Authorize** button works for Checkpoint 2.
- **D67. CORS**: methods GET/POST/PATCH/DELETE/OPTIONS, headers `Authorization` and `Content-Type`, no cookies (Bearer header only).

### Background processing
- **D68. One background task per upload** runs all its candidates with `asyncio.gather`; the Gemini semaphore caps concurrency. Worst case, 20 × 5 MB sits in RAM per upload.
- **D69. Finishing a candidate is one transaction**: candidate fields + private identity + counts, applied **only if the candidate is still `processing`**, so a sweep and a late completion can't both apply.
- **D70. The stale sweep runs only at startup** (as SPEC says) and uses `updatedAt` older than 10 minutes. Candidates interrupted less than 10 minutes before a restart stay `processing` until the next restart. It queries jobs where `counts.processing > 0`, then their candidates where `status == "processing"`, which avoids needing a collection-group index.
- **D71. Error messages**: `GeminiError` / `ValueError` messages are shown to users; anything else becomes "Unexpected error while processing this resume." Logs contain IDs and the exception type only.

### Config files
- **D72. `firebase.json`**: hosting serves `frontend/dist` with a single-page-app rewrite, a long cache for `/assets/**` and `no-cache` for `/demo/**`. `.firebaserc` holds the placeholder `YOUR_FIREBASE_PROJECT_ID`; replace it with your project ID. There is no `firestore.indexes.json`, because no composite queries are used (the frontend sorts on the client).
- **D73. `pytest.ini` filters Starlette's "use httpx2" deprecation warning**, since SPEC lists `httpx`.

---

## Session 2 (cont.): Phase 3 (frontend)

### Stack and structure
- **D74. Frontend versions are the latest releases as of today**: React 19.3, React Router 8.5, Vite 8.3, TypeScript 7.0, Tailwind 4.3, Firebase JS 13.1, Vitest 5. `package.json` uses caret ranges; commit `package-lock.json` for reproducible installs.
- **D75. Declarative routing** (`BrowserRouter` / `Routes`). The signed-in pages are lazy-loaded, so the Firestore SDK is a separate chunk: the first load is about 127 KB gzipped instead of 261 KB, which helps `/demo`.
- **D76. Firebase config is optional at build time.** Without `frontend/.env`, the landing page and `/demo` still work, the sign-in button is disabled with a tooltip, and signed-in routes show a "Firebase isn't configured" message.
- **D77. The jobs list queries `where ownerUid == uid` only and sorts by `createdAt` on the client**, so no composite index is needed.
- **D78. The vite dev server runs on port 5173**, matching the default `ALLOWED_ORIGINS`.

### Flows
- **D79. New job**: "Extract requirements" calls `POST /jobs`, which (per §8) creates the job. "Save job" sends `PATCH /requirements` only if you edited something, then opens the job. Leaving after extraction leaves the job in your list.
- **D80. Requirements can also be edited on the job page until the first upload**, with the same editor, since G1 says "before screening starts".
- **D81. Upload**: the dropzone also validates in the browser (`.pdf`, ≤ 5 MB, ≤ 20 files, ≤ remaining capacity). Accepted files show only as a **count** (no file names). Rejected files are listed by name in a warning until the next upload; they are never sent. It is two-step: choose files, then "Screen N resumes", with a note that requirements lock. Per-file progress shows **anon IDs + status chips** for the batch, never file names.
- **D82. Cold start**: `/health` is called on app load on every page (to wake Render early), and the banner appears after 2 s. It is **hidden on `/demo`**. A failure shows a "can't reach the server" banner with Try again. The health timeout is 90 s.
- **D83. `?candidate=<id>` opens that candidate's drawer** (a deep link; also used for the screenshots).

### Blind table and drawer
- **D84. ⚠ CONFIRM: the ranked table never shows names, even after reveal**, only a "revealed" badge. Identity appears in the drawer's identity card and in the CSV. This reads the acceptance criterion strictly ("the ranked table shows no name … anywhere").
- **D85. Table columns**: "Must-haves" = met / total plus "+N partial"; "Matched" = up to 2 *met requirements* (skill-type first) rather than raw profile skills; "Top gap" = the evaluator's first gap; "Education" = the first listed entry (institution, degree · grade).
- **D86. Rank = position by score among scored candidates**, fixed whatever the filter or sort. Processing and failed candidates sit at the bottom with no rank.
- **D87. The status `scored` is labelled "To review"** in the UI. The drawer's decisions are a three-way control: To review / Shortlist / Reject.
- **D88. "Revealed by you"** is shown when `revealedBy` equals the signed-in uid; otherwise "another user".

### CSV
- **D89. CSV exports the currently filtered rows, in rank order.** Columns: §9's list plus the file name for revealed candidates (per the §6.2 note). Every value is quoted; cells starting with `= + - @` get a leading `'` to block formula injection in spreadsheets; a UTF-8 BOM is added so Excel reads it correctly.

### Demo
- **D90. ⚠ CONFIRM: demo JSON shape = `{job, candidates, demoIdentities?, placeholder?}`.** `demoIdentities` (an addition to §10's shape) lets a viewer shortlist a synthetic candidate and perform a reveal in the demo; candidates with `revealed` already set show as revealed. Demo decisions are local state only; `revealedBy` is `"demo-user"`.
- **D91. Placeholder `demo_job.json`**: 5 hand-written fictional candidates (fictional employers and universities, names marked "(synthetic)", example.com emails, 555 phone numbers), with scores computed by the real formula. It is flagged `placeholder: true` and the demo banner says so. `build_demo.py` replaces it.

### Look and tests
- **D92. Look**: Inter (Google Fonts), indigo accent, slate neutrals, no dark mode. Checked at 1440 px and at a 390 px phone viewport (no horizontal page scroll; the table scrolls inside its card).
- **D93. Frontend tests (Vitest)** cover the CSV identity rules, the ranking helpers, and server-rendered checks that the table never contains identity or file names and that the drawer hides identity until reveal. There are no browser end-to-end tests: the live Firebase + API flow is untested until your Firebase project exists.

---

## Session 2 (cont.): Phase 4 (deploy config + demo data), Phase 5 (evaluation), P1 stretch, README

### Phase 4: deploy config and demo data
- **D94. Added a Render Blueprint (`render.yaml`)**: free plan, `rootDir: backend`, `PYTHON_VERSION=3.11.11`, health check `/health`. Secrets are `sync: false`, so Render asks for them in the dashboard. Setting up the web service by hand, as PLAN describes, still works.
- **D95. ⚠ CONFIRM: four synthetic resumes** (`backend/eval/synthetic/`, committed), generated by `scripts/make_synthetic_resumes.py` with a tiny built-in PDF writer (no new dependency). They are fictional people at fictional employers and universities, with example.com emails, phone numbers in the 555-01xx fiction range, `-synthetic` profile handles and a "this person is fictional" footer. They deliberately exercise redaction: third-person "she/his", the title "Mr.", a full street address, and a date-of-birth / gender / marital-status / nationality block. Intended fit spread for the IT JD: Aisha strong, Rohan good, Daniel network-heavy, Mei Lin junior.
- **D96. `build_demo.py` choices**:
  - Resumes that fail are left out, so the demo never shows an error.
  - The top 2 candidates *with a name* are shortlisted and revealed (Kaggle resumes have no names, so revealing one would show an empty card).
  - Other named candidates go into `demoIdentities`, so viewers can try the reveal flow.
  - The lowest scorer is marked rejected (when there are more than shortlist + 2 candidates), so every state appears.
  - Unrevealed candidates' `fileName` becomes `<anonId>.pdf` in the public JSON, because real file names often contain the person's name.
- **D97. Leak check (`app/leaks.py`)** runs on real pipeline output in `run_local.py` (warns) and `build_demo.py` (**refuses to write** the public demo file unless `--allow-leaks`). It searches the profile and evaluation for the full name, name parts over 2 characters, the email, the phone digits in any formatting, and the links.

### Phase 5: evaluation
- **D98. Throttling**: an optional per-model requests-per-minute cap (`GEMINI_PARSE_RPM`, `GEMINI_EVAL_RPM`, `GEMINI_EMBED_RPM`, which also apply on the server if set) spaces call starts 60/RPM seconds apart. Scripts additionally cache **evaluations** on disk, keyed by eval model + prompt version + exact input. Together with the parse / JD / embedding caches, this makes the eval resumable.
- **D99. ⚠ CONFIRM: pool construction.** JD → category comes from the file name (`information-technology` → `INFORMATION-TECHNOLOGY`, `finance` → `FINANCE`, `hr` → `HR`), overridable with `--jd-category`. PDFs are found recursively, and a PDF's category is its folder name. The pool is 8 per target category + 6 from all other categories, drawn with `random.Random(42)` from sorted file lists, and saved to `eval/pool.json` (commit it). It is reused unless `--new-pool`.
- **D100. Ablation details**:
  - *semantic* = order by raw cosine.
  - *requirements* = (0.5·must + 0.2·nice) / 0.7.
  - *combined* = the production total.
  - Extra 4th row, not required by the spec: *combined with the calibrated LO/HI*.
  - Ties break by resume path. Precision@k always divides by k, so with 8 relevant resumes the best possible P@10 is 0.8; `ablation.md` says so. nDCG is binary with a log2 discount.
- **D101. Calibration** uses the 10th and 90th percentiles of the raw cosine over all (JD, resume) pairs (90 pairs). The script prints the values and instructions; **you edit `scoring.py` yourself** (the script never edits code). If all cosines are equal (no spread), it keeps the current values.
- **D102. Eval outputs**: `metrics.json`, `ablation.md`, `ablation_chart.svg`, plus `scores.csv` (one row per pair, Kaggle IDs only, no identity) so each number can be traced.
- **D103. The chart is an SVG, not a PNG**: no matplotlib dependency, crisp at any size, and it follows GitHub's light/dark mode via `prefers-color-scheme`. Its colours are the validated reference palette's first 3 slots, checked with the palette validator on both surfaces. Light-mode aqua is below 3:1 contrast, so bars carry value labels and the README repeats the numbers as a table.

### P1 stretch (SPEC §17)
- **D104. `PATCH /weights` + sliders**: totals are recomputed from the stored components (no LLM calls). It returns **409 while any candidate is processing**, because in-flight candidates were scored with the weights from upload time. Sliders snap to 5% steps and always total 100% (moving one rescales the other two proportionally). Dragging previews totals and re-ranks the table and drawer live in the browser; **Save** persists. In the demo, Save edits local state only.
- **D105. `DELETE /jobs/{id}`**: deletes the job, its candidates and their private identity docs (Firestore `recursive_delete`), behind a confirm dialog that says it can't be undone. If background processing is still running, its writes fail harmlessly (they are logged as "could not save result").
- **D106. ⚠ OPEN QUESTION: retry for failed candidates was NOT built.** SPEC says retry needs the PDF re-uploaded, but a blind recruiter can't tell *which* PDF failed, because file names are never shown. Options: (a) store the PDF's SHA-256 on the candidate doc (a data-model change, §6), so the recruiter re-selects the whole batch and the server re-processes only the failed matches; (b) show the file name for failed candidates only (weakens blindness); (c) simply delete the failed candidate and upload again (works today). Which do you want?

### README and docs
- **D107. README** covers the problem, links (placeholders), screenshots, architecture, blind policy, scoring, evaluation (a table with placeholders until the eval runs; the chart path is broken until then), limitations (category proxy, graduation year, free-tier data use, synthetic resumes, scale, cold start), privacy, running locally, deploying, and the repo layout. The screenshots in `docs/` come from the **placeholder** demo; retake them after `build_demo.py`. I assumed the dataset URL is `kaggle.com/datasets/snehaanbhawal/resume-dataset`; check it.
- **D108. Not done (outside this repo, or needs you)**: PLAN Phase 6 items 2–3 (pushing the astro and chess projects; the presentation outline for all four projects) and the viva Q&A prep.

## Session 3: finish, publish and deploy (26 Oct 2026)

The request was to complete the plan per the spec, push to GitHub, and put a usable live site up that looks like a real business.

### P1 retry (answers D106)
- **D109. ⚠ CONFIRM: retry for failed candidates works from the uploading tab** (a fourth option, alongside D106's a–c). `POST /jobs/{id}/candidates/{cid}/retry` takes the PDF again as multipart `file`. It uses the same size and type checks as uploads, returns 409 unless the candidate is `failed`, and returns 409 if the file name differs from the candidate's `fileName`, so `fileName` always names the PDF that was processed. It moves failed → processing (counts: failed −1, processing +1) and reruns the pipeline in the background with the job's current weights; the anon ID stays the same. The browser keeps the uploaded `File` objects in memory, by candidate ID, until each candidate is scored, and offers "Retry this resume" in the drawer and "Retry N failed" in the batch panel. After a reload, retry isn't possible and the drawer says to upload again. There's no data-model change (§6), and blindness is unchanged: file names are never rendered, and the browser already holds the recruiter's own files.
- **D110. Upload response order (amends D63).** `candidate_ids` is now returned **in upload order** (index i = file i), so the tab can map files to candidates for retry. Candidates are still created, given anon IDs and processed in shuffled order.

### Hosting and deployment
- **D111. ⚠ CONFIRM: the frontend is hosted on GitHub Pages** (`https://askretik.github.io/fairscreen/`) instead of Firebase Hosting (SPEC §3, §16). Reasons: you asked for the site to go live from GitHub, and this machine has no Firebase CLI or Firebase login. `firebase.json` is kept, so Firebase Hosting still works as an alternative. The build takes `VITE_BASE=/<repo>/`; the router basename, the demo JSON fetch and the logo use that base. `404.html` is a copy of `index.html` so deep links work, since Pages has no rewrites.
- **D112. Public repository `ASKretik/fairscreen`** (the name from PLAN Phase 0). Pages on a free account needs a public repo. Before pushing, I checked that no secrets, `.env` files, caches or raw resumes are tracked.
- **D113. CI/CD (`.github/workflows/ci-deploy.yml`)**:
  - Runs backend `pytest` on Python 3.11 and frontend `npm test` plus the build on Node 22, for every push and PR.
  - Deploys to Pages only from `main`, after both test jobs pass.
  - The Firebase web config and `VITE_API_URL` come from repository **variables**. They are public identifiers, not secrets. Without them the build is demo-only (D114).
- **D114. Demo-only mode.** A production build without `VITE_API_URL` and the Firebase config:
  - hides every sign-in button;
  - skips the `/health` check, so no "can't reach the server" banner appears;
  - makes the main call to action "Try the live demo";
  - shows "Recruiter workspaces are opening soon" on `/jobs*`. The developer hint about `frontend/.env` appears only in dev builds.

  Setting the variables and re-running the workflow turns the full app on with no code change.
- **D115. `render.yaml` sets `ALLOWED_ORIGINS=https://askretik.github.io,http://localhost:5173`** instead of asking for it. A CORS origin has no path, and the value isn't secret.
- **D116. The cold-start banner shows only on `/jobs*` routes** (amends D82, which showed it everywhere except `/demo`). The landing page is now a marketing page, and only the workspace needs the server. The `/health` call still fires on app load when an API is configured, so Render starts waking up as soon as anyone opens the site (SPEC §9).

### Business-style site
- **D117. ⚠ CONFIRM: the landing page is a full product site.** Sections, in order:
  - sticky header with section links;
  - hero with a static preview of the ranked table built from the demo data;
  - proof points;
  - problem; how it works; features;
  - fairness promise (the SPEC §5 table);
  - transparent scoring with a worked example (the demo's CAND-3F9A: 100 × (0.5·1 + 0.2·0.625 + 0.3·0.867) = 88.5);
  - pricing; FAQ; closing call to action;
  - footer linking to the source, the README evaluation and this log.

  To avoid fabricated claims, there are **no testimonials, customer logos or usage numbers**. The proof points are product facts: 7 hidden identity signals (SPEC §5), 0 stored files, 3 score signals, 20 resumes per upload.
- **D118. ⚠ CONFIRM: pricing.**
  - **Starter**: $0, "free during early access". Its limits are the real ones: 50 candidates per job, 20 per upload.
  - **Team**: $29 per recruiter per month, **coming soon**. Features: 500 per job, shared jobs, AI interview questions (SPEC §17 P2), bias spot-check (P2), paid-tier AI processing.
  - **Enterprise**: custom, **coming soon**. Features: SSO, ATS integrations, data residency/DPA, audit export, support.

  Team and Enterprise list SPEC non-goals (teams, ATS integrations, billing) only as future paid features, marked "Coming soon" with a note that paid plans aren't on sale and prices may change. The prices are my invention: change them freely.
- **D119. The FAQ repeats the SPEC §13 free-tier note** in plain language: during early access Google may use prompts on the free tier, so use sample or consented resumes. A business page shouldn't hide this.
- **D120. Sign-in destinations.** "Start screening free" signs in and goes to `/jobs/new`. The header's "Sign in" goes to `/jobs`. If the popup is closed, nothing happens.
- **D121. Demo banner copy** no longer claims "real model output" while the file is placeholder data. It says "a sample IT role with fictional candidates", and switches to "real screening output … on public and synthetic resumes" once `build_demo.py` has written a non-placeholder file. A "Ready to screen your own role?" card follows the demo.
- **D122. README screenshots retaken** (landing, table, drawer) at 1280×800 @2x from the GitHub Pages build. They still show placeholder demo data.

## Session 4: tags with weights and the preloaded demo

The user asked for (1) a tab where a recruiter uploads resumes and creates their own tags with weights, (2) a live demo where anyone can change tags and weights and see the effect on a preloaded Kaggle pool, (3) **at most 100 resumes** in total, finished within 24 hours. Asking for this feature is the go-ahead to change the data model (§6) and scoring (§7.4); the details below are mine and marked for confirmation.

### Tags and weights (upload tab)
- **D123. ⚠ CONFIRM: "tags" are the job's requirements, each with a weight from 1 to 5.** `Requirement` gains `weight: int` (1–5, default 3; §6 change). Must-have / nice-to-have stay as two groups, so the "missing must-have" badge and the three group weights (0.5 / 0.2 / 0.3) are unchanged. The UI says "tags" everywhere; the code and Firestore keep `requirements`.
- **D124. ⚠ CONFIRM: weighted coverage (§7.4 change).** `must = Σ w·value / Σ w` over must-have tags (value 1 / 0.5 / 0 for met / partial / not met), the same for `nice`; `total` is unchanged. With equal weights this is exactly the SPEC formula, so existing scores, tests and the eval are unaffected. A tag missing from the weight map counts as 3. The frontend has the same formula (`weightedCoverage`), tested against the backend's numbers.
- **D125. The evaluator never sees weights.** `evaluate()` sends only `id`, `text` and `kind` of each tag (as before, so cached evaluations stay valid). JD parsing uses a weightless schema (`JobRequirementsDraft`), so Gemini can't invent weights; extracted tags start at 3.
- **D126. Jobs can be created from the recruiter's own tags.** `POST /jobs` takes either `jd_text` (as before) or `requirements` (validated like `PATCH /requirements`: role title, 1–8 must-haves, ≤ 8 nice-to-haves, ≤ 300 characters; no AI call, only the JD-embedding call). `jdText` is stored as "". The New job page has two tabs: "From a job description" and "Write your own tags".
- **D127. ⚠ CONFIRM: tags still lock after the first upload; weights don't.** Changing *which* tags are checked would need every candidate re-judged (one AI call each), so the SPEC's lock stays. `PATCH /weights` now also takes `tag_weights` ({tag ID: 1–5}; unknown IDs → 422) and recomputes `must_have`, `nice_to_have` and `total` from each stored checklist (no LLM or embedding calls), saving the new weights into `requirements`. It is still 409 while anything is processing.
- **D128. Weights UI.** Each tag gets a 1–5 picker (1 low, 3 normal, 5 critical) in the tag editor and in the "Adjust tag weights" panel, which also shows each tag's share of the total score (group weight × tag weight / sum of the group's tag weights). Previews re-rank the table live; Save persists. Tag chips show "×weight"; the drawer's checklist shows each tag's weight.

### Preloaded demo
- **D129. ⚠ CONFIRM: the demo pool is exactly 100 resumes**: 96 from the Kaggle Resume Dataset (24 each from INFORMATION-TECHNOLOGY, FINANCE and HR, 24 sampled from all other categories, seed 42) plus the 4 synthetic resumes. The 96 contain the 30-resume eval pool (`eval/pool.json`; built with run_eval's settings if missing), so the eval reuses those parses and embeddings and the total stays at 100 distinct resumes. The pool is saved to `eval/demo_pool.json`. `build_demo.py` refuses a pool over `--max-resumes` (100).
- **D130. ⚠ CONFIRM: a 43-tag library** (`eval/tag_library.json`): for each of the three roles, the JD's requirements as default tags (wording copied from the old demo's IT requirements, so the placeholder could reuse its verdicts) plus 1–3 extra tags, and 8 general tags (5+ years, leadership, project management, customer-facing, Master's, data analysis, process improvement, sales).
- **D131. One judging call per resume against the whole library** (`GeminiService.judge_tags`, own prompt `tags-v1` with the evaluator's rules; the summary describes the background rather than fit for one role). Verdicts are aligned to the library (missing = not met), evidence clipped to 20 words and pronouns neutralised, as in `align_evaluation`. Results are cached on disk like evaluations. Calls: ~100 parses, 100 judging, 100 + 3 role embeddings.
- **D132. `build_demo.py` is rewritten and writes `frontend/public/demo/demo_pool.json`** (replaces `demo_job.json`, now `frontend/src/test-data/sample_job.json`, a test fixture). Per candidate: anon ID (seeded), dataset label, blind profile, photo flag, redaction count, summary, verdicts (not-met omitted to save space), cosine to each role. Candidates are shuffled. Kaggle candidates have no published identity; only the synthetic people's identities are included, for the reveal flow. The leak check covers profile, summary and evidence, and nothing is written if it finds identity (or if any resume failed, unless `--allow-partial`).
- **D133. The demo ranks in the browser.** Choosing a role loads its default tags at weight 3 and the default group weights. Viewers can add library tags (to must-have or nice-to-have), move tags between groups, remove them, change weights (1–5) and group weights, and reset. Each change rebuilds a `Job` and `Candidate[]` (`deriveWorkspace`), so the existing table, drawer, filters, shortlist, reveal and CSV are reused. Strengths and gaps in the demo are derived from the tags ("Missing: …", "Partly shown: …") because there is no per-role AI summary. Switching role clears shortlist decisions (a new job). Up to 8 tags per group, as in the product.
- **D134. ⚠ CONFIRM: viewer-typed tags are keyword-matched, not AI-judged.** Judging a new tag would cost one AI call per resume for every visitor, and the demo has no sign-in. Matching uses the blind profile's headline, skills, certifications, job titles and summaries, projects and degree/field (never institution or employer names), drops stop words and numbers, allows a plural "s/es", and says met when every keyword appears and partial when at least half do. Evidence quotes the best line. These tags are labelled "approximate keyword match".
- **D135. The demo's semantic component is fixed per role**: the cosine between each profile and the role's default tags (embedded like a JD), rescaled with the LO/HI written into the file. It doesn't change when tags are edited (that would need embeddings in the browser).
- **D136. Demo table extras**: a "Dataset" column with each resume's Kaggle category (or "Synthetic"), "Who makes the top 10?" (how many of the top 10 come from each category, highlighting the role's own), and "Show 25 more / Show all" paging. The category is not identity, and showing it lets viewers judge the ranking.
- **D137. Placeholder until the real build**: `demo_pool.json` ships with the five fictional sample candidates and the IT role only (their existing verdicts mapped to the IT tags), flagged `placeholder: true`; the page says so. `build_demo.py` overwrites it.
- **D138. Models: `gemini-3.5-flash-lite` (parsing) and `gemini-3.5-flash` (judging), embeddings `gemini-embedding-001`.** Chosen by probing the user's key on 2026-10-26: the 2.5 models are closed to new users (404), `gemini-3.8-flash` returned 503 "high demand" on every try, `gemini-3.7-flash` took about 5 minutes for a one-word reply, and `3.5-flash` answered first time in about 13 s. Both chosen models are the same generation, as SPEC §3 asks (a Flash-Lite and a Flash). The same IDs go into Render. Model IDs remain environment settings only.
- **D139. `GEMINI_MAX_ATTEMPTS` (default 5) sets the retry budget per call.** The live server keeps 5, so users aren't left waiting. The local `.env` for the build scripts uses 8 (backoff 2, 4, 8, 16, 32, 60, 60 s), because the Flash models were returning frequent 503s and a two-resume pilot failed with 5 attempts but passed with 8.
- **D140. ⚠ CONFIRM: judging uses `gemini-3.5-flash-lite`, the same model as parsing** (amends D138; the user chose this over enabling billing). On the free tier `gemini-3.5-flash` allows only **20 requests per day per project** (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`), and the demo plus the evaluation need about 190 judging calls. Flash-Lite handled over 100 requests the same day without a cap. SPEC §3 asks for a Flash model for evaluation; this trades some precision for being able to run at all on the free tier. Render's `GEMINI_EVAL_MODEL` must match, so the live site judges the way the demo and the evaluation do. Enabling billing and switching back to a Flash model needs only the environment setting (cached judgements are per model, so it would re-judge).
- **D141. A daily-quota 429 fails at once instead of being retried.** When the error names a per-day quota (`…PerDay…` in the quota ID), retrying for minutes can't help, so the call stops with "The daily Gemini free-tier quota for this model is used up; it resets at midnight Pacific time." Per-minute 429s and 5xx errors are still retried as before.
