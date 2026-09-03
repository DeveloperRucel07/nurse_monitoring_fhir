from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt


KEYCLOAK_JWKS_URL = os.getenv(
    "KEYCLOAK_JWKS_URL",
    "http://localhost:8081/realms/health-interop/protocol/openid-connect/certs",
).rstrip("/")
KEYCLOAK_ISSUER = os.getenv(
    "KEYCLOAK_ISSUER",
    "http://localhost:8081/realms/health-interop",
).rstrip("/")
API_AUDIENCE = os.getenv("KEYCLOAK_API_AUDIENCE", "monitoring-pflege-api")
ALLOWED_CLIENT_ID = os.getenv("KEYCLOAK_ALLOWED_CLIENT_ID", "monitoring-frontend")
JWKS_TIMEOUT_SECONDS = float(os.getenv("KEYCLOAK_JWKS_TIMEOUT", "5"))
JWKS_CACHE_TTL_SECONDS = int(os.getenv("KEYCLOAK_JWKS_CACHE_TTL", "300"))

READ_ROLES = frozenset({"pflege_read", "pflege_write", "pflege_delete", "pflege_admin"})
WRITE_ROLES = frozenset({"pflege_write", "pflege_admin"})
DELETE_ROLES = frozenset({"pflege_delete", "pflege_admin"})

bearer_scheme = HTTPBearer(auto_error=False)

_jwks_cache: dict[str, Any] | None = None
_jwks_cache_expires_at = 0.0
_jwks_lock = threading.Lock()


def _authentication_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _load_public_keys(*, force_refresh: bool = False) -> dict[str, Any]:
    global _jwks_cache, _jwks_cache_expires_at

    now = time.monotonic()
    if not force_refresh and _jwks_cache is not None and now < _jwks_cache_expires_at:
        return _jwks_cache

    with _jwks_lock:
        now = time.monotonic()
        if not force_refresh and _jwks_cache is not None and now < _jwks_cache_expires_at:
            return _jwks_cache

        try:
            response = httpx.get(KEYCLOAK_JWKS_URL, timeout=JWKS_TIMEOUT_SECONDS)
            response.raise_for_status()
            jwks = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Der Anmeldedienst ist momentan nicht erreichbar.",
            ) from exc

        if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Der Anmeldedienst hat ungültige Schlüsseldaten geliefert.",
            )

        _jwks_cache = jwks
        _jwks_cache_expires_at = now + JWKS_CACHE_TTL_SECONDS
        return jwks


def get_key_for_token(token: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise _authentication_error("Ungültiges Zugriffstoken.") from exc

    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise _authentication_error("Das Zugriffstoken enthält keine Schlüssel-ID.")

    for force_refresh in (False, True):
        jwks = _load_public_keys(force_refresh=force_refresh)
        for key in jwks["keys"]:
            if isinstance(key, dict) and key.get("kid") == kid:
                return key

    raise _authentication_error("Der Signaturschlüssel des Zugriffstokens ist unbekannt.")


def verify_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            get_key_for_token(token),
            algorithms=["RS256"],
            audience=API_AUDIENCE,
            issuer=KEYCLOAK_ISSUER,
        )
    except HTTPException:
        raise
    except JWTError as exc:
        raise _authentication_error("Ungültiges oder abgelaufenes Zugriffstoken.") from exc

    if payload.get("typ") != "Bearer":
        raise _authentication_error("Für diese API ist ein Access-Token erforderlich.")
    if payload.get("azp") != ALLOWED_CLIENT_ID:
        raise _authentication_error("Das Zugriffstoken wurde nicht für diesen Client ausgestellt.")
    if not isinstance(payload.get("sub"), str):
        raise _authentication_error("Das Zugriffstoken enthält keine Benutzeridentität.")
    return payload


def get_current_client(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_error("Anmeldung erforderlich.")

    payload = verify_token(credentials.credentials)
    request.state.user_claims = payload
    return payload


def client_roles(payload: dict[str, Any]) -> frozenset[str]:
    resource_access = payload.get("resource_access")
    if not isinstance(resource_access, dict):
        return frozenset()
    api_access = resource_access.get(API_AUDIENCE)
    if not isinstance(api_access, dict):
        return frozenset()
    roles = api_access.get("roles")
    if not isinstance(roles, list):
        return frozenset()
    return frozenset(role for role in roles if isinstance(role, str))


def require_roles(allowed_roles: frozenset[str]) -> Callable[..., dict[str, Any]]:
    def authorize(
        payload: dict[str, Any] = Depends(get_current_client),
    ) -> dict[str, Any]:
        if client_roles(payload).isdisjoint(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Für diese Aktion fehlt die erforderliche Berechtigung.",
            )
        return payload

    return authorize


require_read_access = require_roles(READ_ROLES)
require_write_access = require_roles(WRITE_ROLES)
require_delete_access = require_roles(DELETE_ROLES)
