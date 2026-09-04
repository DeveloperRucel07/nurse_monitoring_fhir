from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import pandas as pd

from backend.app.fhir_ml.fhir.FHIRclient import FHIRClient

logger = logging.getLogger(__name__)

LOINC_SYSTEM = "http://loinc.org"
UCUM_SYSTEM = "http://unitsofmeasure.org"
CODE_HEART_RATE = "8867-4"
CODE_BLOOD_PRESSURE = "85354-9"
CODE_SYSTOLIC = "8480-6"
CODE_DIASTOLIC = "8462-4"
CODE_TEMPERATURE = "8310-5"
CODE_RESPIRATORY_RATE = "9279-1"
CODE_OXYGEN_SATURATION = "2708-6"
CODE_PAIN = "72514-3"
CODE_MOBILITY = "83186-7"
CODE_MORSE_TOTAL = "59460-6"
CODE_MORSE_LEVEL = "59461-4"
CODE_MORSE_GAIT = "59458-0"
RISK_LABEL_SYSTEM = "http://example.org/fhir/CodeSystem/nursing-risk-label"

RISK_LABEL_CODES = {
    "fall": "nursing-risk-fall",
    "pressure_ulcer": "nursing-risk-pressure-ulcer",
    "pain_escalation": "nursing-risk-pain-escalation",
    "clinical_deterioration": "nursing-risk-clinical-deterioration",
}

SYNTHETIC_LABEL_DEFINITION = "Synthetic FHIR label; not a clinical outcome."
MODEL_PURPOSE = "demonstration-only"
CLINICAL_VALIDATION_STATUS = "not-clinically-validated"

DEFAULT_MODEL_DIR = Path(__file__).resolve().parent / "models"

FEATURE_COLUMNS = [
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
]

RISK_FEATURE_COLUMNS = {risk_type: FEATURE_COLUMNS for risk_type in RISK_LABEL_CODES}


class IncompleteFeaturesError(ValueError):
    """Wird ausgelöst, wenn ein Patient nicht alle ML-Features besitzt."""

    def __init__(self, patient_id: str, missing_features: List[str]):
        self.patient_id = patient_id
        self.missing_features = missing_features
        super().__init__(
            f"Patient/{patient_id} has incomplete features: "
            + ", ".join(missing_features)
        )


class ModelArtifactError(RuntimeError):
    """Raised when a model artifact cannot prove its expected demo provenance."""


@dataclass(frozen=True)
class LoadedRiskModel:
    model: Any
    risk_type: str
    feature_columns: tuple[str, ...]
    label_definition: str
    training_rows: int
    purpose: str = MODEL_PURPOSE
    clinical_validation_status: str = CLINICAL_VALIDATION_STATUS


