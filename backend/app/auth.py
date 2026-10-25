"""Firebase ID-token verification (SPEC §8: every route except /health needs a Bearer token)."""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.deps import Services, get_services

# auto_error=False so a missing header is a 401 (not FastAPI's default), and Swagger gets an "Authorize" button.
_bearer = HTTPBearer(auto_error=False, description="Firebase ID token")


@dataclass(frozen=True)
class User:
    uid: str
    email: str | None = None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    services: Services = Depends(get_services),
) -> User:
    # A sync dependency, so FastAPI runs it in a thread: verify_id_token may fetch Google's certs.
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise _unauthorized("Sign in required.")
    try:
        claims = services.verify_token(creds.credentials)
    except Exception:
        raise _unauthorized("Invalid or expired sign-in token. Sign in again.") from None
    uid = claims.get("uid") or claims.get("sub")
    if not uid:
        raise _unauthorized("Invalid sign-in token.")
    return User(uid=uid, email=claims.get("email"))
