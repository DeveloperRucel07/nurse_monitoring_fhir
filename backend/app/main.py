import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.auth import auth_app
from backend.app.core.config import ML_MODE
from backend.app.core.exceptions import FhirClientError
from backend.app.core.logging import AuditMiddleware
from backend.app.core.security import (
    get_current_client,
    require_delete_access,
    require_read_access,
    require_write_access,
)
from backend.app.fhir_ml.fhir.FHIRclient import FHIRClient
from backend.app.fhir_ml.ml.ml_utils import load_risk_models, predict_patient_all_risks
from backend.app.models.models import (
    ClinicalRecordCreate,
    ClinicalRecordSearch,
    ClinicalRecordType,
    NursingReportCreate,
    ObservationCreate,
    PatientContextRequest,
    PatientCreate,
    PatientSearch,
    RiskAssessmentResponse,
    VitalMeasurementCreate,
)

app = FastAPI(
    title="Pflege-Monitoring FHIR API",
    description="API zum Verwalten von Patienten und Observationen für das risiko-basierte Pflege-Monitoring.",
    version="0.1.0",
    dependencies=[Depends(get_current_client)],
)

app.add_middleware(AuditMiddleware)
app.mount("/auth", auth_app)


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    issues = []
    for error in exc.errors()[:20]:
        location = ".".join(
            str(part) for part in error.get("loc", ()) if part != "body"
        )
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

RISK_MODELS = load_risk_models() if ML_MODE == "synthetic-demo" else {}

RISK_CODE_SYSTEM = "https://monitoring-pflege.local/fhir/CodeSystem/nursing-risk"
RISK_EXTENSION_BASE = "https://monitoring-pflege.local/fhir/StructureDefinition"
RISK_DISPLAYS = {
    "fall": "Sturzereignis – synthetisches Demo-Ziel",
    "pressure_ulcer": "Dekubitus – synthetisches Demo-Ziel",
    "pain_escalation": "Schmerzzunahme – synthetisches Demo-Ziel",
    "clinical_deterioration": "Klinische Verschlechterung – synthetisches Demo-Ziel",
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
def search_patients(
    family: Optional[str] = None,
    given: Optional[str] = None,
    birthdate: Optional[str] = None,
):
    """
    Sucht Patienten, optional nach Familienname, Vorname und/oder Geburtsdatum.
    """
    return fhir.search_patients(
        family=family,
        given=given,
        birthdate=birthdate,
    )


@app.post("/ui/patients/search", dependencies=[Depends(require_read_access)])
def search_patients_for_ui(search: PatientSearch):
    """Sucht Patienten ohne Namen oder Geburtsdaten in URL und Access-Logs."""
    return fhir.search_patients(
        family=search.family,
        given=search.given,
        birthdate=search.birthdate.isoformat() if search.birthdate else None,
    )


@app.post("/ui/patient/read", dependencies=[Depends(require_read_access)])
def read_patient_for_ui(context: PatientContextRequest):
    """Liest einen Patienten, ohne dessen ID in die URL aufzunehmen."""
    return fhir.get_patient(context.patientId)


@app.post("/ui/patient/observations", dependencies=[Depends(require_read_access)])
def read_patient_observations_for_ui(context: PatientContextRequest):
    return fhir.search_observations(subject_reference=f"Patient/{context.patientId}")


@app.post("/ui/patient/clinical-records", dependencies=[Depends(require_read_access)])
def read_patient_clinical_records_for_ui(search: ClinicalRecordSearch):
    patient_parameter = (
        "patient" if search.recordType == "AllergyIntolerance" else "subject"
    )
    return fhir.search_resources(
        search.recordType,
        search.patientId,
        patient_parameter,
    )


VITAL_MEASUREMENT_DEFINITIONS: Dict[str, Dict[str, str]] = {
    "heart-rate": {
        "code": "8867-4",
        "display": "Heart rate",
        "unit": "/min",
        "unitCode": "/min",
    },
    "temperature": {
        "code": "8310-5",
        "display": "Body temperature",
        "unit": "°C",
        "unitCode": "Cel",
    },
    "respiratory-rate": {
        "code": "9279-1",
        "display": "Respiratory rate",
        "unit": "/min",
        "unitCode": "/min",
    },
    "oxygen-saturation": {
        "code": "2708-6",
        "display": "Oxygen saturation",
        "unit": "%",
        "unitCode": "%",
    },
    "pain": {
        "code": "72514-3",
        "display": "Pain severity",
        "unit": "score",
        "unitCode": "{score}",
    },
    "morse-score": {
        "code": "59460-6",
        "display": "Morse Fall Scale total score",
        "unit": "score",
        "unitCode": "{score}",
    },
}


def _loinc_concept(code: str, display: str) -> Dict[str, Any]:
    return {
        "coding": [
            {
                "system": "http://loinc.org",
                "code": code,
                "display": display,
            }
        ]
    }


def vital_measurement_resource(measurement: VitalMeasurementCreate) -> Dict[str, Any]:
    resource: Dict[str, Any] = {
        "resourceType": "Observation",
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "vital-signs",
                        "display": "Vital Signs",
                    }
                ]
            }
        ],
        "subject": {"reference": f"Patient/{measurement.patientId}"},
        "effectiveDateTime": measurement.measuredAt.isoformat(),
    }

    if measurement.measurementType == "blood-pressure":
        resource["code"] = _loinc_concept("85354-9", "Blood pressure panel")
        resource["component"] = [
            {
                "code": _loinc_concept("8480-6", "Systolic blood pressure"),
                "valueQuantity": {
                    "value": measurement.systolic,
                    "unit": "mmHg",
                    "system": "http://unitsofmeasure.org",
                    "code": "mm[Hg]",
                },
            },
            {
                "code": _loinc_concept("8462-4", "Diastolic blood pressure"),
                "valueQuantity": {
                    "value": measurement.diastolic,
                    "unit": "mmHg",
                    "system": "http://unitsofmeasure.org",
                    "code": "mm[Hg]",
                },
            },
        ]
        return resource

    definition = VITAL_MEASUREMENT_DEFINITIONS[measurement.measurementType]
    resource["code"] = _loinc_concept(definition["code"], definition["display"])
    resource["valueQuantity"] = {
        "value": measurement.value,
        "unit": definition["unit"],
        "system": "http://unitsofmeasure.org",
        "code": definition["unitCode"],
    }
    return resource


