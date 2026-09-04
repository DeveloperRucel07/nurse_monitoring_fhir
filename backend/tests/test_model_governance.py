from __future__ import annotations

import pytest

from backend.app.fhir_ml.ml import ml_utils


class PredictiveModel:
    def predict(self, _features):
        return [0]

    def predict_proba(self, _features):
        return [[0.8, 0.2]]


def artifact(risk_type: str = "fall") -> dict:
    return {
        "model": PredictiveModel(),
        "risk_type": risk_type,
        "feature_columns": ml_utils.FEATURE_COLUMNS,
        "label_column": f"label_{risk_type}",
        "label_definition": ml_utils.SYNTHETIC_LABEL_DEFINITION,
        "training_rows": 105,
    }


def test_model_loader_retains_verified_demo_provenance(tmp_path, monkeypatch) -> None:
    (tmp_path / "fall.joblib").touch()
    monkeypatch.setattr(ml_utils.joblib, "load", lambda _path: artifact())

    models = ml_utils.load_risk_models(tmp_path)

    loaded = models["fall"]
    assert loaded.purpose == "demonstration-only"
    assert loaded.clinical_validation_status == "not-clinically-validated"
    assert loaded.training_rows == 105


@pytest.mark.parametrize(
    "invalid_artifact",
    [
        PredictiveModel(),
        artifact("pressure_ulcer"),
        {**artifact(), "feature_columns": ["age"]},
        {**artifact(), "label_definition": "Clinical outcome"},
    ],
)
def test_model_loader_rejects_unverifiable_or_mismatched_artifacts(
    tmp_path,
    monkeypatch,
    invalid_artifact,
) -> None:
    (tmp_path / "fall.joblib").touch()
    monkeypatch.setattr(ml_utils.joblib, "load", lambda _path: invalid_artifact)

    with pytest.raises(ml_utils.ModelArtifactError):
        ml_utils.load_risk_models(tmp_path)
