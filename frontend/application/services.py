from typing import Any

from frontend.domain.models import Observation, Patient, RiskResult, RISK_LABELS, parse_observation, parse_patient


def bundle_resources(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry["resource"] for entry in bundle.get("entry", []) if entry.get("resource")]


def patients_from_bundle(bundle: dict[str, Any]) -> list[Patient]:
    return [parse_patient(resource) for resource in bundle_resources(bundle)]


def observations_from_bundle(bundle: dict[str, Any]) -> list[Observation]:
    return [parse_observation(resource) for resource in bundle_resources(bundle)]


def risks_from_assessment(assessment: dict[str, Any]) -> list[RiskResult]:
    results = []
    for prediction in assessment.get("prediction", []):
        outcome = prediction.get("outcome", {}).get("text", "")
        extensions = {item.get("url", "").rsplit("/", 1)[-1]: item for item in prediction.get("extension", [])}
        results.append(RiskResult(
            label=RISK_LABELS.get(outcome, outcome.replace("_", " ").title()),
            probability=prediction.get("probabilityDecimal"),
            status=str(extensions.get("risk-status", {}).get("valueCode", "unbekannt")),
            missing_features=str(extensions.get("missing-features", {}).get("valueString", "")),
        ))
    return results
