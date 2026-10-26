"""End-to-end run of scripts/build_demo.py on a fake Kaggle folder with a fake Gemini (no network)."""

import argparse
import asyncio
import importlib.util
import json
import re
from pathlib import Path

import pytest

from app.config import Settings
from app.models import ParsedResume, RequirementVerdict, TagJudgement
from app.services.gemini import GeminiService
from tests.test_blind import make_parsed

BACKEND = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("build_demo", BACKEND / "scripts" / "build_demo.py")
build_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_demo)

CATS = ["INFORMATION-TECHNOLOGY", "FINANCE", "HR", "CHEF", "ARTS"]


@pytest.fixture
def fake_world(tmp_path, monkeypatch):
    data = tmp_path / "data"
    for cat in CATS:
        (data / cat).mkdir(parents=True)
        for i in range(30):
            (data / cat / f"{i}.pdf").write_bytes(f"%PDF-1.4 CAT={cat} n={i}".encode())
    synthetic = tmp_path / "synthetic"
    synthetic.mkdir()
    for i in range(4):
        (synthetic / f"synthetic_{i}.pdf").write_bytes(f"%PDF-1.4 CAT=SYNTHETIC n={i}".encode())

    calls = {"parse": 0, "judge": 0, "embed": 0}

    async def fake_generate(self, *, model, contents, schema, system, temperature, limiter):
        if schema is ParsedResume:
            calls["parse"] += 1
            text = contents[0].inline_data.data.decode()
            cat = text.split("CAT=")[1].split()[0]
            parsed = make_parsed()
            parsed.profile.headline = f"Profile {cat} #{text.split('n=')[1]}"
            return parsed
        assert schema is TagJudgement and "weight" not in contents
        calls["judge"] += 1
        it = "INFORMATION-TECHNOLOGY" in re.search(r'"headline": "([^"]+)"', contents).group(1)
        return TagJudgement(
            verdicts=[RequirementVerdict(req_id="it2", verdict="met" if it else "not_met",
                                         evidence="Administered Active Directory" if it else ""),
                      RequirementVerdict(req_id="g3", verdict="partial", evidence="Led a migration project")],
            summary="Engineer with backend experience. Her focus is APIs.",
        )

    async def embed(self, text):
        calls["embed"] += 1
        return [1.0, 0.0] if text.startswith("IT Systems") else [0.8, 0.6]

    monkeypatch.setattr(GeminiService, "_generate", fake_generate)
    monkeypatch.setattr(GeminiService, "embed", embed)
    settings = Settings(gemini_api_key="k", gemini_parse_model="p", gemini_eval_model="e", cache_dir=tmp_path / "cache")
    monkeypatch.setattr(build_demo, "get_settings", lambda: settings)
    args = argparse.Namespace(
        data=str(data), synthetic=str(synthetic), library=str(BACKEND / "eval" / "tag_library.json"),
        eval_pool=str(tmp_path / "pool.json"), pool=str(tmp_path / "demo_pool.json"), new_pool=False, seed=7,
        max_resumes=100, out=str(tmp_path / "demo_pool_out.json"), dry_run=False, allow_partial=False, allow_leaks=False)
    return tmp_path, args, calls


def test_pool_is_100_resumes_and_contains_the_eval_pool(fake_world):
    tmp, args, calls = fake_world
    args.dry_run = True
    assert asyncio.run(build_demo.run(args)) == 0
    assert calls == {"parse": 0, "judge": 0, "embed": 0}
    eval_ids = {i["id"] for i in json.loads((tmp / "pool.json").read_text())["items"]}
    demo = json.loads((tmp / "demo_pool.json").read_text())["items"]
    assert len(demo) == 96 and len({i["id"] for i in demo}) == 96 and eval_ids <= {i["id"] for i in demo}
    for cat in ("INFORMATION-TECHNOLOGY", "FINANCE", "HR"):
        assert sum(i["category"] == cat for i in demo) == 24
    args.max_resumes = 99
    assert asyncio.run(build_demo.run(args)) == 2  # 96 + 4 synthetic is over the limit


def test_full_run_writes_blind_pool_with_only_synthetic_identities(fake_world):
    tmp, args, calls = fake_world
    assert asyncio.run(build_demo.run(args)) == 0
    assert calls == {"parse": 100, "judge": 100, "embed": 103}
    out = json.loads((tmp / "demo_pool_out.json").read_text())
    assert out["version"] == 2 and out["placeholder"] is False
    assert {r["id"] for r in out["roles"]} == {"it", "finance", "hr"} and len(out["tags"]) == 43
    cands = out["candidates"]
    assert len(cands) == 100 and len({c["anonId"] for c in cands}) == 100
    assert sum(c["label"] == "SYNTHETIC" for c in cands) == 4
    assert set(out["identities"]) == {c["id"] for c in cands if c["label"] == "SYNTHETIC"}
    it = next(c for c in cands if c["label"] == "INFORMATION-TECHNOLOGY")
    assert it["verdicts"]["it2"]["verdict"] == "met" and it["verdicts"]["g3"]["verdict"] == "partial"
    hr = next(c for c in cands if c["label"] == "HR")
    assert "it2" not in hr["verdicts"]  # not_met verdicts are left out
    assert it["cosine"] == {"it": 0.8, "finance": 1.0, "hr": 1.0}
    blob = json.dumps(cands)
    for needle in ("Priya", "Sharma", "priya.sharma@gmail.com", "Her focus"):
        assert needle not in blob

    # Re-running is served from the caches.
    calls.update(parse=0, judge=0)
    assert asyncio.run(build_demo.run(args)) == 0
    assert (calls["parse"], calls["judge"]) == (0, 0)
