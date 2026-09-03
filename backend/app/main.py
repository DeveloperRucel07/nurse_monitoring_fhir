import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.core.exceptions import FhirClientError
from backend.app.core.logging import AuditMiddleware
from backend.app.core.security import (
    get_current_client,
    require_delete_access,
    require_read_access,
    require_write_access,
)
from backend.app.fhir_ml.ml.ml_utils import (
    load_model,
    load_risk_models,
    predict_patient_all_risks,
)
from backend.app.fhir_ml.fhir.FHIRclient import FHIRClient
from backend.app.models.models import (
    ClinicalRecordCreate,
    ClinicalRecordType,
    ObservationCreate,
    PatientCreate,
    RiskAssessmentResponse,
)

app = FastAPI(
    title="Pflege-Monitoring FHIR API",
    description="API zum Verwalten von Patienten und Observationen für das risiko-basierte Pflege-Monitoring.",
    version="0.1.0",
    dependencies=[Depends(get_current_client)],
)

app.add_middleware(AuditMiddleware)


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    issues = []
    for error in exc.errors()[:20]:
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
        message = str(error.get("msg", "Ungültiger Wert."))
        diagnostics = f"{location}: {message}" if location else message
        issues.append(
            {
                "severity": "error",
                "code": "invalid",
                "diagnostics": diagnostics,
            }
        )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"resourceType": "OperationOutcome", "issue": issues},
        media_type="application/fhir+json",
    )


@app.exception_handler(FhirClientError)
async def handle_fhir_client_error(
    _request: Request,
    exc: FhirClientError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.operation_outcome(),
        media_type="application/fhir+json",
    )

fhir = FHIRClient()

MODEL_PATH = "fall_risk_model.joblib"
model = load_model(MODEL_PATH)
RISK_MODELS = load_risk_models()

RISK_CODE_SYSTEM = "https://monitoring-pflege.local/fhir/CodeSystem/nursing-risk"
RISK_EXTENSION_BASE = (
    "https://monitoring-pflege.local/fhir/StructureDefinition"
)
RISK_DISPLAYS = {
    "fall": "Sturzrisiko",
    "pressure_ulcer": "Dekubitusrisiko",
    "pain_escalation": "Risiko einer Schmerzzunahme",
    "clinical_deterioration": "Risiko einer klinischen Verschlechterung",
}


# ---------- Endpunkte ----------

@app.post(
    "/Patient",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_write_access)],
)
def create_patient(patient: PatientCreate):
    """Legt einen neuen Patienten im FHIR-Server an."""
    patient_data = patient.model_dump(mode="json", exclude_none=True)
    patient_data["resourceType"] = "Patient"
    return fhir.create_patient(patient_data)

@app.get("/Patient/{patient_id}", dependencies=[Depends(require_read_access)])
def get_patient(patient_id: str):
    """Liest einen Patienten anhand seiner ID."""
    return fhir.get_patient(patient_id)


@app.put("/Patient/{patient_id}", dependencies=[Depends(require_write_access)])
def update_patient(patient_id: str, patient: PatientCreate):
    """Aktualisiert die pflegerelevanten Stammdaten eines Patienten."""
    existing_patient = fhir.get_patient(patient_id)
    existing_patient.update(patient.model_dump(mode="json", exclude_none=True))
    existing_patient["resourceType"] = "Patient"
    existing_patient["id"] = patient_id
    return fhir.update_patient(patient_id, existing_patient)


@app.delete(
    "/Patient/{patient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_delete_access)],
)
def delete_patient(patient_id: str):
    """Löscht einen Patienten im FHIR-Server."""
    fhir.delete_patient(patient_id)


@app.get("/Patient", dependencies=[Depends(require_read_access)])
def search_patients(family: Optional[str] = None, given: Optional[str] = None, birthdate: Optional[str] = None):
    """
    Sucht Patienten, optional nach Familienname, Vorname und/oder Geburtsdatum.
    """
    return fhir.search_patients(
        family=family,
        given=given,
        birthdate=birthdate,
    )


# ---------- Observation Endpunkte ----------

@app.post(
    "/Observation",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_write_access)],
)
def create_observation(observation: ObservationCreate):
    """Legt eine neue Observation im FHIR-Server an."""
    observation_data = observation.model_dump(mode="json", exclude_none=True)
    observation_data["resourceType"] = "Observation"
    return fhir.create_observation(observation_data)

@app.get("/Observation/{observation_id}", dependencies=[Depends(require_read_access)])
def get_observation(observation_id: str):
    """Liest eine Observation anhand ihrer ID."""
    return fhir.get_observation(observation_id)

@app.get("/Observation", dependencies=[Depends(require_read_access)])
def search_observations(subject: Optional[str] = None,patient_name: Optional[str] = None):
    """
    Sucht Observationen, optional gefiltert nach subject (z. B. subject=Patient/1)
    oder nach Patientenname (z. B. patient_name=Mustermann).
    """
    return fhir.search_observations(
        subject_reference=subject,
        patient_name=patient_name,
    )

@app.patch(
    "/Observation/{observation_id}",
    dependencies=[Depends(require_write_access)],
)
def patch_observation(observation_id: str, patch: List[Dict[str, Any]]):
    """
    Führt ein JSON Patch auf eine Observation aus.
    Body-Beispiel: [{"op": "replace", "path": "/status", "value": "corrected"}]
    """
    return fhir.patch_observation(observation_id, patch)

@app.delete(
    "/Observation/{observation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_delete_access)],
)
def delete_observation(observation_id: str):
    """
    Löscht eine Observation.
    Gibt 204 No Content zurück.
    """
    fhir.delete_observation(observation_id)


