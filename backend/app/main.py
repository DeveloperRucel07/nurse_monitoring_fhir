from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import requests

from backend.app.fhir_ml.fhir.FHIRclient import FHIRClient
from backend.app.models.models import ObservationCreate, ObservationCreate, PatientCreate

app = FastAPI(
    title="Pflege-Monitoring FHIR API",
    description="API zum Verwalten von Patienten und Observationen für das risiko-basierte Pflege-Monitoring.",
    version="0.1.0"
)

fhir = FHIRClient()


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