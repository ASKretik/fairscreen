"""Build frontend/public/demo/demo_pool.json, the preloaded demo (SPEC §10, extended for tags).

The pool is 100 resumes: 96 from the Kaggle Resume Dataset (24 each from IT, Finance and HR,
24 from other categories) plus the 4 synthetic resumes. The Kaggle part contains the 30-resume
eval pool (eval/pool.json), so the eval reuses these parses and embeddings.

Each resume is parsed and redacted once (cached), judged once against every tag in
eval/tag_library.json (one call per resume) and embedded once; cosines to each role are
precomputed. The demo page then ranks the pool for any choice of tags and weights in the
browser, with no API calls. Only blind data is written, plus the identities of the synthetic
(fictional) people, so the reveal flow can be tried.

Usage, from backend/ (after downloading the Kaggle dataset into eval/data/):
    python scripts/make_synthetic_resumes.py   # once: writes eval/synthetic/*.pdf
    python scripts/build_demo.py --dry-run     # build/show the pool and the call plan; no calls
    python scripts/build_demo.py               # run it (resumable: work is cached under .cache/)

About 100 parses, 100 tag-judging calls and 103 embeddings before cache hits.
"""

import argparse
import asyncio
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app import blind, scoring  # noqa: E402
from app.cache import ParseCache, sha256_hex  # noqa: E402
from app.config import ConfigError, get_settings  # noqa: E402
from app.leaks import find_leaks  # noqa: E402
from app.models import JobRequirements, Requirement, Weights  # noqa: E402
from app.services.gemini import GeminiService  # noqa: E402
from app.services.pipeline import jd_embedding_text, profile_embedding_text  # noqa: E402
from eval.run_eval import DEFAULT_CATEGORIES, build_pool, discover  # noqa: E402

EVAL_DIR = BACKEND / "eval"
DEFAULT_OUT = BACKEND.parent / "frontend" / "public" / "demo" / "demo_pool.json"
TARGETS = list(DEFAULT_CATEGORIES.values())
PER_TARGET = 24       # Kaggle resumes per target category (IT, Finance, HR)
OTHERS = 24           # Kaggle resumes from all other categories
EVAL_PER_CATEGORY, EVAL_OTHERS = 8, 6   # run_eval.py's defaults: the eval pool is a subset
SYNTHETIC_LABEL = "SYNTHETIC"
REVEALED_FIELDS = ("name", "email", "phone", "links", "location")


# ---- library and pool --------------------------------------------------------------------

def load_library(path: Path) -> dict[str, Any]:
    lib = json.loads(path.read_text(encoding="utf-8"))
    ids = [t["id"] for t in lib["tags"]]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"{path}: duplicate tag IDs")
    for role in lib["roles"]:
        unknown = [t for t in role["must"] + role["nice"] if t not in ids]
        if unknown:
            raise SystemExit(f"{path}: role {role['id']} uses unknown tags {unknown}")
    return lib


def library_tags(lib: dict[str, Any]) -> list[Requirement]:
    return [Requirement(id=t["id"], text=t["text"], kind=t["kind"]) for t in lib["tags"]]


def role_requirements(lib: dict[str, Any], role: dict[str, Any]) -> JobRequirements:
    by_id = {t.id: t for t in library_tags(lib)}
    return JobRequirements(
        role_title=role["title"],
        must_have=[by_id[t] for t in role["must"]],
        nice_to_have=[by_id[t] for t in role["nice"]],
        min_years_experience=None,
        education_requirement=None,
    )


def eval_pool(by_cat: dict[str, list[str]], path: Path, seed: int) -> list[dict]:
    """The eval pool from eval/pool.json, or a new one saved there in run_eval.py's format."""
    if path.exists():
        return json.loads(path.read_text())["items"]
    items = build_pool(by_cat, TARGETS, EVAL_PER_CATEGORY, EVAL_OTHERS, seed)
    path.write_text(json.dumps({
        "seed": seed, "per_category": EVAL_PER_CATEGORY, "others": EVAL_OTHERS, "categories": TARGETS,
        "created": datetime.now(timezone.utc).isoformat(), "items": items,
    }, indent=2) + "\n")
    print(f"Saved the eval pool ({len(items)}) to {path}")
    return items