def _get_codings(
    resource: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Gibt alle Coding-Elemente eines FHIR CodeableConcepts zurück.
    """

    return resource.get("code", {}).get("coding", [])


def _get_primary_code(
    resource: Dict[str, Any],
) -> Optional[str]:
    """
    Gibt den bevorzugten Coding-Code unabhängig von der Coding-Reihenfolge zurück.
    """
    codings = _get_codings(resource)
    coded_values = [
        (str(coding.get("system") or ""), str(coding.get("code") or ""))
        for coding in codings
        if isinstance(coding, dict) and coding.get("code")
    ]
    if not coded_values:
        return None

    # Prefer LOINC when it is present; otherwise remain deterministic even if
    # a server changes Coding order.
    coded_values.sort(key=lambda item: (item[0] != LOINC_SYSTEM, item[0], item[1]))
    return coded_values[0][1]


def _get_quantity_value(
    quantity: Optional[Dict[str, Any]],
) -> Optional[float]:
    """
    Extrahiert value aus einer FHIR valueQuantity.
    """
    if not quantity:
        return None
    value = quantity.get("value")
    if value is None:
        return None
    try:
        numeric_value = float(value)
        return numeric_value if math.isfinite(numeric_value) else None
    except (TypeError, ValueError):
        return None


def _get_observation_quantity(
    observation: Dict[str, Any],
) -> Optional[float]:
    """
    Extrahiert valueQuantity.value.
    """
    return _get_quantity_value(observation.get("valueQuantity"))


def _parse_fhir_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    if len(normalized) == 4:
        normalized += "-01-01"
    elif len(normalized) == 7:
        normalized += "-01"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _observation_time(observation: Dict[str, Any]) -> Optional[datetime]:
    effective_period = observation.get("effectivePeriod")
    period_value = None
    if isinstance(effective_period, dict):
        period_value = effective_period.get("end") or effective_period.get("start")
    meta = observation.get("meta")
    last_updated = meta.get("lastUpdated") if isinstance(meta, dict) else None
    for value in (
        observation.get("effectiveDateTime"),
        observation.get("effectiveInstant"),
        period_value,
        observation.get("issued"),
        last_updated,
    ):
        parsed = _parse_fhir_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _observation_sort_key(observation: Dict[str, Any]) -> tuple[Any, ...]:
    observed_at = _observation_time(observation)
    issued_at = _parse_fhir_datetime(observation.get("issued"))
    meta = observation.get("meta")
    updated_at = _parse_fhir_datetime(
        meta.get("lastUpdated") if isinstance(meta, dict) else None
    )
    status_rank = {
        "registered": 1,
        "preliminary": 2,
        "final": 3,
        "amended": 4,
        "corrected": 5,
    }.get(observation.get("status"), 0)
    stable_resource = json.dumps(
        observation,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        observed_at is not None,
        observed_at or datetime.min.replace(tzinfo=timezone.utc),
        issued_at or datetime.min.replace(tzinfo=timezone.utc),
        updated_at or datetime.min.replace(tzinfo=timezone.utc),
        status_rank,
        str(observation.get("id") or ""),
        stable_resource,
    )


def _usable_observations(
    observations: List[Dict[str, Any]],
    code: str,
) -> List[Dict[str, Any]]:
    return sorted(
        (
            observation
            for observation in observations
            if isinstance(observation, dict)
            and observation.get("status") not in {"cancelled", "entered-in-error"}
            and _get_primary_code(observation) == code
        ),
        key=_observation_sort_key,
        reverse=True,
    )


def _latest_value(
    observations: List[Dict[str, Any]],
    code: str,
    extractor: Callable[[Dict[str, Any]], Optional[float]],
) -> Optional[float]:
    for observation in _usable_observations(observations, code):
        value = extractor(observation)
        if value is not None:
            return value
    return None


def _risk_label_value(observation: Dict[str, Any]) -> Optional[int]:
    codings = observation.get("valueCodeableConcept", {}).get("coding", [])
    values = {
        coding.get("code")
        for coding in codings
        if isinstance(coding, dict) and coding.get("code") in {"positive", "negative"}
    }
    if len(values) != 1:
        return None
    return int(values.pop() == "positive")


def extract_risk_labels_from_fhir(
    observations: List[Dict[str, Any]],
) -> Dict[str, Optional[int]]:
    """Liest die getrennten synthetischen Trainingslabels aus FHIR."""
    labels = {risk_type: None for risk_type in RISK_LABEL_CODES}
    code_to_risk = {code: risk_type for risk_type, code in RISK_LABEL_CODES.items()}
    for code, risk_type in code_to_risk.items():
        for observation in _usable_observations(observations, code):
            value = _risk_label_value(observation)
            if value is not None:
                labels[risk_type] = value
                break
    return labels


def _calculate_age(
    birth_date: Optional[str],
) -> Optional[int]:
    """
    Berechnet das tatsächliche Alter anhand des Geburtstags.
    FHIR birthDate kann auch nur YYYY oder YYYY-MM enthalten.
    """
    if not birth_date:
        return None

    try:
        if len(birth_date) >= 10:

            birthday = date.fromisoformat(birth_date[:10])
            today = date.today()
            age = (
                today.year
                - birthday.year
                - (
                    (today.month, today.day)
                    < (
                        birthday.month,
                        birthday.day,
                    )
                )
            )
            return age

        if len(birth_date) == 4:

            return date.today().year - int(birth_date)

    except (ValueError, TypeError):

        logger.warning(
            "Ungültiges birthDate: %s",
            birth_date,
        )

    return None


def _normalize_gender(gender: Optional[str]) -> Optional[int]:
    """
    Wandelt FHIR gender in numerische Features um.

    female = 1
    male   = 0

    unknown/other = None
    """

    if gender == "female":
        return 1

    if gender == "male":
        return 0

    return None


def load_risk_models(
    model_dir: str | Path = DEFAULT_MODEL_DIR,
) -> Dict[str, LoadedRiskModel]:
    """Load only artifacts that prove their expected synthetic-demo provenance."""
    model_dir = Path(model_dir)
    models: Dict[str, LoadedRiskModel] = {}
    for risk_type in RISK_LABEL_CODES:
        path = model_dir / f"{risk_type}.joblib"
        if not path.exists():
            logger.warning("Risikomodell nicht gefunden: %s", path)
            continue
        artifact = joblib.load(path)
        if not isinstance(artifact, dict):
            raise ModelArtifactError(
                f"Model artifact '{path.name}' has no verifiable metadata."
            )

        expected_features = tuple(RISK_FEATURE_COLUMNS[risk_type])
        artifact_features = artifact.get("feature_columns")
        training_rows = artifact.get("training_rows")
        model = artifact.get("model")
        metadata_is_valid = (
            artifact.get("risk_type") == risk_type
            and artifact.get("label_column") == f"label_{risk_type}"
            and isinstance(artifact_features, (list, tuple))
            and tuple(artifact_features) == expected_features
            and artifact.get("label_definition") == SYNTHETIC_LABEL_DEFINITION
            and isinstance(training_rows, int)
            and not isinstance(training_rows, bool)
            and training_rows >= 10
            and callable(getattr(model, "predict", None))
            and callable(getattr(model, "predict_proba", None))
        )
        if not metadata_is_valid:
            raise ModelArtifactError(
                f"Model artifact '{path.name}' does not match its declared demo contract."
            )

        models[risk_type] = LoadedRiskModel(
            model=model,
            risk_type=risk_type,
            feature_columns=expected_features,
            label_definition=SYNTHETIC_LABEL_DEFINITION,
            training_rows=training_rows,
        )
    return models


def _blood_pressure_component(
    observation: Dict[str, Any],
    component_code: str,
) -> Optional[float]:
    values = set()
    for component in observation.get("component", []):
        if (
            isinstance(component, dict)
            and _get_primary_code(component) == component_code
        ):
            value = _get_quantity_value(component.get("valueQuantity"))
            if value is not None:
                values.add(value)
    return values.pop() if len(values) == 1 else None


def _mobility_value(observation: Dict[str, Any]) -> Optional[float]:
    quantity = _get_observation_quantity(observation)
    if quantity is not None:
        return quantity

    codings = observation.get("valueCodeableConcept", {}).get("coding", [])
    numeric_values = []
    for coding in codings:
        if not isinstance(coding, dict):
            continue
        try:
            value = float(coding.get("code"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            numeric_values.append(value)
    unique_values = set(numeric_values)
    return unique_values.pop() if len(unique_values) == 1 else None


def extract_features_from_fhir(
    patient: Dict[str, Any], observations: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Extract the latest usable value for every model feature deterministically."""
    return {
        "age": _calculate_age(patient.get("birthDate")),
        "gender": _normalize_gender(patient.get("gender")),
        "heart_rate": _latest_value(
            observations, CODE_HEART_RATE, _get_observation_quantity
        ),
        "systolic": _latest_value(
            observations,
            CODE_BLOOD_PRESSURE,
            lambda item: _blood_pressure_component(item, CODE_SYSTOLIC),
        ),
        "diastolic": _latest_value(
            observations,
            CODE_BLOOD_PRESSURE,
            lambda item: _blood_pressure_component(item, CODE_DIASTOLIC),
        ),
        "temperature": _latest_value(
            observations, CODE_TEMPERATURE, _get_observation_quantity
        ),
        "respiratory_rate": _latest_value(
            observations, CODE_RESPIRATORY_RATE, _get_observation_quantity
        ),
        "oxygen_saturation": _latest_value(
            observations, CODE_OXYGEN_SATURATION, _get_observation_quantity
        ),
        "pain_score": _latest_value(observations, CODE_PAIN, _get_observation_quantity),
        "mobility_score": _latest_value(observations, CODE_MOBILITY, _mobility_value),
        "morse_score": _latest_value(
            observations, CODE_MORSE_TOTAL, _get_observation_quantity
        ),
    }


def validate_features(
    features: Dict[str, Any],
    required_features: Optional[List[str]] = None,
) -> List[str]:
    """
    Gibt fehlende Features zurück.
    """
    required = required_features or FEATURE_COLUMNS
    missing = []
    for feature in required:
        value = features.get(feature)
        if value is None:

            missing.append(feature)

    return missing


def prepare_model_input(
    features: Dict[str, Any],
) -> pd.DataFrame:
    """
    Erstellt exakt den DataFrame, den das Modell erwartet.
    """
    data = {}
    for column in FEATURE_COLUMNS:

        data[column] = [features.get(column)]
    df = pd.DataFrame(
        data,
        columns=FEATURE_COLUMNS,
    )
    return df


def predict_fall_risk(
    model,
    features: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Führt eine Sturzrisiko-Vorhersage durch.

    Returns:
        {
            "prediction": 0/1,
            "label": "low"/"high",
            "probability": 0.XX
        }
    """

    missing = validate_features(features)
    if missing:

        raise ValueError("Fehlende ML-Features: " + ", ".join(missing))
    X = prepare_model_input(features)
    prediction = int(model.predict(X)[0])

    probability = None

    if hasattr(
        model,
        "predict_proba",
    ):

        probabilities = model.predict_proba(X)[0]
        classes = list(model.classes_)
        if 1 in classes:

            high_index = classes.index(1)
            probability = float(probabilities[high_index])

    label = "high" if prediction == 1 else "low"
    return {
        "prediction": prediction,
        "label": label,
        "probability": probability,
    }


def get_features_for_patient(
    patient_id: str,
    fhir_client: FHIRClient,
    allow_incomplete: bool = False,
) -> Dict[str, Any]:
    """
    Lädt Patient + Observations aus HAPI FHIR
    und erzeugt die ML-Features.
    """

    patient = fhir_client.get_patient(patient_id)
    obs_bundle = fhir_client.search_observations(
        subject_reference=f"Patient/{patient_id}"
    )
    observations = []
    for entry in obs_bundle.get(
        "entry",
        [],
    ):
        resource = entry.get("resource")
        if resource:

            observations.append(resource)

    features = extract_features_from_fhir(
        patient,
        observations,
    )

    missing = validate_features(features)
    if missing and not allow_incomplete:
        logger.warning(
            "Patient/%s has incomplete " "features: %s",
            patient_id,
            ", ".join(missing),
        )

        raise IncompleteFeaturesError(
            patient_id,
            missing,
        )

    return features


def predict_patient_all_risks(
    patient_id: str,
    fhir_client: FHIRClient,
    models: Dict[str, LoadedRiskModel],
) -> Dict[str, Any]:
    """Bewertet alle geladenen Risiken unabhängig voneinander."""
    features = get_features_for_patient(
        patient_id,
        fhir_client,
        allow_incomplete=True,
    )
    return {
        "patient_id": patient_id,
        "features": features,
        "risks": predict_all_risks(models, features),
    }


def predict_patient(
    patient_id: str,
    fhir_client: FHIRClient,
    model,
) -> Dict[str, Any]:
    """
    Lädt einen Patienten aus FHIR,
    extrahiert Features und führt die ML-Prediction durch.
    """

    features = get_features_for_patient(
        patient_id,
        fhir_client,
    )

    prediction = predict_fall_risk(
        model,
        features,
    )

    return {
        "patient_id": patient_id,
        "features": features,
        "prediction": prediction,
    }


def predict_all_risks(
    models: Dict[str, LoadedRiskModel],
    features: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Erzeugt eine Prediction für jedes geladene Pflegerisiko."""
    results = {}
    for risk_type, artifact in models.items():
        if not isinstance(artifact, LoadedRiskModel) or artifact.risk_type != risk_type:
            raise ModelArtifactError("Unverified model supplied for prediction.")
        missing = validate_features(
            features,
            list(artifact.feature_columns),
        )
        if missing:
            results[risk_type] = {
                "status": "incomplete_data",
                "missing_features": missing,
                "prediction": None,
                "label": None,
                "probability": None,
            }
            continue

        prediction = predict_fall_risk(artifact.model, features)
        results[risk_type] = {
            "status": "assessed",
            "missing_features": [],
            **prediction,
        }
    return results
