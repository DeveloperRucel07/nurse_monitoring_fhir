from __future__ import annotations
import logging
from datetime import date, datetime
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

DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parent
    / "fall_risk_model.joblib"
)
DEFAULT_MODEL_DIR = (
    Path(__file__).resolve().parent
    / "models"
)

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

RISK_FEATURE_COLUMNS = {
    risk_type: FEATURE_COLUMNS
    for risk_type in RISK_LABEL_CODES
}


class IncompleteFeaturesError(ValueError):
    """Wird ausgelöst, wenn ein Patient nicht alle ML-Features besitzt."""

    def __init__(self, patient_id: str, missing_features: List[str]):
        self.patient_id = patient_id
        self.missing_features = missing_features
        super().__init__(
            f"Patient/{patient_id} has incomplete features: "
            + ", ".join(missing_features)
        )


def _get_codings(resource: Dict[str, Any],) -> List[Dict[str, Any]]:
    """
    Gibt alle Coding-Elemente eines FHIR CodeableConcepts zurück.
    """

    return (
        resource.get("code", {}).get("coding", [])
    )


def _get_primary_code(resource: Dict[str, Any],) -> Optional[str]:
    """
    Gibt den ersten Coding-Code zurück.
    """
    codings = _get_codings(resource)
    if not codings:
        return None
    return codings[0].get("code")


def _get_quantity_value(quantity: Optional[Dict[str, Any]],) -> Optional[float]:
    """
    Extrahiert value aus einer FHIR valueQuantity.
    """
    if not quantity:
        return None
    value = quantity.get("value")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_observation_quantity(observation: Dict[str, Any],) -> Optional[float]:
    """
    Extrahiert valueQuantity.value.
    """
    return _get_quantity_value(
        observation.get("valueQuantity")
    )


def extract_risk_labels_from_fhir(
    observations: List[Dict[str, Any]],
) -> Dict[str, Optional[int]]:
    """Liest die getrennten synthetischen Trainingslabels aus FHIR."""
    labels = {
        risk_type: None
        for risk_type in RISK_LABEL_CODES
    }
    code_to_risk = {
        code: risk_type
        for risk_type, code in RISK_LABEL_CODES.items()
    }
    for observation in observations:
        risk_type = code_to_risk.get(
            _get_primary_code(observation)
        )
        if risk_type is None:
            continue
        codings = (
            observation
            .get("valueCodeableConcept", {})
            .get("coding", [])
        )
        if codings:
            value = codings[0].get("code")
            if value in {"positive", "negative"}:
                labels[risk_type] = int(value == "positive")
    return labels


def _calculate_age(birth_date: Optional[str],) -> Optional[int]:
    """
    Berechnet das tatsächliche Alter anhand des Geburtstags.
    FHIR birthDate kann auch nur YYYY oder YYYY-MM enthalten.
    """
    if not birth_date:
        return None

    try:
        if len(birth_date) >= 10:

            birthday = date.fromisoformat(
                birth_date[:10]
            )
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

            return (
                date.today().year
                - int(birth_date)
            )

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


def load_model(model_path: str | Path = DEFAULT_MODEL_PATH,):
    """
    Lädt das trainierte ML-Modell.

    Das Modell wird NICHT bei jedem Request neu trainiert.
    """

    model_path = Path(model_path)

    if not model_path.exists():

        raise FileNotFoundError(
            f"ML-Modell nicht gefunden: {model_path}"
        )

    logger.info(
        "Loading fall risk model: %s",
        model_path,
    )

    model = joblib.load(model_path)

    return model


def load_risk_models(
    model_dir: str | Path = DEFAULT_MODEL_DIR,
) -> Dict[str, Any]:
    """Lädt alle verfügbaren Modelle für die Pflegerisiken."""
    model_dir = Path(model_dir)
    models = {}
    for risk_type in RISK_LABEL_CODES:
        path = model_dir / f"{risk_type}.joblib"
        if not path.exists():
            logger.warning("Risikomodell nicht gefunden: %s", path)
            continue
        artifact = joblib.load(path)
        models[risk_type] = (
            artifact["model"]
            if isinstance(artifact, dict) and "model" in artifact
            else artifact
        )
    return models


