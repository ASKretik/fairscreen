"""Offline evaluation (SPEC §11): precision@5, precision@10, nDCG@10, a 3-way ablation and cosine calibration.

Usage, from backend/ (after downloading the Kaggle "Resume Dataset" into eval/data/):
    python eval/run_eval.py --dry-run     # build/show the fixed pool and the API-call plan; no calls
    python eval/run_eval.py               # run it (slowly, within GEMINI_*_RPM from .env)

Resumable: parses, embeddings and evaluations are cached under .cache/, so after a
stop (Ctrl-C, quota, crash) the same command continues where it left off.

Relevance is a proxy: a resume counts as relevant to a JD when its Kaggle category
matches the JD's category.
"""

import argparse
import asyncio
import csv
import json
import random
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app import blind, scoring  # noqa: E402
from app.cache import ParseCache, sha256_hex  # noqa: E402
from app.config import ConfigError, get_settings  # noqa: E402
from app.models import BlindProfile, JobRequirements, Weights  # noqa: E402
from app.services.gemini import GeminiService  # noqa: E402
from app.services.pipeline import jd_embedding_text, profile_embedding_text  # noqa: E402
from eval.chart import ablation_chart_svg  # noqa: E402
from eval.metrics import ndcg_at_k, percentile, precision_at_k, rank  # noqa: E402

EVAL_DIR = BACKEND / "eval"
DEFAULT_CATEGORIES = {"information-technology": "INFORMATION-TECHNOLOGY", "finance": "FINANCE", "hr": "HR"}
METHODS = {
    "semantic": "Semantic only (embedding cosine)",
    "requirements": "Requirements only (must/nice, weights renormalised)",
    "combined": "Combined score (production formula)",
    "combined_calibrated": "Combined, with LO/HI calibrated on this pool",
}


@dataclass
class Row:
    jd: str
    resume: str
    category: str
    relevant: bool
    must: float
    nice: float
    semantic_raw: float
    semantic: float
    total: float
    missing_must_have: bool


# ---- pool --------------------------------------------------------------------------------

def discover(data_dir: Path) -> dict[str, list[str]]:
    """Category (the PDF's folder name) -> sorted relative paths of its PDFs."""
    by_cat: dict[str, list[str]] = {}
    for pdf in sorted(data_dir.rglob("*.pdf")):
        by_cat.setdefault(pdf.parent.name.upper(), []).append(str(pdf.relative_to(data_dir)))
    return by_cat


