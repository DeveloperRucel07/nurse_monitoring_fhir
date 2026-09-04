from datetime import date

import pytest

from backend.app.core.exceptions import FhirTimeoutError
from backend.app.fhir_ml.ml.ml_utils import (
    LoadedRiskModel,
    SYNTHETIC_LABEL_DEFINITION,
    extract_features_from_fhir,
    extract_risk_labels_from_fhir,
    get_features_for_patient,
    predict_all_risks,
    validate_features,
)


def observation(code: str, value: float) -> dict:
    return {
        "code": {"coding": [{"code": code}]},
        "valueQuantity": {"value": value},
    }


def dated_observation(code: str, value: float, observed_at: str, **extra) -> dict:
    resource = observation(code, value)
    resource.update(
        {
            "id": extra.pop("id", f"observation-{value}"),
            "status": extra.pop("status", "final"),
            "effectiveDateTime": observed_at,
            **extra,
        }
    )
    return resource


def complete_observations() -> list[dict]:
    return [
        observation("8867-4", 72),
        {
            "code": {"coding": [{"code": "85354-9"}]},
            "component": [
                {
                    "code": {"coding": [{"code": "8480-6"}]},
                    "valueQuantity": {"value": 120},
                },
                {
                    "code": {"coding": [{"code": "8462-4"}]},
                    "valueQuantity": {"value": 80},
                },
            ],
        },
        observation("8310-5", 36.7),
        observation("9279-1", 16),
        observation("2708-6", 98),
        observation("72514-3", 2),
        observation("83186-7", 3),
        observation("59460-6", 15),
    ]


def test_extract_features_from_complete_fhir_observations() -> None:
    patient = {"birthDate": "1990-05-15", "gender": "female"}

    features = extract_features_from_fhir(patient, complete_observations())

    expected_age = (
        date.today().year - 1990 - ((date.today().month, date.today().day) < (5, 15))
    )
    assert features == {
        "age": expected_age,
        "gender": 1,
        "heart_rate": 72.0,
        "systolic": 120.0,
        "diastolic": 80.0,
        "temperature": 36.7,
        "respiratory_rate": 16.0,
        "oxygen_saturation": 98.0,
        "pain_score": 2.0,
        "mobility_score": 3.0,
        "morse_score": 15.0,
    }
    assert validate_features(features) == []


def test_validate_features_reports_missing_data() -> None:
    features = extract_features_from_fhir(
        {"birthDate": "1990-05-15", "gender": "male"},
        [observation("8867-4", 72)],
    )

    assert validate_features(features) == [
        "systolic",
        "diastolic",
        "temperature",
        "respiratory_rate",
        "oxygen_saturation",
        "pain_score",
        "mobility_score",
        "morse_score",
    ]


def test_extract_risk_labels_from_fhir() -> None:
    observations = [
        {
            "code": {"coding": [{"code": "nursing-risk-fall"}]},
            "valueCodeableConcept": {"coding": [{"code": "positive"}]},
        },
        {
            "code": {"coding": [{"code": "nursing-risk-pressure-ulcer"}]},
            "valueCodeableConcept": {"coding": [{"code": "negative"}]},
        },
    ]

    labels = extract_risk_labels_from_fhir(observations)

    assert labels == {
        "fall": 1,
        "pressure_ulcer": 0,
        "pain_escalation": None,
        "clinical_deterioration": None,
    }


def test_predict_all_risks_returns_incomplete_data_without_models() -> None:
    artifact = LoadedRiskModel(
        model=object(),
        risk_type="fall",
        feature_columns=(
            "age",
            "gender",
            "heart_rate",
            "systolic",
            "diastolic",
            "temperature",
            "respiratory_rate",
            "oxygen_saturation",
            "pain_score",
            "mobility_score",
            "morse_score",
        ),
        label_definition=SYNTHETIC_LABEL_DEFINITION,
        training_rows=105,
    )
    result = predict_all_risks({"fall": artifact}, {"age": 40})

    assert result["fall"]["status"] == "incomplete_data"
    assert result["fall"]["probability"] is None
    assert "gender" in result["fall"]["missing_features"]


def test_feature_selection_uses_latest_measurement_independent_of_input_order() -> None:
    patient = {"birthDate": "1990-05-15", "gender": "female"}
    observations = [
        dated_observation("8867-4", 60, "2026-01-01T08:00:00Z"),
        dated_observation("8867-4", 82, "2026-01-02T08:00:00Z"),
    ]

    forward = extract_features_from_fhir(patient, observations)
    reverse = extract_features_from_fhir(patient, list(reversed(observations)))

    assert forward == reverse
    assert forward["heart_rate"] == 82.0


def test_feature_selection_skips_entered_in_error_and_invalid_latest_value() -> None:
    patient = {"birthDate": "1990", "gender": "male"}
    observations = [
        dated_observation("8310-5", 36.5, "2026-01-01T08:00:00Z"),
        dated_observation("8310-5", float("nan"), "2026-01-02T08:00:00Z"),
        dated_observation(
            "8310-5",
            42,
            "2026-01-03T08:00:00Z",
            status="entered-in-error",
        ),
    ]

    features = extract_features_from_fhir(patient, observations)

    assert features["temperature"] == 36.5


def test_risk_label_selection_uses_latest_valid_label() -> None:
    observations = [
        {
            "id": "older",
            "status": "final",
            "effectiveDateTime": "2026-01-01T08:00:00Z",
            "code": {"coding": [{"code": "nursing-risk-fall"}]},
            "valueCodeableConcept": {"coding": [{"code": "negative"}]},
        },
        {
            "id": "newer",
            "status": "final",
            "effectiveDateTime": "2026-01-02T08:00:00Z",
            "code": {"coding": [{"code": "nursing-risk-fall"}]},
            "valueCodeableConcept": {"coding": [{"code": "positive"}]},
        },
    ]

    forward = extract_risk_labels_from_fhir(observations)
    reverse = extract_risk_labels_from_fhir(list(reversed(observations)))

    assert forward == reverse
    assert forward["fall"] == 1


def test_feature_loading_preserves_fhir_error_semantics() -> None:
    class FailingClient:
        def get_patient(self, _patient_id):
            return {"resourceType": "Patient", "id": "123"}

        def search_observations(self, **_kwargs):
            raise FhirTimeoutError("FHIR timeout")

    with pytest.raises(FhirTimeoutError):
        get_features_for_patient("123", FailingClient(), allow_incomplete=True)