def extend_pool(by_cat: dict[str, list[str]], base: list[dict], seed: int) -> list[dict]:
    """`base` plus random resumes up to PER_TARGET per target category and OTHERS from the rest."""
    rng = random.Random(seed)
    items = list(base)
    taken = {i["id"] for i in items}
    for cat in TARGETS:
        need = PER_TARGET - sum(i["category"] == cat for i in items)
        rest = [f for f in by_cat.get(cat, []) if f not in taken]
        if need > len(rest):
            raise SystemExit(f"Category {cat} has too few PDFs for the demo pool.")
        items += [{"id": f, "category": cat} for f in rng.sample(rest, max(0, need))]
    need = OTHERS - sum(i["category"] not in TARGETS for i in items)
    rest = [(f, c) for c, fs in sorted(by_cat.items()) if c not in TARGETS for f in fs if f not in taken]
    items += [{"id": f, "category": c} for f, c in rng.sample(rest, min(max(0, need), len(rest)))]
    return items


def demo_pool(by_cat: dict[str, list[str]], eval_path: Path, path: Path, seed: int, rebuild: bool) -> list[dict]:
    if path.exists() and not rebuild:
        return json.loads(path.read_text())["items"]
    items = extend_pool(by_cat, eval_pool(by_cat, eval_path, seed), seed)
    path.write_text(json.dumps({
        "seed": seed, "per_target": PER_TARGET, "others": OTHERS, "targets": TARGETS,
        "created": datetime.now(timezone.utc).isoformat(), "items": items,
    }, indent=2) + "\n")
    print(f"Saved the demo pool ({len(items)}) to {path}")
    return items


def anon_ids(n: int, rng: random.Random) -> list[str]:
    out: list[str] = []
    while len(out) < n:
        anon = f"CAND-{rng.getrandbits(16):04X}"
        if anon not in out:
            out.append(anon)
    return out


# ---- run ---------------------------------------------------------------------------------------

