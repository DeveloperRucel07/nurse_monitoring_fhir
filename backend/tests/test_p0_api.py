from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.core import security
from backend.app.core.exceptions import FhirValidationError
from backend.app.local_test.seed import (
    ENCOUNTER_IDENTIFIER_SYSTEM,
    PATIENT_IDENTIFIER_SYSTEM,
    BundleGenerator,
    CarePlanGenerator,
    PatientGenerator,
)


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    main.app.dependency_overrides.clear()
    yield
    main.app.dependency_overrides.clear()


def claims(*roles: str) -> dict:
    return {
        "sub": "test-user",
        "azp": security.ALLOWED_CLIENT_ID,
        "resource_access": {
            security.API_AUDIENCE: {"roles": list(roles)},
        },
    }


def test_fhir_errors_are_returned_as_operation_outcome(monkeypatch) -> None:
    class InvalidFhir:
        def create_patient(self, _patient):
            raise FhirValidationError(
                "Die FHIR-Ressource ist nicht valide.",
                diagnostics=["Patient.name is required"],
            )

    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_admin"
    )
    monkeypatch.setattr(main, "fhir", InvalidFhir())

    response = TestClient(main.app).post(
        "/Patient",
        json={"name": [{"family": "Test"}]},
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/fhir+json")
    assert response.json()["resourceType"] == "OperationOutcome"
    assert response.json()["issue"][1]["diagnostics"] == "Patient.name is required"


def test_invalid_api_input_is_returned_as_operation_outcome() -> None:
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_admin"
    )

    response = TestClient(main.app).post(
        "/Patient",
        json={"name": [{"family": "Test"}], "gender": "invalid"},
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/fhir+json")
    assert response.json()["resourceType"] == "OperationOutcome"
    assert response.json()["issue"][0]["code"] == "invalid"


def test_risk_assessment_omits_null_probability_and_is_fhir_validated(
    monkeypatch,
) -> None:
    class ValidatingFhir:
        validated = None

        def validate_resource(self, resource_type, resource):
            self.validated = (resource_type, resource)

    fake_fhir = ValidatingFhir()
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_read"
    )
    monkeypatch.setattr(main, "fhir", fake_fhir)
    monkeypatch.setattr(main, "ML_MODE", "synthetic-demo")
    monkeypatch.setattr(main, "RISK_MODELS", {"verified": object()})
    monkeypatch.setattr(
        main,
        "predict_patient_all_risks",
        lambda **_kwargs: {
            "risks": {
                "fall": {
                    "status": "assessed",
                    "label": "low",
                    "probability": 0.2,
                    "missing_features": [],
                },
                "pressure_ulcer": {
                    "status": "incomplete_data",
                    "label": None,
                    "probability": None,
                    "missing_features": ["mobility_score"],
                },
            }
        },
    )

    response = TestClient(main.app).get("/Patient/123/nursing-risk-assessment")

    assert response.status_code == 200
    predictions = response.json()["prediction"]
    assert predictions[0]["probabilityDecimal"] == 0.2
    assert "probabilityDecimal" not in predictions[1]
    payload = response.json()
    assert payload["status"] == "preliminary"
    assert payload["method"]["coding"][0]["code"] == "synthetic-demo-ml-model"
    assert "qualitativeRisk" not in predictions[0]
    assert {extension["valueCode"] for extension in payload["extension"]} == {
        "demonstration-only",
        "not-clinically-validated",
        "synthetic",
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-model-purpose"] == "synthetic-demo-only"
    assert fake_fhir.validated[0] == "RiskAssessment"


def test_invalid_model_probability_is_not_published(monkeypatch) -> None:
    class ValidatingFhir:
        def validate_resource(self, _resource_type, _resource):
            raise AssertionError("invalid model output must not reach FHIR validation")

    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_read"
    )
    monkeypatch.setattr(main, "fhir", ValidatingFhir())
    monkeypatch.setattr(main, "ML_MODE", "synthetic-demo")
    monkeypatch.setattr(main, "RISK_MODELS", {"verified": object()})
    monkeypatch.setattr(
        main,
        "predict_patient_all_risks",
        lambda **_kwargs: {
            "risks": {
                "fall": {
                    "status": "assessed",
                    "label": "high",
                    "probability": 1.5,
                    "missing_features": [],
                }
            }
        },
    )

    response = TestClient(main.app).get("/Patient/123/nursing-risk-assessment")

    assert response.status_code == 503


def test_ml_endpoint_is_fail_closed_when_demo_mode_is_disabled(monkeypatch) -> None:
    main.app.dependency_overrides[security.get_current_client] = lambda: claims(
        "pflege_read"
    )
    monkeypatch.setattr(main, "ML_MODE", "disabled")
    monkeypatch.setattr(
        main,
        "predict_patient_all_risks",
        lambda **_kwargs: pytest.fail("disabled ML must not execute"),
    )

    response = TestClient(main.app).get("/Patient/123/nursing-risk-assessment")

    assert response.status_code == 503
    assert "nicht für den klinischen Einsatz" in response.json()["detail"]


def test_seed_care_plan_uses_valid_contained_goal_references() -> None:
    profile = PatientGenerator(random.Random(1)).generate()

    care_plan = CarePlanGenerator.generate(
        profile,
        "Patient/example",
        "2026-01-01T00:00:00Z",
    )

    contained_ids = {goal["id"] for goal in care_plan["contained"]}
    references = {item["reference"] for item in care_plan["goal"]}
    assert references == {f"#{goal_id}" for goal_id in contained_ids}
    assert all(goal["resourceType"] == "Goal" for goal in care_plan["contained"])
    assert all(
        goal["subject"]["reference"] == "Patient/example"
        for goal in care_plan["contained"]
    )


def test_seed_bundle_creates_patient_with_active_encounter_identifiers() -> None:
    _, bundle = BundleGenerator(random.Random(1)).generate(sequence=7)

    patient_entry, encounter_entry = bundle["entry"][:2]
    patient = patient_entry["resource"]
    encounter = encounter_entry["resource"]

    assert patient["resourceType"] == "Patient"
    assert patient["identifier"] == [
        {
            "use": "official",
            "system": PATIENT_IDENTIFIER_SYSTEM,
            "value": "PAT-SEED-000007",
        }
    ]
    assert encounter["resourceType"] == "Encounter"
    assert encounter["identifier"] == [
        {
            "use": "official",
            "system": ENCOUNTER_IDENTIFIER_SYSTEM,
            "value": "FALL-SEED-000007",
        }
    ]
    assert encounter["status"] == "in-progress"
    assert encounter["class"]["code"] == "IMP"
    assert encounter["subject"]["reference"] == patient_entry["fullUrl"]
    assert encounter_entry["request"] == {"method": "POST", "url": "Encounter"}
