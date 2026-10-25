"""Run the real pipeline on a JD and a folder of PDFs, without Firestore (Phase 1 checkpoint).

Usage, from backend/:
    python scripts/run_local.py --jd eval/jds/information-technology.txt --resumes path/to/pdfs

Prints a ranked table and writes full results (blind profiles, evaluations,
scores) to .cache/run_local/<jd name>.json. Raw parses, which include identity,
are cached in .cache/parse/<pdf sha256>.json. Both are gitignored.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cache import ParseCache  # noqa: E402
from app.config import ConfigError, get_settings  # noqa: E402
from app.leaks import find_leaks  # noqa: E402
from app.models import Weights  # noqa: E402
from app.services.gemini import GeminiService  # noqa: E402
from app.services.pipeline import jd_embedding_text, new_anon_id, process_resume  # noqa: E402


def _fmt_row(cols: list[str], widths: list[int]) -> str:
    return "  ".join(c.ljust(w) for c, w in zip(cols, widths))


def print_table(rows: list[dict]) -> None:
    header = ["#", "Anon ID", "Score", "Must", "Nice", "Sem", "Cos", "Missing", "Redact", "Photo", "File"]
    lines = []
    for i, r in enumerate(rows, 1):
        s = r.get("score")
        if s:
            lines.append([
                str(i), r["anon_id"], f"{s['total']:.1f}", f"{s['must_have']:.2f}", f"{s['nice_to_have']:.2f}",
                f"{s['semantic']:.2f}", f"{s['semantic_raw']:.3f}", "YES" if s["missing_must_have"] else "",
                str(r["redaction_count"]), "yes" if r["photo_present"] else "", r["file"],
            ])
        else:
            lines.append(["-", r["anon_id"], "FAILED", "", "", "", "", "", "", "", f"{r['file']}: {r['error']}"])
    widths = [max(len(h), *(len(l[i]) for l in lines)) if lines else len(h) for i, h in enumerate(header)]
    print(_fmt_row(header, widths))
    print(_fmt_row(["-" * w for w in widths], widths))
    for l in lines:
        print(_fmt_row(l, widths))


async def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    try:
        settings.require_gemini()
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2

    jd_path, folder = Path(args.jd), Path(args.resumes)
    pdfs = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    if args.limit:
        pdfs = pdfs[: args.limit]
    if not pdfs:
        print(f"No PDFs found in {folder}", file=sys.stderr)
        return 2

    gemini = GeminiService(settings, disk_cache_dir=settings.cache_dir)
    cache = ParseCache(gemini.parse_cache_tag, disk_root=settings.cache_dir)
    weights = Weights()

    print(f"Parsing JD {jd_path.name} ...")
    requirements = await gemini.parse_jd(jd_path.read_text(encoding="utf-8"))
    print(f"\nRole: {requirements.role_title}")
    for r in requirements.must_have:
        print(f"  [must] {r.id} ({r.kind}) {r.text}")
    for r in requirements.nice_to_have:
        print(f"  [nice] {r.id} ({r.kind}) {r.text}")
    print(f"  min years: {requirements.min_years_experience}   education: {requirements.education_requirement}\n")
    jd_embedding = await gemini.embed(jd_embedding_text(requirements))

    taken: set[str] = set()
    max_bytes = settings.max_file_mb * 1024 * 1024
    done = 0

    async def run_one(path: Path) -> dict:
        nonlocal done
        anon = new_anon_id(taken)
        taken.add(anon)
        row: dict = {"anon_id": anon, "file": path.name, "status": "failed", "error": None}
        data = path.read_bytes()
        try:
            if len(data) > max_bytes:
                raise ValueError(f"File is larger than {settings.max_file_mb} MB.")
            res = await process_resume(data, requirements, jd_embedding, weights, gemini, cache)
            row.update(
                status="scored",
                sha256=res.sha256,
                score=res.score.model_dump(),
                redaction_count=res.redaction_count,
                photo_present=res.photo_present,
                evaluation=res.evaluation.model_dump(),
                profile=res.profile.model_dump(),
                identity=res.identity.model_dump(),  # local debug output only; never printed
                leaks=find_leaks({"profile": res.profile.model_dump(), "evaluation": res.evaluation.model_dump()},
                                 res.identity),
            )
        except Exception as e:  # one bad resume must not stop the batch
            row["error"] = str(e) or type(e).__name__
        done += 1
        print(f"  [{done}/{len(pdfs)}] {anon} {row['status']}", flush=True)
        return row

    print(f"Processing {len(pdfs)} resumes (concurrency {settings.gemini_concurrency}) ...")
    rows = await asyncio.gather(*(run_one(p) for p in pdfs))
    rows.sort(key=lambda r: (r["status"] != "scored", -(r.get("score") or {}).get("total", 0)))

    print()
    print_table(rows)
    leaky = [r for r in rows if r.get("leaks")]
    if leaky:
        print(f"\nWARNING: identity found in the blind data of {len(leaky)} resume(s):")
        for r in leaky:
            print(f"  {r['anon_id']} ({r['file']}): {len(r['leaks'])} item(s); see the JSON output")
    elif any(r["status"] == "scored" for r in rows):
        print("\nLeak check: no name, email, phone or link found in any blind profile or evaluation.")

    out_dir = settings.cache_dir / "run_local"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{jd_path.stem}.json"
    out.write_text(
        json.dumps(
            {"jd": jd_path.name, "requirements": requirements.model_dump(), "weights": weights.model_dump(), "results": rows},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nFull results: {out}")
    print(f"Raw parses (pre-redaction, include identity): {settings.cache_dir / 'parse'}/<sha256>.json")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jd", required=True, help="Path to a job description .txt file")
    parser.add_argument("--resumes", required=True, help="Folder of PDF resumes")
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N PDFs (sorted by name)")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(asyncio.run(main(parser.parse_args())))
