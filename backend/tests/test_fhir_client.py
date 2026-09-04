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


def test_search_combines_all_bundle_pages() -> None:
    session = FakeSession(
        [
            response(
                200,
                {
                    "resourceType": "Bundle",
                    "type": "searchset",
                    "total": 2,
                    "entry": [{"resource": {"resourceType": "Patient", "id": "1"}}],
                    "link": [
                        {
                            "relation": "next",
                            "url": "http://hapi/fhir/Patient?_getpages=page-2",
                        }
                    ],
                },
            ),
            response(
                200,
                {
                    "resourceType": "Bundle",
                    "type": "searchset",
                    "entry": [{"resource": {"resourceType": "Patient", "id": "2"}}],
                },
            ),
        ]
    )
    client = FHIRClient(base_url="http://hapi/fhir", page_size=50, session=session)

    bundle = client.search_patients(family="Test")

    assert [entry["resource"]["id"] for entry in bundle["entry"]] == ["1", "2"]
    assert bundle["total"] == 2
    assert "link" not in bundle
    assert session.calls[0][2]["params"] == {"family": "Test", "_count": "50"}
    assert session.calls[1][1] == "http://hapi/fhir/Patient?_getpages=page-2"


def test_search_rejects_cross_origin_next_link() -> None:
    client = FHIRClient(
        base_url="http://hapi/fhir",
        session=FakeSession(
            [
                response(
                    200,
                    {
                        "resourceType": "Bundle",
                        "link": [
                            {
                                "relation": "next",
                                "url": "http://attacker.invalid/fhir/Patient?page=2",
                            }
                        ],
                    },
                )
            ]
        ),
    )

    with pytest.raises(FhirBadGatewayError, match="unsicheren Pagination-Link"):
        client.search_patients()


def test_search_fails_instead_of_returning_partial_results_at_page_limit() -> None:
    client = FHIRClient(
        base_url="http://hapi/fhir",
        max_pages=1,
        session=FakeSession(
            [
                response(
                    200,
                    {
                        "resourceType": "Bundle",
                        "entry": [{"resource": {"resourceType": "Patient", "id": "1"}}],
                        "link": [
                            {
                                "relation": "next",
                                "url": "http://hapi/fhir/Patient?page=2",
                            }
                        ],
                    },
                )
            ]
        ),
    )

    with pytest.raises(FhirBadGatewayError, match="Seitengrenze"):
        client.search_patients()


def test_query_only_next_link_is_resolved_against_current_search_url() -> None:
    session = FakeSession(
        [
            response(
                200,
                {
                    "resourceType": "Bundle",
                    "link": [{"relation": "next", "url": "?page=2"}],
                },
            ),
            response(200, {"resourceType": "Bundle"}),
        ]
    )
    client = FHIRClient(base_url="http://hapi/fhir", session=session)

    client.search_patients()

    assert session.calls[1][1] == "http://hapi/fhir/Patient?page=2"


def test_update_resource_uses_weak_etag_for_optimistic_concurrency() -> None:
    session = FakeSession(
        [
            response(200, {"resourceType": "OperationOutcome", "issue": []}),
            response(
                200,
                {
                    "resourceType": "Composition",
                    "id": "report-1",
                    "meta": {"versionId": "2"},
                },
            ),
        ]
    )
    client = FHIRClient(base_url="http://hapi/fhir", session=session)

    client.update_resource(
        "Composition",
        "report-1",
        {"resourceType": "Composition", "id": "report-1"},
        expected_version_id="1",
    )

    assert session.calls[1][2]["headers"]["If-Match"] == 'W/"1"'


def test_transaction_validates_each_resource_before_atomic_post() -> None:
    session = FakeSession(
        [
            response(200, {"resourceType": "OperationOutcome", "issue": []}),
            response(200, {"resourceType": "OperationOutcome", "issue": []}),
            response(200, {"resourceType": "Bundle", "type": "transaction-response"}),
        ]
    )
    client = FHIRClient(base_url="http://hapi/fhir", session=session)
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {
                "resource": {"resourceType": "Patient"},
                "request": {"method": "POST", "url": "Patient"},
            },
            {
                "resource": {"resourceType": "Encounter"},
                "request": {"method": "POST", "url": "Encounter"},
            },
        ],
    }

    client.transaction(bundle)

    assert [call[1] for call in session.calls] == [
        "http://hapi/fhir/Patient/$validate",
        "http://hapi/fhir/Encounter/$validate",
        "http://hapi/fhir/",
    ]
    assert session.calls[2][2]["headers"]["Prefer"] == "return=representation"
