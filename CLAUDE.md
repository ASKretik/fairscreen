Read SPEC.md and PLAN.md before any work. Implement only the phase you are asked to.
Stop at the phase checkpoint and summarise what to verify.
Do not change the blind-screening policy (SPEC §5), scoring (§7.4) or data model (§6) without asking.
Ask before making design assumptions not covered by the spec.
Never commit secrets; use .env.example.
Record every assumption and design decision not covered by the spec in decisionsp4.md (append; keep the numbering).

Local dev: backend `cd backend && .venv/bin/python -m pytest` (tests), `.venv/bin/uvicorn app.main:app --reload` (API), `.venv/bin/python scripts/run_local.py --jd <jd.txt> --resumes <folder>` (pipeline without Firestore); frontend `cd frontend && npm run dev`, `npm test`, `npm run build`.
