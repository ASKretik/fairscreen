"""Settings from environment variables (SPEC §12). Locally they come from backend/.env."""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    pass


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = ""
    gemini_parse_model: str = ""
    gemini_eval_model: str = ""
    gemini_embed_model: str = "gemini-embedding-001"
    gemini_concurrency: int = 2
    # Optional requests-per-minute caps (0 = no cap), from the AI Studio rate-limit page.
    gemini_parse_rpm: int = 0
    gemini_eval_rpm: int = 0
    gemini_embed_rpm: int = 0
    firebase_service_account_b64: str = ""
    allowed_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    max_files_per_upload: int = 20
    max_file_mb: int = 5
    max_candidates_per_job: int = 50
    cache_dir: Path = BACKEND_DIR / ".cache"

    def require_gemini(self) -> None:
        """Model IDs are never hard-coded (SPEC §3), so fail loudly if they are missing."""
        missing = [
            name
            for name, value in (
                ("GEMINI_API_KEY", self.gemini_api_key),
                ("GEMINI_PARSE_MODEL", self.gemini_parse_model),
                ("GEMINI_EVAL_MODEL", self.gemini_eval_model),
                ("GEMINI_EMBED_MODEL", self.gemini_embed_model),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                f"Missing environment variables: {', '.join(missing)}. "
                "Copy backend/.env.example to backend/.env and fill them in."
            )


@lru_cache
def get_settings() -> Settings:
    load_dotenv(BACKEND_DIR / ".env")  # no-op on Render, where real env vars are set
    origins = os.getenv("ALLOWED_ORIGINS", "").strip()
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_parse_model=os.getenv("GEMINI_PARSE_MODEL", "").strip(),
        gemini_eval_model=os.getenv("GEMINI_EVAL_MODEL", "").strip(),
        gemini_embed_model=os.getenv("GEMINI_EMBED_MODEL", "").strip() or "gemini-embedding-001",
        gemini_concurrency=max(1, _int("GEMINI_CONCURRENCY", 2)),
        gemini_parse_rpm=max(0, _int("GEMINI_PARSE_RPM", 0)),
        gemini_eval_rpm=max(0, _int("GEMINI_EVAL_RPM", 0)),
        gemini_embed_rpm=max(0, _int("GEMINI_EMBED_RPM", 0)),
        firebase_service_account_b64=os.getenv("FIREBASE_SERVICE_ACCOUNT_B64", "").strip(),
        allowed_origins=[o.strip() for o in origins.split(",") if o.strip()] or ["http://localhost:5173"],
        max_files_per_upload=_int("MAX_FILES_PER_UPLOAD", 20),
        max_file_mb=_int("MAX_FILE_MB", 5),
        max_candidates_per_job=_int("MAX_CANDIDATES_PER_JOB", 50),
    )