def extract_features_from_fhir(patient: Dict[str, Any],observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extrahiert ML-Features aus FHIR Patient + Observation.

    Diese Funktion enthält ausschließlich Features.
    Das Prediction-Label wird später vom ML-Modell erzeugt.
    """
    age = _calculate_age(
        patient.get("birthDate")
    )
    gender = _normalize_gender(
        patient.get("gender")
    )

    heart_rate = None

    systolic = None
    diastolic = None

    temperature = None

    respiratory_rate = None

    oxygen_saturation = None

    pain_score = None

    mobility_score = None

    morse_score = None

    for observation in observations:

        code = _get_primary_code(
            observation
        )

        if not code:
            continue

        if code == CODE_HEART_RATE:
            value = _get_observation_quantity(
                observation
            )

            if value is not None:
                heart_rate = value

        elif code == CODE_BLOOD_PRESSURE:

            for component in observation.get(
                "component",
                [],
            ):

                component_code = (
                    _get_primary_code(
                        component
                    )
                )

                if component_code == CODE_SYSTOLIC:

                    systolic = (
                        _get_quantity_value(
                            component.get(
                                "valueQuantity"
                            )
                        )
                    )

                elif component_code == CODE_DIASTOLIC:

                    diastolic = (
                        _get_quantity_value(
                            component.get(
                                "valueQuantity"
                            )
                        )
                    )

        elif code == CODE_TEMPERATURE:

            temperature = (
                _get_observation_quantity(
                    observation
                )
            )

        elif code == CODE_RESPIRATORY_RATE:

            respiratory_rate = (
                _get_observation_quantity(
                    observation
                )
            )

        elif code == CODE_OXYGEN_SATURATION:

            oxygen_saturation = (
                _get_observation_quantity(
                    observation
                )
            )

        elif code == CODE_PAIN:

            pain_score = (
                _get_observation_quantity(
                    observation
                )
            )

        elif code == CODE_MOBILITY:

            coding = (
                observation
                .get(
                    "valueCodeableConcept",
                    {},
                )
                .get(
                    "coding",
                    [],
                )
            )

            if coding:

                mobility_code = (
                    coding[0].get("code")
                )

                try:

                    mobility_score = (
                        float(mobility_code)
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    logger.warning(
                        "Invalid mobility code: %s",
                        mobility_code,
                    )

        elif code == CODE_MORSE_TOTAL:

            morse_score = (
                _get_observation_quantity(
                    observation
                )
            )

    features = {
        "age": age,
        "gender": gender,
        "heart_rate": heart_rate,
        "systolic": systolic,
        "diastolic": diastolic,
        "temperature": temperature,
        "respiratory_rate":respiratory_rate,
        "oxygen_saturation": oxygen_saturation,
        "pain_score": pain_score,
        "mobility_score": mobility_score,
        "morse_score":morse_score,
    }

    return features


def validate_features(features: Dict[str, Any],required_features: Optional[List[str]] = None,) -> List[str]:
    """
    Gibt fehlende Features zurück.
    """
    required = (
        required_features
        or FEATURE_COLUMNS
    )
    missing = []
    for feature in required:
        value = features.get(
            feature
        )
        if value is None:

            missing.append(
                feature
            )

    return missing


def prepare_model_input(features: Dict[str, Any],) -> pd.DataFrame:
    """
    Erstellt exakt den DataFrame, den das Modell erwartet.
    """
    data = {}
    for column in FEATURE_COLUMNS:

        data[column] = [
            features.get(column)
        ]
    df = pd.DataFrame(
        data,
        columns=FEATURE_COLUMNS,
    )
    return df


def predict_fall_risk(model,features: Dict[str, Any],) -> Dict[str, Any]:
    """
    Führt eine Sturzrisiko-Vorhersage durch.

    Returns:
        {
            "prediction": 0/1,
            "label": "low"/"high",
            "probability": 0.XX
        }
    """

    missing = validate_features(
        features
    )
    if missing:

        raise ValueError(
            "Fehlende ML-Features: "
            + ", ".join(missing)
        )
    X = prepare_model_input(features)
    prediction = int(
        model.predict(X)[0]
    )

    probability = None

    if hasattr( model,"predict_proba",):

        probabilities = (
            model.predict_proba(X)[0]
        )
        classes = list(
            model.classes_
        )
        if 1 in classes:

            high_index = (
                classes.index(1)
            )
            probability = float(
                probabilities[high_index]
            )

    label = (
        "high"
        if prediction == 1
        else "low"
    )
    return {
        "prediction": prediction,
        "label": label,
        "probability": probability,
    }



def get_features_for_patient(
    patient_id: str,
    fhir_client: FHIRClient,
    allow_incomplete: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Lädt Patient + Observations aus HAPI FHIR
    und erzeugt die ML-Features.
    """

    try:
        patient = (
            fhir_client.get_patient(
                patient_id
            )
        )
    except Exception as exc:

        logger.error(
            "Could not load Patient/%s: %s",
            patient_id,
            exc,
        )

        return None
    try:

        obs_bundle = (
            fhir_client.search_observations(
                subject_reference=(
                    f"Patient/{patient_id}"
                )
            )
        )
    except Exception as exc:

        logger.error(
            "Could not load observations "
            "for Patient/%s: %s",
            patient_id,
            exc,
        )
        return None
    observations = []
    for entry in obs_bundle.get(
        "entry",
        [],
    ):
        resource = entry.get(
            "resource"
        )
        if resource:

            observations.append(
                resource
            )

    features = extract_features_from_fhir(
        patient,
        observations,
    )

    missing = validate_features(
        features
    )
    if missing and not allow_incomplete:
        logger.warning(
            "Patient/%s has incomplete "
            "features: %s",
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
    models: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Bewertet alle geladenen Risiken unabhängig voneinander."""
    features = get_features_for_patient(
        patient_id,
        fhir_client,
        allow_incomplete=True,
    )
    if features is None:
        return None
    return {
        "patient_id": patient_id,
        "features": features,
        "risks": predict_all_risks(models, features),
    }

def predict_patient(patient_id: str,fhir_client: FHIRClient,model,) -> Optional[Dict[str, Any]]:
    """
    Lädt einen Patienten aus FHIR,
    extrahiert Features und führt die ML-Prediction durch.
    """

    features = get_features_for_patient(
        patient_id,
        fhir_client,
    )

    if features is None:

        return None

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
    models: Dict[str, Any],
    features: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Erzeugt eine Prediction für jedes geladene Pflegerisiko."""
    results = {}
    for risk_type, model in models.items():
        missing = validate_features(
            features,
            RISK_FEATURE_COLUMNS[risk_type],
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

        prediction = predict_fall_risk(model, features)
        results[risk_type] = {
            "status": "assessed",
            "missing_features": [],
            **prediction,
        }
    return results