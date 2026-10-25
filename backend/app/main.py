"""FastAPI app (SPEC §8). Render start command: uvicorn app.main:app --host 0.0.0.0 --port $PORT"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.formparsers import MultiPartParser
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings
from app.deps import Services, build_services
from app.routers import candidates, jobs
from app.services.pipeline import sweep_stale

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("fairscreen")

MB = 1024 * 1024


class UploadSizeLimit:
    """Reject oversized uploads from Content-Length, before the body is read or parsed."""

    def __init__(self, app: ASGIApp, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"].endswith("/resumes"):
            length = dict(scope["headers"]).get(b"content-length")
            if length and length.isdigit() and int(length) > self.max_bytes:
                response = JSONResponse({"detail": "Upload is too large."}, status_code=413)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(services: Services | None = None) -> FastAPI:
    settings = services.settings if services else get_settings()

    # Keep every uploaded PDF in memory: Starlette otherwise spools parts over 1 MB to a
    # temp file on disk, and raw resumes must never be stored (SPEC §4, §13).
    MultiPartParser.spool_max_size = (settings.max_file_mb + 1) * MB

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.services is None:
            app.state.services = build_services(settings)
        try:
            await sweep_stale(app.state.services)
        except Exception:
            log.exception("stale-processing sweep failed")
        yield

    app = FastAPI(title="FairScreen API", version="1.0", lifespan=lifespan)
    app.state.services = services
    app.add_middleware(UploadSizeLimit, max_bytes=settings.max_files_per_upload * settings.max_file_mb * MB + MB)
    # Added last, so it is outermost and its headers are on every response, errors included.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(jobs.router)
    app.include_router(candidates.router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, bool]:
        return {"ok": True}

    return app


app = create_app()
