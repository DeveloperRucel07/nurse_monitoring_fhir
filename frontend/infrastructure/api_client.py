import os
import re
from typing import Any

import requests


class ApiError(RuntimeError):
    pass


class FhirApiClient:
    """HTTP adapter for the trusted backend API. It never logs response bodies."""

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("BACKEND_API_URL", "http://localhost:8000")).rstrip("/")
        self.token = token or os.getenv("BACKEND_API_TOKEN")

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = {"Accept": "application/fhir+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = requests.request(method, f"{self.base_url}{path}", headers=headers, timeout=10, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None
        except requests.RequestException as exc:
            raise ApiError("Backend ist momentan nicht erreichbar.") from exc

    @staticmethod
    def _safe_id(patient_id: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9.-]{1,64}", patient_id):
            raise ApiError("Ungültige Patienten-ID.")
        return patient_id

    def list_patients(self, family: str = "") -> dict[str, Any]:
        return self._request("GET", "/Patient", params={"family": family} if family else {})

    def get_patient(self, patient_id: str) -> dict[str, Any]:
        return self._request("GET", f"/Patient/{self._safe_id(patient_id)}")

    def create_patient(self, given_name: str, family_name: str, gender: str, birth_date: str) -> dict[str, Any]:
        return self._request("POST", "/Patient", json={
            "name": [{"family": family_name.strip(), "given": [given_name.strip()]}],
            "gender": gender,
            "birthDate": birth_date,
        })

    def list_observations(self, patient_id: str) -> dict[str, Any]:
        return self._request("GET", "/Observation", params={"subject": f"Patient/{self._safe_id(patient_id)}"})

    def create_observation(self, patient_id: str, code: str, display: str, value: float, unit: str, effective: str) -> dict[str, Any]:
        return self._request("POST", "/Observation", json={
            "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}]},
            "subject": {"reference": f"Patient/{self._safe_id(patient_id)}"},
            "effectiveDateTime": effective,
            "valueQuantity": {"value": value, "unit": unit, "system": "http://unitsofmeasure.org", "code": unit},
        })

    def assess_risks(self, patient_id: str) -> dict[str, Any]:
        return self._request("GET", f"/Patient/{self._safe_id(patient_id)}/nursing-risk-assessment")