def codeable_concept(record: ClinicalRecordCreate) -> Dict[str, Any]:
    concept: Dict[str, Any] = {"text": record.display}
    if record.code:
        concept["coding"] = [{
            "system": record.system,
            "code": record.code,
            "display": record.display,
        }]
    return concept


def clinical_resource(
    patient_id: str,
    record_type: ClinicalRecordType,
    record: ClinicalRecordCreate,
) -> Dict[str, Any]:
    concept = codeable_concept(record)
    reference = {"reference": f"Patient/{patient_id}"}

    if record_type == "Condition":
        resource = {
            "resourceType": record_type,
            "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": record.status}]},
            "code": concept,
            "subject": reference,
        }
    elif record_type == "MedicationStatement":
        resource = {
            "resourceType": record_type,
            "status": record.status,
            "medicationCodeableConcept": concept,
            "subject": reference,
        }
    elif record_type == "AllergyIntolerance":
        resource = {
            "resourceType": record_type,
            "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "code": record.status}]},
            "code": concept,
            "patient": reference,
        }
    elif record_type == "ClinicalImpression":
        resource = {
            "resourceType": record_type,
            "status": "completed",
            "subject": reference,
            "date": datetime.now(timezone.utc).isoformat(),
            "summary": record.display,
        }
        if record.details:
            resource["description"] = record.details
    else:
        resource = {
            "resourceType": record_type,
            "status": record.status,
            "intent": "plan",
            "subject": reference,
            "title": record.display,
        }
        if record.details:
            resource["description"] = record.details
    return resource


@app.post(
    "/Patient/{patient_id}/clinical-records/{record_type}",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_write_access)],
)
def create_clinical_record(
    patient_id: str,
    record_type: ClinicalRecordType,
    record: ClinicalRecordCreate,
):
    return fhir.create_resource(
        record_type,
        clinical_resource(patient_id, record_type, record),
    )


@app.get(
    "/Patient/{patient_id}/clinical-records/{record_type}",
    dependencies=[Depends(require_read_access)],
)
def list_clinical_records(
    patient_id: str,
    record_type: ClinicalRecordType,
):
    patient_parameter = "patient" if record_type == "AllergyIntolerance" else "subject"
    return fhir.search_resources(record_type, patient_id, patient_parameter)

@app.get(
    "/Patient/{patient_id}/nursing-risk-assessment",
    response_model=RiskAssessmentResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(require_read_access)],
)
def get_nursing_risk_assessment(patient_id: str):
    """Erstellt eine gemeinsame Bewertung der verfügbaren Pflegerisiken."""
    if not RISK_MODELS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Keine Pflegerisikomodelle geladen.",
        )
    result = predict_patient_all_risks(
        patient_id=patient_id,
        fhir_client=fhir,
        models=RISK_MODELS,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient/{patient_id} nicht gefunden.",
        )

    predictions = []
    for risk_type, assessment in result["risks"].items():
        if risk_type not in RISK_DISPLAYS or not isinstance(assessment, dict):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Das Risikomodell hat eine ungültige Ausgabe geliefert.",
            )

        prediction: dict[str, Any] = {
            "outcome": {
                "coding": [
                    {
                        "system": RISK_CODE_SYSTEM,
                        "code": risk_type,
                        "display": RISK_DISPLAYS[risk_type],
                    }
                ],
                "text": risk_type,
            },
            "extension": [
                {
                    "url": f"{RISK_EXTENSION_BASE}/risk-status",
                    "valueCode": "assessed",
                }
            ],
        }

        assessment_status = assessment.get("status")
        if assessment_status == "assessed":
            probability = assessment.get("probability")
            label = assessment.get("label")
            if (
                isinstance(probability, bool)
                or not isinstance(probability, (int, float))
                or not math.isfinite(float(probability))
                or not 0 <= float(probability) <= 1
                or label not in {"low", "high"}
            ):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Das Risikomodell hat eine ungültige Ausgabe geliefert.",
                )
            prediction["probabilityDecimal"] = float(probability)
            prediction["qualitativeRisk"] = {
                "coding": [
                    {
                        "system": RISK_CODE_SYSTEM,
                        "code": label,
                        "display": "Hohes Risiko" if label == "high" else "Niedriges Risiko",
                    }
                ]
            }
        elif assessment_status == "incomplete_data":
            missing_features = assessment.get("missing_features")
            if not isinstance(missing_features, list) or not all(
                isinstance(feature, str) and feature
                for feature in missing_features
            ):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Das Risikomodell hat eine ungültige Ausgabe geliefert.",
                )
            prediction["extension"][0]["valueCode"] = "incomplete-data"
            prediction["extension"].append(
                {
                    "url": f"{RISK_EXTENSION_BASE}/missing-features",
                    "valueString": ", ".join(missing_features),
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Das Risikomodell hat eine ungültige Ausgabe geliefert.",
            )
        predictions.append(prediction)

    resource = {
        "resourceType": "RiskAssessment",
        "status": "final",
        "subject": {"reference": f"Patient/{patient_id}"},
        "occurrenceDateTime": datetime.now(timezone.utc).isoformat(),
        "method": {
            "coding": [
                {
                    "system": RISK_CODE_SYSTEM,
                    "code": "synthetic-ml-model",
                    "display": "Synthetisches ML-Modell",
                }
            ],
            "text": "Experimentelle, nicht klinisch validierte ML-Auswertung",
        },
        "prediction": predictions,
        "note": [
            {
                "text": (
                    "Automatisierte Auswertung eines synthetisch trainierten Modells. "
                    "Das Ergebnis ist keine klinische Entscheidung und ersetzt keine "
                    "professionelle Pflegeeinschätzung."
                ),
            }
        ],
    }
    fhir.validate_resource("RiskAssessment", resource)
    return RiskAssessmentResponse.model_validate(resource)
