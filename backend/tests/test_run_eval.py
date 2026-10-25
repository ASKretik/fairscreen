"""End-to-end run of eval/run_eval.py on a fake Kaggle folder with a fake Gemini (no network)."""

import argparse
import asyncio
import json
import re

import pytest

from app.config import Settings
from app.models import CandidateEvaluation, JobRequirements, ParsedResume, RequirementVerdict
from app.services.gemini import GeminiService
from eval import run_eval
from tests.fakes import FAKE_REQS
from tests.test_blind import make_parsed

CATS = ["INFORMATION-TECHNOLOGY", "FINANCE", "HR", "CHEF", "ARTS"]


@pytest.fixture
def fake_world(tmp_path, monkeypatch):
    data = tmp_path / "data"
    for cat in CATS:
        (data / cat).mkdir(parents=True)
        for i in range(10):
            (data / cat / f"{cat.lower()}_{i}.pdf").write_bytes(f"%PDF-1.4 CAT={cat} n={i}".encode())
    jds = tmp_path / "jds"
    jds.mkdir()
    for stem, cat in [("information-technology", "INFORMATION-TECHNOLOGY"), ("finance", "FINANCE"), ("hr", "HR")]:
        (jds / f"{stem}.txt").write_text(f"{cat} role")

    calls = {"parse": 0, "eval": 0}

    # Fake only the raw model call, so GeminiService's own caching (JD, evaluation) runs for real.
    async def fake_generate(self, *, model, contents, schema, system, temperature, limiter):
        if schema is ParsedResume:
            calls["parse"] += 1
            parsed = make_parsed()
            text = contents[0].inline_data.data.decode()
            parsed.profile.headline = f"marker {text.split('CAT=')[1].split()[0]} #{text.split('n=')[1]}"  # unique per resume
            return parsed
        if schema is JobRequirements:
            return FAKE_REQS.model_copy(update={"role_title": contents.split("\n\n", 1)[1].split()[0]})
        calls["eval"] += 1
        role = re.search(r'"role_title": "([^"]+)"', contents).group(1)
        headline = re.search(r'"headline": "([^"]+)"', contents).group(1)
        verdict = "met" if role in headline else "not_met"
        return CandidateEvaluation(
            must_have=[RequirementVerdict(req_id=r.id, verdict=verdict, evidence="x" if verdict == "met" else "")
                       for r in FAKE_REQS.must_have],
            nice_to_have=[], strengths=[], gaps=[], summary="s")

    async def embed(self, text):
        return [1.0, 0.0] if "Must have" in text else [0.8, 0.6]

    monkeypatch.setattr(GeminiService, "_generate", fake_generate)
    monkeypatch.setattr(GeminiService, "embed", embed)
    settings = Settings(gemini_api_key="k", gemini_parse_model="p", gemini_eval_model="e", cache_dir=tmp_path / "cache")
    monkeypatch.setattr(run_eval, "get_settings", lambda: settings)
    args = argparse.Namespace(
        data=str(data), jds=[str(p) for p in sorted(jds.glob("*.txt"))], jd_category=[], per_category=8, others=6,
        seed=7, pool=str(tmp_path / "pool.json"), new_pool=False, out=str(tmp_path / "results"), dry_run=False)
    return tmp_path, args, calls


def test_full_run_writes_outputs_and_scores_correctly(fake_world):
    tmp, args, calls = fake_world
    assert asyncio.run(run_eval.run(args)) == 0

    pool = json.loads((tmp / "pool.json").read_text())
    assert len(pool["items"]) == 30 and pool["seed"] == 7
    per_cat = {c: sum(i["category"] == c for i in pool["items"]) for c in CATS}
    assert per_cat["FINANCE"] == per_cat["HR"] == per_cat["INFORMATION-TECHNOLOGY"] == 8
    assert per_cat["CHEF"] + per_cat["ARTS"] == 6

    metrics = json.loads((tmp / "results" / "metrics.json").read_text())
    req = metrics["mean"]["requirements"]
    assert req["p@5"] == 1.0 and req["p@10"] == pytest.approx(0.8) and req["ndcg@10"] == pytest.approx(1.0)
    assert set(metrics["mean"]) == {"semantic", "requirements", "combined", "combined_calibrated"}
    assert metrics["calibration"]["n_pairs"] == 90
    assert (tmp / "results" / "ablation_chart.svg").read_text().startswith("<svg")
    assert "| Requirements only" in (tmp / "results" / "ablation.md").read_text()
    assert len((tmp / "results" / "scores.csv").read_text().strip().splitlines()) == 91
    assert calls == {"parse": 30, "eval": 90}


def test_rerun_is_resumable_from_cache_and_keeps_the_pool(fake_world):
    tmp, args, calls = fake_world
    asyncio.run(run_eval.run(args))
    first_pool = (tmp / "pool.json").read_text()
    asyncio.run(run_eval.run(args))
    assert (tmp / "pool.json").read_text() == first_pool
    assert calls == {"parse": 30, "eval": 90}  # second run: everything from the disk caches


def test_dry_run_makes_no_calls(fake_world):
    tmp, args, calls = fake_world
    args.dry_run = True
    assert asyncio.run(run_eval.run(args)) == 0
    assert calls == {"parse": 0, "eval": 0}
    assert (tmp / "pool.json").exists()
