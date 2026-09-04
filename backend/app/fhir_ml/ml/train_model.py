import os, sys
from pathlib import Path
from typing import Any, Dict, List
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.fhir_ml.ml.ml_utils import (
    CLINICAL_VALIDATION_STATUS,
    MODEL_PURPOSE,
    RISK_FEATURE_COLUMNS,
    RISK_LABEL_CODES,
    SYNTHETIC_LABEL_DEFINITION,
    extract_features_from_fhir,
    extract_risk_labels_from_fhir,
)
from backend.app.fhir_ml.fhir.FHIRclient import FHIRClient

BASE_URL = os.getenv(
    "FHIR_SERVER_URL",
    "http://localhost:8080/fhir",
).rstrip("/")
MODEL_DIR = Path(
    os.getenv(
        "FALL_RISK_MODEL_DIR",
        str(PROJECT_ROOT / "backend/app/fhir_ml/ml/models"),
    )
)
FHIR_CLIENT = FHIRClient(BASE_URL)


def get_bundle_resources(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        entry["resource"]
        for entry in bundle.get("entry", [])
        if isinstance(entry, dict) and isinstance(entry.get("resource"), dict)
    ]


def get_all_patients() -> List[Dict[str, Any]]:
    return get_bundle_resources(FHIR_CLIENT.search_patients())


def get_observations_for_patient(patient_id: str) -> List[Dict[str, Any]]:
    return get_bundle_resources(
        FHIR_CLIENT.search_observations(subject_reference=f"Patient/{patient_id}")
    )


def build_dataframe() -> pd.DataFrame:
    rows = []
    patients = get_all_patients()
    print(f"HAPI: {len(patients)} Patienten gefunden")
    for patient in patients:
        patient_id = patient.get("id")
        if not patient_id:
            continue
        observations = get_observations_for_patient(patient_id)
        features = extract_features_from_fhir(patient, observations)
        labels = extract_risk_labels_from_fhir(observations)
        rows.append(
            {
                "patient_id": patient_id,
                **features,
                **{f"label_{risk_type}": value for risk_type, value in labels.items()},
            }
        )
    return pd.DataFrame(rows)


def train_risk_model(
    dataframe: pd.DataFrame,
    risk_type: str,
) -> Dict[str, Any]:
    label_column = f"label_{risk_type}"
    data = dataframe.dropna(subset=[label_column]).copy()
    feature_columns = RISK_FEATURE_COLUMNS[risk_type]
    if len(data) < 10 or data[label_column].nunique() < 2:
        raise ValueError(
            f"Zu wenige Daten oder nur eine Klasse für Risiko '{risk_type}'."
        )

    X = data[feature_columns]
    y = data[label_column].astype(int)
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )
    pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=200,
                    random_state=42,
                    class_weight="balanced",
                ),
            ),
        ]
    )
    pipeline.fit(X_train, y_train)
    predictions = pipeline.predict(X_test)
    print(f"\nRisiko: {risk_type}")
    print(confusion_matrix(y_test, predictions))
    print(classification_report(y_test, predictions, zero_division=0))
    return {
        "model": pipeline,
        "risk_type": risk_type,
        "feature_columns": feature_columns,
        "label_column": label_column,
        "label_definition": SYNTHETIC_LABEL_DEFINITION,
        "training_rows": len(data),
        "training_data_kind": "synthetic",
        "intended_use": MODEL_PURPOSE,
        "clinical_validation_status": CLINICAL_VALIDATION_STATUS,
        "artifact_version": 1,
    }


def train() -> None:
    dataframe = build_dataframe()
    if dataframe.empty:
        raise ValueError("Keine Patientendaten zum Trainieren gefunden.")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for risk_type in RISK_LABEL_CODES:
        metadata = train_risk_model(dataframe, risk_type)
        path = MODEL_DIR / f"{risk_type}.joblib"
        joblib.dump(metadata, path)
        print(f"Modell gespeichert: {path}")


if __name__ == "__main__":
    train()