@app.post(
    "/ui/patient/vital-measurements",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_write_access)],
)
def create_vital_measurement_for_ui(measurement: VitalMeasurementCreate):
    """Creates a vital sign using server-controlled LOINC and UCUM metadata."""
    return fhir.create_observation(vital_measurement_resource(measurement))


@app.post(
    "/ui/patient/nursing-reports",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_write_access)],
)
def create_nursing_report_for_ui(report: NursingReportCreate):
    """Stores a plain-text nursing note without placing identifiers in the URL."""
    record = ClinicalRecordCreate(
        display=report.title,
        status="completed",
        details=report.text,
    )
    return fhir.create_resource(
        "ClinicalImpression",
        clinical_resource(report.patientId, "ClinicalImpression", record),
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
def search_observations(
    subject: Optional[str] = None, patient_name: Optional[str] = None
):
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
        concept["coding"] = [
            {
                "system": record.system,
                "code": record.code,
                "display": record.display,
            }
        ]
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
            "clinicalStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": record.status,
                    }
                ]
            },
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
            "clinicalStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                        "code": record.status,
                    }
                ]
            },
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
    summary="Experimentelle synthetische Modellsimulation",
    description=(
        "Nur für technische Demonstrationen. Die Ausgabe ist nicht klinisch "
        "validiert und darf nicht für Pflege- oder Behandlungsentscheidungen "
        "verwendet werden."
    ),
    dependencies=[Depends(require_read_access)],
)
def get_nursing_risk_assessment(patient_id: str, response: Response):
    """Create an explicitly non-clinical simulation from synthetic models."""
    if ML_MODE != "synthetic-demo":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Die experimentelle ML-Demonstration ist deaktiviert. "
                "Sie ist nicht für den klinischen Einsatz freigegeben."
            ),
        )
    if not RISK_MODELS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Keine Pflegerisikomodelle geladen.",
        )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Model-Purpose"] = "synthetic-demo-only"
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
                    "valueCode": "synthetic-demo-result",
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
        elif assessment_status == "incomplete_data":
            missing_features = assessment.get("missing_features")
            if not isinstance(missing_features, list) or not all(
                isinstance(feature, str) and feature for feature in missing_features
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
        "status": "preliminary",
        "subject": {"reference": f"Patient/{patient_id}"},
        "occurrenceDateTime": datetime.now(timezone.utc).isoformat(),
        "extension": [
            {
                "url": f"{RISK_EXTENSION_BASE}/model-purpose",
                "valueCode": "demonstration-only",
            },
            {
                "url": f"{RISK_EXTENSION_BASE}/clinical-validation-status",
                "valueCode": "not-clinically-validated",
            },
            {
                "url": f"{RISK_EXTENSION_BASE}/training-data-kind",
                "valueCode": "synthetic",
            },
        ],
        "method": {
            "coding": [
                {
                    "system": RISK_CODE_SYSTEM,
                    "code": "synthetic-demo-ml-model",
                    "display": "Synthetisches ML-Demonstrationsmodell",
                }
            ],
            "text": "Nicht klinisch validierte technische Modellsimulation",
        },
        "prediction": predictions,
        "note": [
            {
                "text": (
                    "Automatisierte Auswertung eines synthetisch trainierten Modells. "
                    "Die Prozentwerte sind keine validierten Erkrankungs- oder "
                    "Ereigniswahrscheinlichkeiten. Die Ausgabe darf nicht für Diagnose, "
                    "Triage, Pflegeplanung oder Behandlung verwendet werden."
                ),
            }
        ],
    }
    fhir.validate_resource("RiskAssessment", resource)
    return RiskAssessmentResponse.model_validate(resource)


@app.post(
    "/ui/patient/risk-assessment",
    response_model=RiskAssessmentResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(require_read_access)],
)
def get_nursing_risk_assessment_for_ui(
    context: PatientContextRequest,
    response: Response,
):
    """UI-Zugriff ohne Patienten-ID in URL oder Browserhistorie."""
    return get_nursing_risk_assessment(context.patientId, response)