def build_pool(by_cat: dict[str, list[str]], targets: list[str], per_category: int, others: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    pool = []
    for cat in targets:
        files = by_cat.get(cat, [])
        if len(files) < per_category:
            raise SystemExit(f"Category {cat} has {len(files)} PDFs; need {per_category}. Categories found: {sorted(by_cat)}")
        pool += [{"id": f, "category": cat} for f in rng.sample(files, per_category)]
    rest = [(f, c) for c, fs in sorted(by_cat.items()) if c not in targets for f in fs]
    pool += [{"id": f, "category": c} for f, c in rng.sample(rest, min(others, len(rest)))]
    return pool


# ---- metrics -------------------------------------------------------------------------------

def requirements_only(r: Row, w: Weights) -> float:
    denom = w.must + w.nice
    return (w.must * r.must + w.nice * r.nice) / denom if denom else 0.0


def method_keys(w: Weights, lo: float, hi: float) -> dict:
    return {
        "semantic": lambda r: r.semantic_raw,
        "requirements": lambda r: requirements_only(r, w),
        "combined": lambda r: r.total,
        "combined_calibrated": lambda r: scoring.combine(r.must, r.nice, scoring.rescale_cosine(r.semantic_raw, lo, hi), w),
    }


def evaluate_rankings(rows: list[Row], keys: dict) -> dict[str, dict[str, float]]:
    out = {}
    for name, key in keys.items():
        ranked = rank(rows, key=key, tiebreak=lambda r: r.resume)
        rel = [r.relevant for r in ranked]
        out[name] = {"p@5": precision_at_k(rel, 5), "p@10": precision_at_k(rel, 10), "ndcg@10": ndcg_at_k(rel, 10)}
    return out


def ablation_markdown(result: dict) -> str:
    cal = result["calibration"]
    lines = [
        "# Evaluation: ranking quality and ablation",
        "",
        f"Pool: {result['pool_size']} Kaggle resumes (seed {result['seed']}), {result['per_category']} per target category "
        f"+ {result['others']} from other categories. Relevant = same Kaggle category as the JD. "
        f"With {result['per_category']} relevant resumes per JD, the best possible precision@10 is "
        f"{min(1.0, result['per_category'] / 10):.1f}.",
        "",
        "## Mean over job descriptions",
        "",
        "| Method | Precision@5 | Precision@10 | nDCG@10 |",
        "|---|---:|---:|---:|",
    ]
    for name, label in METHODS.items():
        m = result["mean"][name]
        lines.append(f"| {label} | {m['p@5']:.2f} | {m['p@10']:.2f} | {m['ndcg@10']:.2f} |")
    lines += ["", "## Per job description", "", "| JD | Category | Method | P@5 | P@10 | nDCG@10 |", "|---|---|---|---:|---:|---:|"]
    for jd, info in result["jds"].items():
        for name in METHODS:
            m = info["methods"][name]
            lines.append(f"| {jd} | {info['category']} | {name} | {m['p@5']:.2f} | {m['p@10']:.2f} | {m['ndcg@10']:.2f} |")
    lines += [
        "",
        "## Cosine calibration",
        "",
        f"Raw cosine over {cal['n_pairs']} (JD, resume) pairs: min {cal['min']:.3f}, 10th percentile **{cal['p10']:.3f}**, "
        f"median {cal['p50']:.3f}, 90th percentile **{cal['p90']:.3f}**, max {cal['max']:.3f}. "
        f"The scorer used LO={cal['used_lo']}, HI={cal['used_hi']}; the calibrated values are LO={cal['p10']:.2f}, HI={cal['p90']:.2f}.",
        "",
        "## Caveat",
        "",
        "Category labels are only a proxy for relevance: an IT resume is not necessarily a fit for this particular IT job, "
        "and a resume from another category can still meet the requirements.",
        "",
    ]
    return "\n".join(lines)


# ---- run ---------------------------------------------------------------------------------------

async def run(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    jd_files = [Path(p) for p in args.jds] if args.jds else sorted((EVAL_DIR / "jds").glob("*.txt"))
    overrides = dict(kv.split("=", 1) for kv in args.jd_category)
    jd_cats = {jd.name: overrides.get(jd.name) or DEFAULT_CATEGORIES.get(jd.stem, jd.stem.upper()) for jd in jd_files}
    targets = list(dict.fromkeys(jd_cats.values()))

    if not data_dir.exists():
        print(f"No data at {data_dir}. Download the Kaggle Resume Dataset there first.", file=sys.stderr)
        return 2
    pool_path = Path(args.pool)
    if pool_path.exists() and not args.new_pool:
        saved = json.loads(pool_path.read_text())
        pool, seed = saved["items"], saved["seed"]
        if set(saved.get("categories", [])) != set(targets):
            print(f"Note: {pool_path} was built for {saved.get('categories')}; JDs now map to {targets}. Use --new-pool to rebuild.")
    else:
        by_cat = discover(data_dir)
        if not by_cat:
            print(f"No PDFs under {data_dir}.", file=sys.stderr)
            return 2
        seed = args.seed
        pool = build_pool(by_cat, targets, args.per_category, args.others, seed)
        pool_path.write_text(json.dumps({
            "seed": seed, "per_category": args.per_category, "others": args.others, "categories": targets,
            "created": datetime.now(timezone.utc).isoformat(), "items": pool,
        }, indent=2) + "\n")
        print(f"Saved a new pool of {len(pool)} to {pool_path}")

    counts: dict[str, int] = {}
    for item in pool:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    print(f"Pool: {len(pool)} resumes {counts}; JDs: {jd_cats}")
    print(f"Plan (before cache hits): {len(pool)} parses, {len(pool) * len(jd_files)} evaluations, "
          f"{len(pool) + len(jd_files)} embeddings, {len(jd_files)} JD parses.")
    if args.dry_run:
        return 0

    settings = get_settings()
    try:
        settings.require_gemini()
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2
    if not (settings.gemini_parse_rpm and settings.gemini_eval_rpm):
        print("Tip: set GEMINI_PARSE_RPM / GEMINI_EVAL_RPM / GEMINI_EMBED_RPM in .env to stay under the free-tier limits.")
    gemini = GeminiService(settings, disk_cache_dir=settings.cache_dir)
    cache = ParseCache(gemini.parse_cache_tag, disk_root=settings.cache_dir)
    weights = Weights()
    failures: list[str] = []

    # 1. parse + redact + embed every resume once (JD-independent)
    profiles: dict[str, tuple[BlindProfile, list[float]]] = {}
    done = 0

    async def prepare(item: dict) -> None:
        nonlocal done
        rid = item["id"]
        try:
            data = (data_dir / rid).read_bytes()
            sha = sha256_hex(data)
            parsed = cache.get(sha)
            if parsed is None:
                parsed = await gemini.parse_resume(data)
                cache.put(sha, parsed)
            profile, _, _ = blind.redact(parsed)
            profiles[rid] = (profile, await gemini.embed(profile_embedding_text(profile)))
        except Exception as e:
            failures.append(f"prepare {rid}: {e}")
        done += 1
        print(f"\r  resumes prepared {done}/{len(pool)}", end="", flush=True)

    await asyncio.gather(*(prepare(i) for i in pool))
    print()

    # 2. per JD: requirements, JD embedding, evaluate + score every resume
    rows: list[Row] = []
    for jd in jd_files:
        req: JobRequirements = await gemini.parse_jd(jd.read_text(encoding="utf-8"))
        jd_emb = await gemini.embed(jd_embedding_text(req))
        category = jd_cats[jd.name]
        done = 0

        async def score_one(item: dict) -> None:
            nonlocal done
            rid = item["id"]
            if rid not in profiles:
                return
            profile, emb = profiles[rid]
            try:
                ev = await gemini.evaluate(profile, req)
                s = scoring.score(ev, jd_emb, emb, weights)
                rows.append(Row(jd.name, rid, item["category"], item["category"] == category, s.must_have,
                                s.nice_to_have, s.semantic_raw, s.semantic, s.total, s.missing_must_have))
            except Exception as e:
                failures.append(f"evaluate {jd.name} × {rid}: {e}")
            done += 1
            print(f"\r  {jd.name}: evaluated {done}/{len(profiles)}", end="", flush=True)

        await asyncio.gather(*(score_one(i) for i in pool))
        print()

    if failures:
        print(f"\n{len(failures)} step(s) failed (re-run to retry; cached work is kept):")
        for f in failures[:10]:
            print("  -", f)
    if not rows:
        print("No results to score.", file=sys.stderr)
        return 1

    # 3. calibration and metrics
    raws = [r.semantic_raw for r in rows]
    cal = {
        "n_pairs": len(raws), "min": min(raws), "max": max(raws), "p10": percentile(raws, 10),
        "p50": percentile(raws, 50), "p90": percentile(raws, 90),
        "used_lo": scoring.SEMANTIC_LO, "used_hi": scoring.SEMANTIC_HI,
    }
    # A degenerate spread (all cosines equal) can't define a rescale; keep the current bounds then.
    cal["degenerate"] = cal["p90"] - cal["p10"] < 1e-6
    lo, hi = (cal["used_lo"], cal["used_hi"]) if cal["degenerate"] else (cal["p10"], cal["p90"])
    keys = method_keys(weights, lo, hi)
    per_jd = {}
    for jd in jd_files:
        jd_rows = [r for r in rows if r.jd == jd.name]
        per_jd[jd.name] = {
            "category": jd_cats[jd.name],
            "n_scored": len(jd_rows),
            "n_relevant": sum(r.relevant for r in jd_rows),
            "methods": evaluate_rankings(jd_rows, keys) if jd_rows else {},
        }
    scored_jds = [v for v in per_jd.values() if v["methods"]]
    mean = {m: {k: sum(v["methods"][m][k] for v in scored_jds) / len(scored_jds) for k in ("p@5", "p@10", "ndcg@10")}
            for m in METHODS}
    result = {
        "created": datetime.now(timezone.utc).isoformat(),
        "models": {"parse": settings.gemini_parse_model, "eval": settings.gemini_eval_model, "embed": settings.gemini_embed_model},
        "seed": seed, "pool_size": len(pool), "per_category": args.per_category, "others": args.others,
        "weights": weights.model_dump(), "failures": len(failures),
        "jds": per_jd, "mean": mean, "calibration": cal,
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")
    (out / "ablation.md").write_text(ablation_markdown(result))
    (out / "ablation_chart.svg").write_text(ablation_chart_svg(
        mean, f"Mean over {len(scored_jds)} job descriptions, {len(pool)}-resume Kaggle pool"))
    with (out / "scores.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(Row.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(r) for r in sorted(rows, key=lambda r: (r.jd, -r.total)))

    print("\nMean over JDs:")
    for name in METHODS:
        m = mean[name]
        print(f"  {name:<20} P@5 {m['p@5']:.2f}   P@10 {m['p@10']:.2f}   nDCG@10 {m['ndcg@10']:.2f}")
    print(f"\nRaw cosine 10th percentile = {cal['p10']:.3f}, 90th percentile = {cal['p90']:.3f}")
    if cal["degenerate"]:
        print("The cosines have no spread, so there is nothing to calibrate; keep the current LO/HI.")
    else:
        print(f"To calibrate: set SEMANTIC_LO = {cal['p10']:.2f} and SEMANTIC_HI = {cal['p90']:.2f} in app/scoring.py,")
        print("then re-run scripts/build_demo.py.")
    print(f"Wrote {out}/metrics.json, ablation.md, ablation_chart.svg, scores.csv")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=str(EVAL_DIR / "data"), help="Kaggle data folder (PDFs in one folder per category)")
    parser.add_argument("--jds", nargs="*", help="JD .txt files (default: eval/jds/*.txt)")
    parser.add_argument("--jd-category", action="append", default=[], metavar="FILE=CATEGORY",
                        help="Override the category for a JD file, e.g. hr.txt=HR")
    parser.add_argument("--per-category", type=int, default=8)
    parser.add_argument("--others", type=int, default=6)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--pool", default=str(EVAL_DIR / "pool.json"))
    parser.add_argument("--new-pool", action="store_true", help="Rebuild pool.json even if it exists")
    parser.add_argument("--out", default=str(EVAL_DIR / "results"))
    parser.add_argument("--dry-run", action="store_true", help="Show the pool and call plan; make no API calls")
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
