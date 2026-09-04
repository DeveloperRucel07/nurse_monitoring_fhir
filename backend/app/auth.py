from __future__ import annotations

import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from jose import JWTError, jwt

from backend.app.core.bff_session import (
    COOKIE_SECURE,
    LOGIN_COOKIE_NAME,
    OIDC_CLIENT_ID,
    OIDC_CLIENT_SECRET,
    OIDC_TOKEN_URL,
    SESSION_COOKIE_NAME,
    SessionUnavailableError,
    code_challenge,
    consume_login_flow,
    create_login_flow,
    create_session,
    delete_session,
    load_session,
)
from backend.app.core.config import APP_ORIGIN, ML_MODE
from backend.app.core.security import client_roles, get_key_for_token, verify_token

OIDC_AUTHORIZATION_URL = os.getenv(
    "OIDC_AUTHORIZATION_URL",
    "http://localhost:8081/realms/health-interop/protocol/openid-connect/auth",
)
OIDC_ISSUER = os.getenv(
    "KEYCLOAK_ISSUER", "http://localhost:8081/realms/health-interop"
).rstrip("/")
OIDC_LOGOUT_URL = os.getenv(
    "OIDC_LOGOUT_URL",
    "http://localhost:8081/realms/health-interop/protocol/openid-connect/logout",
)
REDIRECT_URI = f"{APP_ORIGIN}/auth/callback"

auth_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"


def _safe_return_to(value: str | None) -> str:
    candidate = value or "/"
    parsed = urlsplit(candidate)
    if (
        parsed.scheme
        or parsed.netloc
        or not candidate.startswith("/")
        or candidate.startswith("//")
        or "\\" in candidate
    ):
        return "/"
    return candidate if candidate in {"/", "/patients", "/patient"} else "/"


def _session_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Der Sitzungsdienst ist momentan nicht erreichbar.",
    )


def _load_request_session(request: Request) -> tuple[str, dict[str, Any]]:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="Anmeldung erforderlich.")
    try:
        session = load_session(session_id)
    except SessionUnavailableError as exc:
        raise _session_error() from exc
    if session is None:
        raise HTTPException(status_code=401, detail="Die Sitzung ist abgelaufen.")
    return session_id, session


def _revoke_refresh_token(session_data: dict[str, Any]) -> None:
    token = session_data.get("token")
    refresh_token = token.get("refresh_token") if isinstance(token, dict) else None
    if not isinstance(refresh_token, str) or not OIDC_CLIENT_SECRET:
        return
    try:
        httpx.post(
            OIDC_LOGOUT_URL,
            data={
                "client_id": OIDC_CLIENT_ID,
                "client_secret": OIDC_CLIENT_SECRET,
                "refresh_token": refresh_token,
            },
            timeout=5,
        )
    except httpx.HTTPError:
        # Die lokale Sitzung wird trotzdem zwingend beendet.
        return


