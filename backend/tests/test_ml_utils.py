from datetime import date

from backend.app.fhir_ml.ml.ml_utils import (
    extract_features_from_fhir,
    extract_risk_labels_from_fhir,
    predict_all_risks,
    validate_features,
)


def observation(code: str, value: float) -> dict:
    return {
        "code": {"coding": [{"code": code}]},
        "valueQuantity": {"value": value},
    }


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

    expected_age = date.today().year - 1990 - (
        (date.today().month, date.today().day) < (5, 15)
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
    result = predict_all_risks({"fall": object()}, {"age": 40})

    assert result["fall"]["status"] == "incomplete_data"
    assert result["fall"]["probability"] is None
    assert "gender" in result["fall"]["missing_features"]