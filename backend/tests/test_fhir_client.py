from __future__ import annotations

import json

import pytest
import requests

from backend.app.core.exceptions import (
    FhirBadGatewayError,
    FhirNotFoundError,
    FhirTimeoutError,
    FhirValidationError,
)
from backend.app.fhir_ml.fhir.FHIRclient import FHIRClient


def response(status_code: int, payload: dict | None = None) -> requests.Response:
    result = requests.Response()
    result.status_code = status_code
    result.headers["Content-Type"] = "application/fhir+json; charset=UTF-8"
    result._content = b"" if payload is None else json.dumps(payload).encode()
    result._content_consumed = True
    return result


class FakeSession:
    def __init__(self, responses: list[requests.Response | Exception]) -> None:
        self.headers: dict[str, str] = {}
        self.responses = responses
        self.calls: list[tuple[str, str, dict]] = []
        self.adapters = {}

    def mount(self, prefix: str, adapter) -> None:
        self.adapters[prefix] = adapter

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        current = self.responses.pop(0)
        if isinstance(current, Exception):
            raise current
        return current


def test_create_validates_with_hapi_before_writing() -> None:
    session = FakeSession(
        [
            response(200, {"resourceType": "OperationOutcome", "issue": []}),
            response(201, {"resourceType": "Patient", "id": "123"}),
        ]
    )
    client = FHIRClient(base_url="http://hapi/fhir", session=session)
    patient = {"resourceType": "Patient", "name": [{"family": "Test"}]}

    created = client.create_patient(patient)

    assert created["id"] == "123"
    assert session.calls[0][0:2] == ("POST", "http://hapi/fhir/Patient/$validate")
    assert session.calls[1][0:2] == ("POST", "http://hapi/fhir/Patient")
    assert session.calls[0][2]["timeout"] == (3.05, 15)


def test_hapi_validation_error_becomes_unprocessable_entity() -> None:
    session = FakeSession(
        [
            response(
                400,
                {
                    "resourceType": "OperationOutcome",
                    "issue": [
                        {
                            "severity": "error",
                            "code": "processing",
                            "diagnostics": "Patient.name is invalid",
                        }
                    ],
                },
            )
        ]
    )
    client = FHIRClient(base_url="http://hapi/fhir", session=session)

    with pytest.raises(FhirValidationError) as exc_info:
        client.create_patient({"resourceType": "Patient"})

    assert exc_info.value.http_status == 422
    assert exc_info.value.diagnostics == ["Patient.name is invalid"]
    assert len(session.calls) == 1


def test_timeout_is_classified_without_leaking_transport_details() -> None:
    client = FHIRClient(
        base_url="http://internal-host/fhir",
        session=FakeSession([requests.Timeout("secret internal URL")]),
    )

    with pytest.raises(FhirTimeoutError) as exc_info:
        client.get_patient("123")

    assert exc_info.value.http_status == 504
    assert "secret" not in exc_info.value.message


def test_not_found_is_classified() -> None:
    client = FHIRClient(
        base_url="http://hapi/fhir",
        session=FakeSession([response(404, {"resourceType": "OperationOutcome"})]),
    )

    with pytest.raises(FhirNotFoundError) as exc_info:
        client.get_patient("missing")

    assert exc_info.value.http_status == 404


def test_unexpected_resource_type_is_rejected() -> None:
    client = FHIRClient(
        base_url="http://hapi/fhir",
        session=FakeSession([response(200, {"resourceType": "Observation"})]),
    )

    with pytest.raises(FhirBadGatewayError):
        client.get_patient("123")


def test_automatic_retries_are_limited_to_idempotent_methods() -> None:
    session = FakeSession([])
    FHIRClient(base_url="http://hapi/fhir", retries=3, session=session)

    retry = session.adapters["http://"].max_retries
    assert retry.total == 3
    assert retry.allowed_methods == frozenset({"GET", "HEAD", "OPTIONS"})