def _verify_id_token(
    id_token: str,
    access_token: str,
    expected_nonce: str,
    expected_subject: object,
) -> dict[str, Any]:
    """Prüft ID-Token einschließlich OIDC-at_hash und Browser-Nonce."""
    try:
        claims = jwt.decode(
            id_token,
            get_key_for_token(id_token),
            algorithms=["RS256"],
            audience=OIDC_CLIENT_ID,
            issuer=OIDC_ISSUER,
            access_token=access_token,
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Ungültige Anmeldung.") from exc
    if claims.get("nonce") != expected_nonce or claims.get("sub") != expected_subject:
        raise HTTPException(status_code=401, detail="Ungültige Anmeldung.")
    return claims


@auth_app.get("/login")
def login(return_to: str | None = None):
    if not OIDC_CLIENT_SECRET:
        raise _session_error()
    browser_binding = secrets.token_urlsafe(32)
    try:
        state, nonce, verifier = create_login_flow(
            _safe_return_to(return_to),
            browser_binding,
        )
    except SessionUnavailableError as exc:
        raise _session_error() from exc
    query = urlencode(
        {
            "client_id": OIDC_CLIENT_ID,
            "response_type": "code",
            "scope": "openid profile",
            "redirect_uri": REDIRECT_URI,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    response = RedirectResponse(f"{OIDC_AUTHORIZATION_URL}?{query}", status_code=302)
    response.set_cookie(
        LOGIN_COOKIE_NAME,
        browser_binding,
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=300,
    )
    _no_store(response)
    return response


@auth_app.get("/callback")
def callback(request: Request, code: str, state: str):
    browser_binding = request.cookies.get(LOGIN_COOKIE_NAME)
    if not browser_binding:
        raise HTTPException(status_code=400, detail="Ungültiger Anmeldevorgang.")
    try:
        flow = consume_login_flow(state)
    except SessionUnavailableError as exc:
        raise _session_error() from exc
    if flow is None:
        raise HTTPException(status_code=400, detail="Ungültiger Anmeldevorgang.")
    expected_binding = flow.get("browser_binding")
    if not isinstance(expected_binding, str) or not secrets.compare_digest(
        browser_binding,
        expected_binding,
    ):
        raise HTTPException(status_code=400, detail="Ungültiger Anmeldevorgang.")
    verifier = flow.get("verifier")
    nonce = flow.get("nonce")
    if not isinstance(verifier, str) or not isinstance(nonce, str):
        raise HTTPException(status_code=400, detail="Ungültiger Anmeldevorgang.")
    try:
        token_response = httpx.post(
            OIDC_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": OIDC_CLIENT_ID,
                "client_secret": OIDC_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "code": code,
                "code_verifier": verifier,
            },
            timeout=10,
        )
        token_response.raise_for_status()
        token = token_response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail="Anmeldung fehlgeschlagen."
        ) from exc
    if not isinstance(token, dict):
        raise HTTPException(status_code=502, detail="Anmeldung fehlgeschlagen.")
    access_token = token.get("access_token")
    id_token = token.get("id_token")
    if not isinstance(access_token, str) or not isinstance(id_token, str):
        raise HTTPException(status_code=502, detail="Anmeldung fehlgeschlagen.")

    access_claims = verify_token(access_token)
    _verify_id_token(
        id_token,
        access_token,
        nonce,
        access_claims.get("sub"),
    )

    token["obtained_at"] = int(time.time())
    try:
        session_id, _csrf_token = create_session(token)
    except SessionUnavailableError as exc:
        raise _session_error() from exc
    response = RedirectResponse(str(flow.get("return_to") or "/"), status_code=303)
    response.delete_cookie(
        LOGIN_COOKIE_NAME,
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=None,
    )
    _no_store(response)
    return response


@auth_app.get("/session")
def session(request: Request):
    _session_id, session_data = _load_request_session(request)
    token = session_data.get("token")
    access_token = token.get("access_token") if isinstance(token, dict) else None
    if not isinstance(access_token, str):
        raise HTTPException(status_code=401, detail="Die Sitzung ist ungültig.")
    claims = verify_token(access_token)
    roles = client_roles(claims)
    display_name = (
        claims.get("name") or claims.get("preferred_username") or "Angemeldet"
    )
    response = JSONResponse(
        {
            "authenticated": True,
            "user": {"displayName": str(display_name)[:200]},
            "capabilities": {
                "canRead": not roles.isdisjoint(
                    {"pflege_read", "pflege_write", "pflege_delete", "pflege_admin"}
                ),
                "canWrite": not roles.isdisjoint({"pflege_write", "pflege_admin"}),
                "canDelete": not roles.isdisjoint({"pflege_delete", "pflege_admin"}),
            },
            "csrfToken": session_data.get("csrf_token"),
            "features": {"experimentalMl": ML_MODE == "synthetic-demo"},
        }
    )
    _no_store(response)
    return response


@auth_app.post("/logout", status_code=204)
def logout(request: Request, x_csrf_token: str = Header(default="")):
    session_id, session_data = _load_request_session(request)
    expected = session_data.get("csrf_token")
    if (
        request.headers.get("Origin") != APP_ORIGIN
        or not isinstance(expected, str)
        or not secrets.compare_digest(x_csrf_token, expected)
    ):
        raise HTTPException(status_code=403, detail="Ungültige Sicherheitsprüfung.")
    try:
        delete_session(session_id)
    except SessionUnavailableError as exc:
        raise _session_error() from exc
    _revoke_refresh_token(session_data)
    response = Response(status_code=204)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    _no_store(response)
    return response
