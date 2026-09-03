from __future__ import annotations

import pytest
import requests

from frontend.infrastructure.api_client import ApiError, FhirApiClient


def test_client_requires_an_authenticated_access_token():
    with pytest.raises(ApiError, match="Anmeldung erforderlich"):
        FhirApiClient(token=None)


def test_client_forwards_access_token(monkeypatch):
    captured = {}

    class Response:
        content = b'{"resourceType":"Bundle"}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"resourceType": "Bundle"}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return Response()

    monkeypatch.setattr(requests, "request", fake_request)
    client = FhirApiClient(base_url="http://backend:8000", token="access-token")

    response = client.list_patients()

    assert response["resourceType"] == "Bundle"
    assert captured["headers"]["Authorization"] == "Bearer access-token"


def test_client_explains_missing_role(monkeypatch):
    response = requests.Response()
    response.status_code = 403
    response._content = b'{"detail":"forbidden"}'

    monkeypatch.setattr(requests, "request", lambda *_args, **_kwargs: response)
    client = FhirApiClient(token="access-token")

    with pytest.raises(ApiError, match="Berechtigung"):
        client.list_patients()