async def run(args: argparse.Namespace) -> int:
    data_dir, synthetic_dir = Path(args.data), Path(args.synthetic)
    lib = load_library(Path(args.library))
    tags = library_tags(lib)
    if not data_dir.exists():
        print(f"No data at {data_dir}. Download the Kaggle Resume Dataset there first.", file=sys.stderr)
        return 2
    by_cat = discover(data_dir)
    kaggle = demo_pool(by_cat, Path(args.eval_pool), Path(args.pool), args.seed, args.new_pool)
    synthetic = sorted(p for p in synthetic_dir.glob("*.pdf")) if synthetic_dir.exists() else []
    entries = [(data_dir / i["id"], i["category"]) for i in kaggle] + [(p, SYNTHETIC_LABEL) for p in synthetic]
    if len(entries) > args.max_resumes:
        print(f"The pool has {len(entries)} resumes; the limit is {args.max_resumes}.", file=sys.stderr)
        return 2

    counts: dict[str, int] = {}
    for _, cat in entries:
        counts[cat] = counts.get(cat, 0) + 1
    print(f"Pool: {len(entries)} resumes {dict(sorted(counts.items()))}")
    print(f"Library: {len(tags)} tags, {len(lib['roles'])} roles")
    print(f"Plan (before cache hits): {len(entries)} parses, {len(entries)} tag-judging calls, "
          f"{len(entries) + len(lib['roles'])} embeddings.")
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

    role_embeddings = {}
    for role in lib["roles"]:
        role_embeddings[role["id"]] = await gemini.embed(jd_embedding_text(role_requirements(lib, role)))

    failures: list[str] = []
    done = 0

    async def prepare(path: Path, label: str) -> dict[str, Any] | None:
        nonlocal done
        try:
            data = path.read_bytes()
            sha = sha256_hex(data)
            parsed = cache.get(sha)
            if parsed is None:
                parsed = await gemini.parse_resume(data)
                cache.put(sha, parsed)
            profile, identity, redactions = blind.redact(parsed)
            judgement, emb = await asyncio.gather(
                gemini.judge_tags(profile, tags), gemini.embed(profile_embedding_text(profile))
            )
            return {
                "path": path, "label": label, "profile": profile, "identity": identity,
                "photo": parsed.photo_present, "redactions": redactions, "judgement": judgement,
                "cosine": {rid: round(scoring.cosine_similarity(e, emb), 4) for rid, e in role_embeddings.items()},
            }
        except Exception as e:
            failures.append(f"{path.name}: {e}")
            return None
        finally:
            done += 1
            print(f"\r  resumes done {done}/{len(entries)}", end="", flush=True)

    results = [r for r in await asyncio.gather(*(prepare(p, c) for p, c in entries)) if r is not None]
    print()
    if failures:
        print(f"\n{len(failures)} resume(s) failed (re-run to retry; cached work is kept):", file=sys.stderr)
        for f in failures[:10]:
            print("  -", f, file=sys.stderr)
        if not args.allow_partial:
            print("Nothing written. Re-run, or pass --allow-partial to leave the failed ones out.", file=sys.stderr)
            return 1
    if not results:
        return 1

    rng = random.Random(args.seed)
    rng.shuffle(results)  # so the file order says nothing about categories or files
    candidates, identities, leaks_found = [], {}, False
    for i, (r, anon) in enumerate(zip(results, anon_ids(len(results), rng)), 1):
        cid = f"c{i:03d}"
        verdicts = {
            v.req_id: {"verdict": v.verdict, "evidence": v.evidence}
            for v in r["judgement"].verdicts
            if v.verdict != "not_met"  # a library tag missing here is not met
        }
        cand = {
            "id": cid,
            "anonId": anon,
            "label": r["label"],
            "profile": r["profile"].model_dump(),
            "photoPresent": r["photo"],
            "redactionCount": r["redactions"],
            "summary": r["judgement"].summary,
            "verdicts": verdicts,
            "cosine": r["cosine"],
        }
        leaks = find_leaks({k: cand[k] for k in ("profile", "summary", "verdicts")}, r["identity"])
        if leaks:
            leaks_found = True
            print(f"  WARNING {anon} ({r['path'].name}): identity found in blind data: {leaks}", file=sys.stderr)
        if r["label"] == SYNTHETIC_LABEL:
            identities[cid] = {k: getattr(r["identity"], k) for k in REVEALED_FIELDS}
        candidates.append(cand)

    out_data = {
        "version": 2,
        "placeholder": False,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": f"{len(candidates) - len(identities)} resumes from the Kaggle Resume Dataset and "
                  f"{len(identities)} synthetic (fictional) resumes",
        "models": {"parse": settings.gemini_parse_model, "eval": settings.gemini_eval_model,
                   "embed": settings.gemini_embed_model},
        "semantic": {"lo": scoring.SEMANTIC_LO, "hi": scoring.SEMANTIC_HI},
        "weights": Weights().model_dump(),
        "roles": lib["roles"],
        "tags": lib["tags"],
        "candidates": candidates,
        "identities": identities,
    }
    if leaks_found and not args.allow_leaks:
        # The demo file is public: never write one that leaks identity.
        print("\nIdentity leaked into some blind profiles; nothing written. Fix the parse prompt or blind.py "
              "(or pass --allow-leaks to write anyway for debugging).", file=sys.stderr)
        return 3
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(out_data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Wrote {out}: {len(candidates)} candidates, {out.stat().st_size / 1024:.0f} KB.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=str(EVAL_DIR / "data"), help="Kaggle data folder (PDFs in one folder per category)")
    parser.add_argument("--synthetic", default=str(EVAL_DIR / "synthetic"))
    parser.add_argument("--library", default=str(EVAL_DIR / "tag_library.json"))
    parser.add_argument("--eval-pool", default=str(EVAL_DIR / "pool.json"))
    parser.add_argument("--pool", default=str(EVAL_DIR / "demo_pool.json"))
    parser.add_argument("--new-pool", action="store_true", help="Rebuild demo_pool.json even if it exists")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-resumes", type=int, default=100)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--dry-run", action="store_true", help="Show the pool and call plan; make no API calls")
    parser.add_argument("--allow-partial", action="store_true", help="Write the file even if some resumes failed")
    parser.add_argument("--allow-leaks", action="store_true", help="Write the file even if the leak check fails")
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
