"""Build frontend/public/demo/demo_job.json from the real pipeline (SPEC §10).

Usage, from backend/:
    python scripts/make_synthetic_resumes.py            # once: writes eval/synthetic/*.pdf
    python scripts/build_demo.py --jd eval/jds/information-technology.txt \\
        --resumes eval/synthetic eval/demo_resumes      # folders and/or PDF files, about 10 in total

Uses the disk caches (.cache/), so re-running costs no API calls for unchanged
inputs. The top candidates *with a name* are shortlisted and revealed (default 2);
other named candidates go into `demoIdentities`, so viewers can try the reveal flow
themselves. The lowest-scoring candidate is marked rejected. Resumes that fail are
left out, so the demo never shows an error.
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cache import ParseCache  # noqa: E402
from app.config import ConfigError, get_settings  # noqa: E402
from app.leaks import find_leaks  # noqa: E402
from app.models import Weights  # noqa: E402
from app.services.gemini import GeminiService  # noqa: E402
from app.services.pipeline import ResumeResult, jd_embedding_text, new_anon_id, process_resume  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demo" / "demo_job.json"
DEMO_USER = "demo-user"


def collect_pdfs(paths: list[str]) -> list[Path]:
    pdfs: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            pdfs += sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() == ".pdf")
        elif p.suffix.lower() == ".pdf" and p.is_file():
            pdfs.append(p)
        else:
            print(f"skipping {p}: not a PDF or folder", file=sys.stderr)
    return pdfs


async def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    try:
        settings.require_gemini()
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2
    pdfs = collect_pdfs(args.resumes)
    if not pdfs:
        print("No PDFs found.", file=sys.stderr)
        return 2

    gemini = GeminiService(settings, disk_cache_dir=settings.cache_dir)
    cache = ParseCache(gemini.parse_cache_tag, disk_root=settings.cache_dir)
    weights = Weights()
    jd_text = Path(args.jd).read_text(encoding="utf-8")
    requirements = await gemini.parse_jd(jd_text)
    jd_embedding = await gemini.embed(jd_embedding_text(requirements))
    print(f"Role: {requirements.role_title}; processing {len(pdfs)} resumes ...")

    async def run(path: Path) -> tuple[Path, ResumeResult | None]:
        try:
            return path, await process_resume(path.read_bytes(), requirements, jd_embedding, weights, gemini, cache)
        except Exception as e:
            print(f"  left out {path.name}: {e}", file=sys.stderr)
            return path, None

    results = [(p, r) for p, r in await asyncio.gather(*(run(p) for p in pdfs)) if r is not None]
    results.sort(key=lambda pr: -pr[1].score.total)
    if not results:
        print("Every resume failed; nothing to write.", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc).isoformat()
    taken: set[str] = set()
    named = [r for _, r in results if r.identity.name]
    shortlist = {id(r) for r in named[: args.shortlist]}
    reject = id(results[-1][1]) if len(results) > args.shortlist + 2 else None

    candidates, demo_identities, leaks_found = [], {}, False
    for path, r in results:
        anon = new_anon_id(taken)
        taken.add(anon)
        cid = anon.lower()
        revealed = r.identity.model_dump() if id(r) in shortlist else None
        status = "shortlisted" if id(r) in shortlist else "rejected" if id(r) == reject else "scored"
        doc = {
            "id": cid,
            "anonId": anon,
            # Real file names (often the candidate's name) only for revealed candidates.
            "fileName": path.name if revealed else f"{anon}.pdf",
            "status": status,
            "error": None,
            "profile": r.profile.model_dump(),
            "evaluation": r.evaluation.model_dump(),
            "score": r.score.model_dump(),
            "photoPresent": r.photo_present,
            "redactionCount": r.redaction_count,
            "revealed": revealed,
            "revealedAt": now if revealed else None,
            "revealedBy": DEMO_USER if revealed else None,
            "createdAt": now,
            "updatedAt": now,
        }
        public = {k: doc[k] for k in ("profile", "evaluation")}
        leaks = find_leaks(public, r.identity)
        if leaks:
            leaks_found = True
            print(f"  WARNING {anon} ({path.name}): identity found in blind data: {leaks}", file=sys.stderr)
        if not revealed and r.identity.name:
            demo_identities[cid] = r.identity.model_dump()
        candidates.append(doc)

    counts = {
        "total": len(candidates),
        "processing": 0,
        "scored": len(candidates),
        "failed": 0,
        "shortlisted": sum(c["status"] == "shortlisted" for c in candidates),
    }
    demo = {
        "job": {
            "id": "demo-job",
            "title": f"{requirements.role_title} (demo)",
            "jdText": jd_text,
            "requirements": requirements.model_dump(),
            "requirementsLocked": True,
            "weights": weights.model_dump(),
            "counts": counts,
            "createdAt": now,
            "updatedAt": now,
        },
        "candidates": candidates,
        "demoIdentities": demo_identities,
    }
    for c in candidates:
        print(f"  {c['anonId']}  {c['score']['total']:5.1f}  {c['status']:<11}  {c['fileName']}")
    if leaks_found and not args.allow_leaks:
        # The demo file is public: never write one that leaks identity.
        print("\nIdentity leaked into some blind profiles; nothing written. Fix the parse prompt or blind.py "
              "(or pass --allow-leaks to write anyway for debugging).", file=sys.stderr)
        return 3
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(demo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {out} ({len(candidates)} candidates, {counts['shortlisted']} revealed).")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jd", required=True, help="Job description .txt")
    parser.add_argument("--resumes", nargs="+", required=True, help="Folders and/or PDF files")
    parser.add_argument("--shortlist", type=int, default=2, help="How many named candidates to shortlist and reveal")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--allow-leaks", action="store_true", help="Write the file even if the leak check fails")
    sys.exit(asyncio.run(main(parser.parse_args())))
