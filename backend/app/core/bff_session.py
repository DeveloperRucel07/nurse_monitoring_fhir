from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from typing import Any

import httpx
import redis
from cryptography.fernet import Fernet, InvalidToken

COOKIE_SECURE = os.getenv("BFF_COOKIE_SECURE", "true").lower() == "true"
SESSION_COOKIE_NAME = (
    "__Host-monitoring_session" if COOKIE_SECURE else "monitoring_session"
)
LOGIN_COOKIE_NAME = "__Host-monitoring_login" if COOKIE_SECURE else "monitoring_login"
SESSION_IDLE_SECONDS = int(os.getenv("BFF_SESSION_IDLE_SECONDS", "1800"))
SESSION_ABSOLUTE_SECONDS = int(os.getenv("BFF_SESSION_ABSOLUTE_SECONDS", "28800"))
REDIS_URL = os.getenv("BFF_REDIS_URL", "redis://localhost:6379/0")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "monitoring-frontend")
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "")
OIDC_TOKEN_URL = os.getenv(
    "OIDC_TOKEN_URL",
    "http://localhost:8081/realms/health-interop/protocol/openid-connect/token",
)


class SessionUnavailableError(RuntimeError):
    pass


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(
        REDIS_URL,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=False,
    )


def _cipher() -> Fernet:
    configured = os.getenv("BFF_SESSION_ENCRYPTION_KEY", "")
    if not configured:
        raise SessionUnavailableError("Session encryption is not configured.")
    try:
        return Fernet(configured.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise SessionUnavailableError("Session encryption is invalid.") from exc


def _key(prefix: str, identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    return f"monitoring:{prefix}:{digest}"


def _encode(payload: dict[str, Any]) -> bytes:
    serialized = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return _cipher().encrypt(serialized)


def _decode(value: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(_cipher().decrypt(value))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write(prefix: str, identifier: str, payload: dict[str, Any], ttl: int) -> None:
    try:
        _redis_client().setex(_key(prefix, identifier), ttl, _encode(payload))
    except redis.RedisError as exc:
        raise SessionUnavailableError("Session store is unavailable.") from exc


def _read(
    prefix: str, identifier: str, *, delete: bool = False
) -> dict[str, Any] | None:
    client = _redis_client()
    key = _key(prefix, identifier)
    try:
        value = client.getdel(key) if delete else client.get(key)
    except redis.RedisError as exc:
        raise SessionUnavailableError("Session store is unavailable.") from exc
    if not isinstance(value, bytes):
        return None
    payload = _decode(value)
    if payload is None:
        try:
            client.delete(key)
        except redis.RedisError:
            pass
    return payload


def create_login_flow(return_to: str, browser_binding: str) -> tuple[str, str, str]:
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    _write(
        "flow",
        state,
        {
            "nonce": nonce,
            "verifier": verifier,
            "return_to": return_to,
            "browser_binding": browser_binding,
        },
        300,
    )
    return state, nonce, verifier


def consume_login_flow(state: str) -> dict[str, Any] | None:
    return _read("flow", state, delete=True)


def create_session(token: dict[str, Any]) -> tuple[str, str]:
    now = int(time.time())
    session_id = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    payload = {
        "created_at": now,
        "absolute_expires_at": now + SESSION_ABSOLUTE_SECONDS,
        "csrf_token": csrf_token,
        "token": token,
    }
    _write("session", session_id, payload, SESSION_IDLE_SECONDS)
    return session_id, csrf_token


def delete_session(session_id: str) -> None:
    try:
        _redis_client().delete(_key("session", session_id))
    except redis.RedisError as exc:
        raise SessionUnavailableError("Session store is unavailable.") from exc


def _refresh_token(token: dict[str, Any]) -> dict[str, Any] | None:
    refresh_token = token.get("refresh_token")
    if not isinstance(refresh_token, str) or not OIDC_CLIENT_SECRET:
        return None
    try:
        response = httpx.post(
            OIDC_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": OIDC_CLIENT_ID,
                "client_secret": OIDC_CLIENT_SECRET,
                "refresh_token": refresh_token,
            },
            timeout=10,
        )
        response.raise_for_status()
        refreshed = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(refreshed, dict) or not isinstance(
        refreshed.get("access_token"), str
    ):
        return None
    if "refresh_token" not in refreshed:
        refreshed["refresh_token"] = refresh_token
    refreshed["obtained_at"] = int(time.time())
    return refreshed


def load_session(session_id: str) -> dict[str, Any] | None:
    payload = _read("session", session_id)
    if payload is None:
        return None
    now = int(time.time())
    absolute_expires_at = payload.get("absolute_expires_at")
    if not isinstance(absolute_expires_at, int) or absolute_expires_at <= now:
        delete_session(session_id)
        return None

    token = payload.get("token")
    if not isinstance(token, dict):
        delete_session(session_id)
        return None
    obtained_at = token.get("obtained_at", payload.get("created_at", now))
    expires_in = token.get("expires_in", 0)
    if not isinstance(obtained_at, int) or not isinstance(expires_in, int):
        delete_session(session_id)
        return None
    if obtained_at + expires_in <= now + 30:
        refreshed = _refresh_token(token)
        if refreshed is None:
            delete_session(session_id)
            return None
        payload["token"] = refreshed

    ttl = min(SESSION_IDLE_SECONDS, absolute_expires_at - now)
    _write("session", session_id, payload, ttl)
    return payload


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
