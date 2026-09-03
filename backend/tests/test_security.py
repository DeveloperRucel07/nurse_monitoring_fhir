from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt

from backend.app import main
from backend.app.core import security


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    main.app.dependency_overrides.clear()
    yield
    main.app.dependency_overrides.clear()


def claims(*roles: str) -> dict:
    return {
        "sub": "test-user",
        "preferred_username": "pflege.test",
        "azp": security.ALLOWED_CLIENT_ID,
        "resource_access": {
            security.API_AUDIENCE: {"roles": list(roles)},
        },
    }


def test_anonymous_request_cannot_read_patient_data():
    response = TestClient(main.app).get("/Patient")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_reader_can_read_but_cannot_create(monkeypatch):
    class FakeFhir:
        def search_patients(self, **_kwargs):
            return {"resourceType": "Bundle", "entry": []}

    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_read"
    )
    monkeypatch.setattr(main, "fhir", FakeFhir())
    client = TestClient(main.app)

    read_response = client.get("/Patient")
    write_response = client.post(
        "/Patient",
        json={
            "name": [{"family": "Test", "given": ["Tina"]}],
            "gender": "female",
            "birthDate": "1980-01-01",
        },
    )

    assert read_response.status_code == 200
    assert write_response.status_code == 403


def test_writer_cannot_delete_patient():
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_write"
    )

    response = TestClient(main.app).delete("/Patient/123")

    assert response.status_code == 403


def test_verify_token_checks_signature_issuer_audience_and_client(monkeypatch):
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
    now = datetime.now(timezone.utc)
    payload = {
        **claims("pflege_read"),
        "typ": "Bearer",
        "iss": security.KEYCLOAK_ISSUER,
        "aud": security.API_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    token = jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": "test"})
    monkeypatch.setattr(security, "get_key_for_token", lambda _token: public_pem)

    verified = security.verify_token(token)

    assert verified["sub"] == "test-user"


def test_verify_token_rejects_wrong_audience(monkeypatch):
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
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            **claims("pflege_read"),
            "typ": "Bearer",
            "iss": security.KEYCLOAK_ISSUER,
            "aud": "some-other-api",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test"},
    )
    monkeypatch.setattr(security, "get_key_for_token", lambda _token: public_pem)

    with pytest.raises(HTTPException) as exc_info:
        security.verify_token(token)

    assert exc_info.value.status_code == 401
