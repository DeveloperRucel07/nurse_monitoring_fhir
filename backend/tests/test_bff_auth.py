from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt
from starlette.requests import Request

from backend.app import auth
from backend.app.core import security


def test_login_uses_pkce_and_rejects_external_return_url(monkeypatch) -> None:
    monkeypatch.setattr(auth, "OIDC_CLIENT_SECRET", "test-secret")
    captured: dict[str, str] = {}

    def create_flow(return_to: str, browser_binding: str):
        captured["return_to"] = return_to
        captured["browser_binding"] = browser_binding
        return "state-value", "nonce-value", "verifier-value"

    monkeypatch.setattr(auth, "create_login_flow", create_flow)
    response = TestClient(auth.auth_app).get(
        "/login?return_to=https://attacker.invalid/patient",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert captured["return_to"] == "/"
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["nonce"] == ["nonce-value"]
    assert query["state"] == ["state-value"]
    assert "access_token" not in response.headers["location"]
    assert captured["browser_binding"] in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_session_exposes_capabilities_but_no_oauth_tokens(monkeypatch) -> None:
    monkeypatch.setattr(
        auth,
        "load_session",
        lambda _session_id: {
            "csrf_token": "csrf-value-with-sufficient-length",
            "token": {
                "access_token": "secret-access-token",
                "refresh_token": "secret-refresh-token",
            },
        },
    )
    monkeypatch.setattr(
        auth,
        "verify_token",
        lambda _token: {
            "sub": "user-1",
            "name": "Pflege Test",
            "resource_access": {security.API_AUDIENCE: {"roles": ["pflege_read"]}},
        },
    )
    client = TestClient(auth.auth_app)
    client.cookies.set(auth.SESSION_COOKIE_NAME, "opaque-session-id")

    response = client.get("/session")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["capabilities"]["canRead"] is True
    assert "access_token" not in response.text
    assert "refresh_token" not in response.text


def test_session_authenticated_mutation_requires_origin_and_csrf(monkeypatch) -> None:
    session = {
        "csrf_token": "expected-csrf",
        "token": {"access_token": "server-only-token"},
    }
    monkeypatch.setattr(security, "load_session", lambda _session_id: session)
    monkeypatch.setattr(security, "verify_token", lambda _token: {"sub": "user-1"})
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/ui/patients/search",
        "headers": [(b"cookie", f"{security.SESSION_COOKIE_NAME}=opaque".encode())],
    }

    with pytest.raises(HTTPException) as exc_info:
        security.get_current_client(Request(scope), None)

    assert exc_info.value.status_code == 403


def test_session_authenticated_mutation_accepts_bound_csrf(monkeypatch) -> None:
    session = {
        "csrf_token": "expected-csrf",
        "token": {"access_token": "server-only-token"},
    }
    monkeypatch.setattr(security, "load_session", lambda _session_id: session)
    monkeypatch.setattr(security, "verify_token", lambda _token: {"sub": "user-1"})
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/ui/patients/search",
        "headers": [
            (b"cookie", f"{security.SESSION_COOKIE_NAME}=opaque".encode()),
            (b"origin", security.APP_ORIGIN.encode()),
            (b"x-csrf-token", b"expected-csrf"),
        ],
    }

    claims = security.get_current_client(Request(scope), None)

    assert claims["sub"] == "user-1"


def test_id_token_verification_includes_access_token_hash_binding(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(auth, "get_key_for_token", lambda _token: {"kid": "test"})

    def decode(_token, _key, **kwargs):
        captured.update(kwargs)
        return {"sub": "user-1", "nonce": "expected-nonce"}

    monkeypatch.setattr(auth.jwt, "decode", decode)

    result = auth._verify_id_token(
        "id-token",
        "access-token",
        "expected-nonce",
        "user-1",
    )

    assert result["sub"] == "user-1"
    assert captured["access_token"] == "access-token"
    assert captured["audience"] == auth.OIDC_CLIENT_ID
    assert captured["issuer"] == auth.OIDC_ISSUER


def test_id_token_with_real_at_hash_is_accepted(monkeypatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    access_token = "opaque-access-token-for-hash-binding"
    digest = hashlib.sha256(access_token.encode("ascii")).digest()
    at_hash = base64.urlsafe_b64encode(digest[: len(digest) // 2]).rstrip(b"=").decode()
    now = datetime.now(timezone.utc)
    id_token = jwt.encode(
        {
            "iss": auth.OIDC_ISSUER,
            "aud": auth.OIDC_CLIENT_ID,
            "sub": "user-1",
            "nonce": "expected-nonce",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "at_hash": at_hash,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test"},
    )
    monkeypatch.setattr(auth, "get_key_for_token", lambda _token: public_pem)

    claims = auth._verify_id_token(
        id_token,
        access_token,
        "expected-nonce",
        "user-1",
    )

    assert claims["sub"] == "user-1"
