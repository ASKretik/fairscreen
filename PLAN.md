# PLAN — FairScreen build plan (deadline: Tue 27 Oct 2026)

Work one phase at a time in Claude Code. Each phase ends at a **checkpoint**: verify it yourself before starting the next. SPEC.md is the source of truth.

## Schedule at a glance

| When | Phase | Time |
|---|---|---|
| Sun 25, evening | 0 Setup (manual) + 1 Core pipeline | ~3 h |
| Mon 26, morning | 2 API + Firestore + auth | ~1.5 h |
| Mon 26, afternoon | 3 Frontend | ~2.5 h |
| Mon 26, evening | 4 Deploy + demo data | ~1 h |
| Mon 26, night | 5 Evaluation (let it run slowly) | ~1.5 h, mostly waiting |
| Tue 27, morning | 6 README, GitHub pushes (astro + chess), presentation outline | ~2 h |
| Tue 27 | Buffer | |

**If you fall behind, cut in this order:** P1/P2 stretch items → eval reduced to 1 JD → weight sliders → demo synthetic resumes. Never cut: blind redaction, the reveal gate, `/demo`, deployment.

---

## Phase 0 — Setup (manual, ~45 min)

1. **Repo.** Create the GitHub repo `fairscreen`. Add `SPEC.md`, `PLAN.md`, and a `CLAUDE.md` containing:
   ```
   Read SPEC.md and PLAN.md before any work. Implement only the phase you are asked to.
   Stop at the phase checkpoint and summarise what to verify.
   Do not change the blind-screening policy (SPEC §5), scoring (§7.4) or data model (§6) without asking.
   Ask before making design assumptions not covered by the spec.
   Never commit secrets; use .env.example.
   ```
2. **Firebase** (a new project, separate from chess):
   - Authentication → enable the Google provider.
   - Firestore → create the database in production mode.
   - Register a web app → copy the config into `frontend/.env`.
   - Project settings → Service accounts → generate a private key. Base64 it for `FIREBASE_SERVICE_ACCOUNT_B64` (`base64 -i key.json | tr -d '\n'`). Keep the JSON out of git.
