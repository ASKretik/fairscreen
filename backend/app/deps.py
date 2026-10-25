"""Shared services, built once at startup and injected into routes (tests pass fakes)."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from app.cache import ParseCache
from app.config import Settings
from app.services.firestore import Store
from app.services.gemini import GeminiService

TokenVerifier = Callable[[str], dict[str, Any]]  # ID token -> decoded claims; raises if invalid


@dataclass
class Services:
    settings: Settings
    store: Store
    gemini: GeminiService
    parse_cache: ParseCache
    verify_token: TokenVerifier


def get_services(request: Request) -> Services:
    return request.app.state.services


def build_services(settings: Settings) -> Services:
    from firebase_admin import auth as firebase_auth

    from app.services.firestore import init_firestore

    store = init_firestore(settings)  # initialises the Firebase app, which auth also needs
    gemini = GeminiService(settings)
    return Services(
        settings=settings,
        store=store,
        gemini=gemini,
        parse_cache=ParseCache(gemini.parse_cache_tag),  # in memory only on the server
        verify_token=lambda token: firebase_auth.verify_id_token(token, clock_skew_seconds=10),
    )
