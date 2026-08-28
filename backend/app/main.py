from datetime import datetime

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import requests
import joblib
from backend.app.fhir_ml.ml.ml_utils import (
    IncompleteFeaturesError,
    load_model,
    load_risk_models,
    predict_patient_all_risks,
    predict_patient,
)

from backend.app.fhir_ml.fhir.FHIRclient import FHIRClient
from backend.app.models.models import (
    ClinicalRecordCreate,
    ClinicalRecordType,
    ObservationCreate,
    PatientCreate,
)

app = FastAPI(
    title="Pflege-Monitoring FHIR API",
    description="API zum Verwalten von Patienten und Observationen für das risiko-basierte Pflege-Monitoring.",
    version="0.1.0"
)

fhir = FHIRClient()

MODEL_PATH = "fall_risk_model.joblib"
model = load_model(MODEL_PATH)
RISK_MODELS = load_risk_models()


# ---------- Endpunkte ----------

@app.post("/Patient", status_code=status.HTTP_201_CREATED)
async def create_patient(patient: PatientCreate):
    """Legt einen neuen Patienten im FHIR-Server an."""
    # Pydantic-Modell in FHIR-JSON umwandeln
    patient_data = patient.model_dump(exclude_none=True)
    patient_data["resourceType"] = "Patient"

    try:
        created = fhir.create_patient(patient_data)
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

    return created

@app.get("/Patient/{patient_id}")
async def get_patient(patient_id: str):
    """Liest einen Patienten anhand seiner ID."""
    try:
        patient = fhir.get_patient(patient_id)
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

    return patient


@app.put("/Patient/{patient_id}")
async def update_patient(patient_id: str, patient: PatientCreate):
    """Aktualisiert die pflegerelevanten Stammdaten eines Patienten."""
    try:
        existing_patient = fhir.get_patient(patient_id)
        existing_patient.update(patient.model_dump(exclude_none=True))
        existing_patient["resourceType"] = "Patient"
        existing_patient["id"] = patient_id
        return fhir.update_patient(patient_id, existing_patient)
    except requests.exceptions.HTTPError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))


@app.delete("/Patient/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(patient_id: str):
    """Löscht einen Patienten im FHIR-Server."""
    try:
        fhir.delete_patient(patient_id)
    except requests.exceptions.HTTPError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))


@app.get("/Patient")
async def search_patients(family: Optional[str] = None, given: Optional[str] = None, birthdate: Optional[str] = None):
    """
    Sucht Patienten, optional nach Familienname, Vorname und/oder Geburtsdatum.
    """
    try:
        bundle = fhir.search_patients(
            family=family,
            given=given,
            birthdate=birthdate
        )
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

    return bundle


# ---------- Observation Endpunkte ----------

@app.post("/Observation", status_code=status.HTTP_201_CREATED)
async def create_observation(observation: ObservationCreate):
    """Legt eine neue Observation im FHIR-Server an."""
    observation_data = observation.model_dump(exclude_none=True)
    observation_data["resourceType"] = "Observation"

    try:
        created = fhir.create_observation(observation_data)
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

    return created

@app.get("/Observation/{observation_id}")
async def get_observation(observation_id: str):
    """Liest eine Observation anhand ihrer ID."""
    try:
        observation = fhir.get_observation(observation_id)
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

    return observation

@app.get("/Observation")
async def search_observations(subject: Optional[str] = None,patient_name: Optional[str] = None):
    """
    Sucht Observationen, optional gefiltert nach subject (z. B. subject=Patient/1)
    oder nach Patientenname (z. B. patient_name=Mustermann).
    """
    try:
        bundle = fhir.search_observations(
            subject_reference=subject,
            patient_name=patient_name
        )
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

    return bundle

@app.patch("/Observation/{observation_id}")
async def patch_observation(observation_id: str, patch: List[Dict[str, Any]]):
    """
    Führt ein JSON Patch auf eine Observation aus.
    Body-Beispiel: [{"op": "replace", "path": "/status", "value": "corrected"}]
    """
    try:
        updated = fhir.patch_observation(observation_id, patch)
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    return updated

@app.delete("/Observation/{observation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_observation(observation_id: str):
    """
    Löscht eine Observation.
    Gibt 204 No Content zurück.
    """
    try:
        fhir.delete_observation(observation_id)
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    # Kein Body bei 204


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
)
async def create_clinical_record(
    patient_id: str,
    record_type: ClinicalRecordType,
    record: ClinicalRecordCreate,
):
    try:
        return fhir.create_resource(
            record_type,
            clinical_resource(patient_id, record_type, record),
        )
    except requests.exceptions.HTTPError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))


@app.get("/Patient/{patient_id}/clinical-records/{record_type}")
async def list_clinical_records(
    patient_id: str,
    record_type: ClinicalRecordType,
):
    patient_parameter = "patient" if record_type == "AllergyIntolerance" else "subject"
    try:
        return fhir.search_resources(record_type, patient_id, patient_parameter)
    except requests.exceptions.HTTPError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))

from datetime import datetime, timezone

from fastapi import HTTPException


@app.get("/Patient/{patient_id}/nursing-risk-assessment", response_model=dict)
async def get_nursing_risk_assessment(patient_id: str):
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
    return {
        "resourceType": "RiskAssessment",
        "status": "final",
        "subject": {"reference": f"Patient/{patient_id}"},
        "occurrenceDateTime": datetime.now(timezone.utc).isoformat(),
        "prediction": [
            {
                "outcome": {
                    "text": risk_type,
                },
                "probabilityDecimal": assessment["probability"],
                "extension": [
                    {
                        "url": "http://example.org/fhir/StructureDefinition/risk-status",
                        "valueCode": assessment["status"],
                    },
                    {
                        "url": "http://example.org/fhir/StructureDefinition/missing-features",
                        "valueString": ", ".join(assessment["missing_features"]),
                    },
                ],
            }
            for risk_type, assessment in result["risks"].items()
        ],
        "basis": [
            {
                "display": "FHIR Patient and clinical Observation data",
            }
        ],
        "note": [
            {
                "text": (
                    "Automated synthetic nursing risk assessment. "
                    "This result does not replace professional nursing assessment."
                ),
            }
        ],
    }