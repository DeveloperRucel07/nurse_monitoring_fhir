from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import requests

from app.fhir_ml.fhir.FHIRclient import FHIRClient
from backend.app.models.models import PatientCreate

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
async def search_patients(family: Optional[str] = None):
    """Sucht Patienten, optional nach Familienname."""
    try:
        bundle = fhir.search_patients(family)
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

    return bundle