"""Retry and error handling in GeminiService, with a fake google-genai client (no network)."""

import asyncio
from types import SimpleNamespace

import pytest
from google.genai import errors

from app.config import ConfigError, Settings
from app.models import JobRequirements, Requirement
from app.services import gemini as gemini_mod
from app.services.gemini import GeminiError, GeminiService, _is_retryable, _retry_delay_hint

SETTINGS = Settings(gemini_api_key="k", gemini_parse_model="parse-model", gemini_eval_model="eval-model")


def api_error(code: int, status: str, retry_delay: str | None = None) -> errors.APIError:
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay}] if retry_delay else []
    return errors.APIError(code, {"error": {"code": code, "status": status, "message": "boom", "details": details}})


REQS = JobRequirements(
    role_title="Analyst",
    must_have=[Requirement(id="m1", text="SQL", kind="skill")],
    nice_to_have=[],
    min_years_experience=None,
    education_requirement=None,
)


class FakeModels:
    def __init__(self, failures: list[Exception]):
        self.failures = list(failures)
        self.calls = 0
        self.in_flight = 0
        self.max_in_flight = 0

    async def generate_content(self, *, model, contents, config):
        self.calls += 1
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0.01)
            if self.failures:
                raise self.failures.pop(0)
            return SimpleNamespace(parsed=REQS, text=None, candidates=None, prompt_feedback=None)
        finally:
            self.in_flight -= 1


def service(failures: list[Exception]) -> tuple[GeminiService, FakeModels]:
    models = FakeModels(failures)
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return GeminiService(SETTINGS, client=client), models


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(gemini_mod, "_wait", lambda state: 0)


def test_missing_config_fails_loudly():
    with pytest.raises(ConfigError, match="GEMINI_PARSE_MODEL"):
        GeminiService(Settings(gemini_api_key="k"), client=SimpleNamespace())


def test_retries_rate_limits_then_succeeds():
    svc, models = service([api_error(429, "RESOURCE_EXHAUSTED"), api_error(503, "UNAVAILABLE")])
    req = asyncio.run(svc.parse_jd("JD text"))
    assert models.calls == 3
    assert req.must_have[0].id == "m1"


def test_gives_up_after_five_attempts_with_readable_error():
    svc, models = service([api_error(429, "RESOURCE_EXHAUSTED")] * 10)
    with pytest.raises(GeminiError, match="rate limit"):
        asyncio.run(svc.parse_jd("JD text"))
    assert models.calls == 5


def test_client_errors_are_not_retried():
    svc, models = service([api_error(400, "INVALID_ARGUMENT")])
    with pytest.raises(GeminiError, match="400"):
        asyncio.run(svc.parse_jd("JD text"))
    assert models.calls == 1


def test_semaphore_caps_concurrency():
    svc, models = service([])

    async def many():
        await asyncio.gather(*(svc.parse_jd(f"JD {i}") for i in range(6)))

    asyncio.run(many())
    assert models.max_in_flight == SETTINGS.gemini_concurrency == 2


def test_retry_classification_and_delay_hint():
    assert _is_retryable(api_error(429, "RESOURCE_EXHAUSTED"))
    assert _is_retryable(api_error(500, "INTERNAL"))
    assert not _is_retryable(api_error(404, "NOT_FOUND"))
    assert not _is_retryable(ValueError())
    assert _retry_delay_hint(api_error(429, "RESOURCE_EXHAUSTED", "37s")) == 37.0
    assert _retry_delay_hint(api_error(429, "RESOURCE_EXHAUSTED")) == 0.0


def test_rate_limiter_spaces_calls(monkeypatch):
    from app.services.gemini import RateLimiter

    clock = {"t": 100.0}
    sleeps: list[float] = []

    async def fake_sleep(d):
        sleeps.append(round(d, 3))

    monkeypatch.setattr(gemini_mod.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(gemini_mod.asyncio, "sleep", fake_sleep)
    limiter = RateLimiter(rpm=30)  # one call every 2 s

    async def three():
        for _ in range(3):
            await limiter.wait()

    asyncio.run(three())
    assert sleeps == [2.0, 4.0]  # first call immediate, then queued 2 s apart
    assert RateLimiter(rpm=0).interval == 0.0


def test_evaluations_are_cached_on_disk_for_scripts(tmp_path):
    from app.models import CandidateEvaluation, RequirementVerdict
    from tests.test_blind import make_parsed

    ev = CandidateEvaluation(must_have=[RequirementVerdict(req_id="m1", verdict="met", evidence="SQL")],
                             nice_to_have=[], strengths=[], gaps=[], summary="Fit.")
    calls = {"n": 0}

    class Models:
        async def generate_content(self, *, model, contents, config):
            calls["n"] += 1
            return SimpleNamespace(parsed=ev, text=None, candidates=None, prompt_feedback=None)

    client = SimpleNamespace(aio=SimpleNamespace(models=Models()))
    profile = make_parsed().profile
    for _ in range(2):
        svc = GeminiService(SETTINGS, client=client, disk_cache_dir=tmp_path)
        out = asyncio.run(svc.evaluate(profile, REQS))
        assert out.must_have[0].verdict == "met"
    assert calls["n"] == 1