3. **Gemini.** Create an API key in Google AI Studio. Open the rate-limit page and note: which Flash and Flash-Lite model IDs are free for you, their requests-per-minute and per-day limits, and the embedding model. Put the IDs in `backend/.env`.
4. **Kaggle data.** Download the "Resume Dataset" (Snehaan Bhawal) into `backend/eval/data/` and add that folder to `.gitignore`. Open 3–4 PDFs and check whether they contain names and contact details. If they don't, you'll add synthetic resumes in Phase 4.
5. **JDs.** Choose 3 categories for eval (e.g. IT, Finance, HR) and pick the demo role (I'd use the IT one). Write or paste 3 realistic JDs into `backend/eval/jds/`. Claude can draft them.

**Checkpoint 0:** `.env` files filled in locally, dataset unzipped, 3 JDs saved.

---

## Phase 1 — Core pipeline, no web (~2 h)

**Claude Code prompt:**
> Implement Phase 1 from PLAN.md: backend scaffold, `models.py`, `services/gemini.py` (parse_jd, parse_resume from PDF bytes, evaluate, embed, with retry and a semaphore), `blind.py`, `scoring.py`, `cache.py` (disk cache by PDF SHA-256), `tests/test_blind.py`, `tests/test_scoring.py`, and `scripts/run_local.py`. No FastAPI routes or Firestore yet. Check the current google-genai docs for PDF input, structured output and embeddings before writing gemini.py.

**Checkpoint 1:**
- `pytest` passes.
- `python scripts/run_local.py --jd eval/jds/<it>.txt --resumes <folder of 5 PDFs>` prints a ranked table.
- Open the cached parse JSON for 2 resumes. Confirm the blind profile has **no** name, email, phone, URL, location or gendered pronouns, and **does** have college, degree, grade and years. If anything leaks, fix the prompt or `blind.py` now, before building on it.

---

## Phase 2 — API, Firestore, auth (~1.5 h)

**Claude Code prompt:**
> Implement Phase 2 from PLAN.md: FastAPI app with the endpoints in SPEC §8 (MVP ones only, not P1), Firebase token verification, Firestore writes per SPEC §6.2, background processing per §7.2 with progress counts, the stale-processing sweep on startup, upload validation, CORS, `firestore.rules`, and `tests/test_api.py` with Gemini and Firestore mocked.

**Checkpoint 2:**
- `pytest` passes.
- Run locally. Using Swagger (`/docs`) with a real ID token (grab one from a tiny test page or the Phase 3 app): create a job, upload 3 PDFs, and watch the docs appear in the Firestore console. Check that reveal returns 403 before shortlisting and works after.
- Deploy the rules: `firebase deploy --only firestore:rules`.

---

## Phase 3 — Frontend (~2.5 h)

**Claude Code prompt:**
> Implement Phase 3 from PLAN.md: the React + Vite + TS frontend per SPEC §9. Firebase Google sign-in, Firestore real-time listeners for jobs and candidates, all routes (`/`, `/demo`, `/jobs`, `/jobs/new`, `/jobs/:jobId`), the candidate drawer with the reveal flow, CSV export, and the cold-start banner. For `/demo`, read `public/demo/demo_job.json`; create a small placeholder JSON for now. Clean SaaS look.

**Checkpoint 3 (full local run, backend on localhost):**
- Sign in → new job → requirements extracted and edited → upload 10 PDFs → rows fill in live.
- Search the page, including the table and the drawer, for any name, email or file name. There should be none.
- Shortlist → reveal → identity card shows. CSV export contains identity only for that candidate.
- `/demo` works logged out.

---

## Phase 4 — Deploy and demo data (~1 h)

1. **Render:** new Web Service from the repo, root `backend`, start command from SPEC §15, env vars from SPEC §12. Hit `/health`.
2. **Firebase Hosting:** set `VITE_API_URL` to the Render URL, `npm run build`, then `firebase deploy --only hosting`. Add the hosting URL to `ALLOWED_ORIGINS` on Render, and to Firebase Auth → authorised domains.
3. **Demo data:** if needed, have Claude write 3–4 synthetic resumes (fictional people, with names and contacts) and export them to PDF. Then run:
   > Implement and run `scripts/build_demo.py` per SPEC §10 on the IT JD and about 10 resumes (including the synthetic ones). Mark 2 as shortlisted and revealed in the JSON.
   Commit `demo_job.json` and redeploy hosting.

**Checkpoint 4:** the live URL works end to end in an incognito window. `/demo` loads while the Render service is asleep.

---

## Phase 5 — Evaluation (~1.5 h, runs slowly to respect quota)

**Claude Code prompt:**
> Implement Phase 5 from PLAN.md: `eval/run_eval.py` per SPEC §11 — fixed pool of 30 with seed saved to pool.json, cached parsing, evaluation for 3 JDs, precision@5/@10 and nDCG@10, the 3-way ablation, cosine calibration (print the 10th and 90th percentiles), and the outputs in eval/results/ including one chart. Throttle calls to stay within the free-tier limits I put in .env, and make it resumable if it stops halfway.

Start it, and let it run while you do other things. Then update `LO`/`HI` in `scoring.py` from the printed percentiles, re-run `build_demo.py`, and redeploy.

**Checkpoint 5:** `metrics.json`, `ablation.md` and the chart exist. You can explain one number from each in a sentence.

---

## Phase 6 — Wrap-up (Tue morning, ~2 h)

1. **README:** the problem, a screenshot, the live and demo links, the architecture diagram (SPEC §4), the blind-screening table (SPEC §5), the eval results and ablation, the limitations (category labels as proxy, graduation year as an age proxy, free-tier data use), and how to run it locally.
2. Push the **astro** and **chess** projects to GitHub as well (budget about an hour).
3. Presentation outline for all four projects.

---

## Likely viva questions (prepare one-line answers)
- Why compute the score in code instead of asking the LLM for a number? (Reproducible, explainable, adjustable without new calls.)
- How do you know redaction works? (Two layers, unit tests, the redaction count shown in the UI.)
- Why is college visible but not scored? Isn't graduation year an age proxy?
- What does precision@5 mean here, and what are the limits of using category labels as ground truth?
- What did the ablation show: do embeddings add anything over requirement checks?
- What breaks at 1,000 resumes per job? (Rate limits → batch API or paid tier, a queue instead of background tasks, cost.)
- Why are no raw resumes stored?

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Gemini free-tier limits hit mid-demo | Demo mode needs no API calls; parse cache; concurrency 2; retries with backoff |
| Render cold start during the viva | Open the live app 2 minutes before; the banner explains the wait; `/demo` doesn't need the backend |
| Identity leaks into the profile text | Two-layer redaction, tests, and a manual check at Checkpoint 1 |
| Kaggle resumes have no names | Synthetic resumes for the demo (labelled as synthetic) |
| Running out of time | Cut order at the top of this file |
