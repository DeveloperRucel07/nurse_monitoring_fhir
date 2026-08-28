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

    def list_patients(
        self,
        family: str = "",
        given: str = "",
        birthdate: str = "",
    ) -> dict[str, Any]:
        params = {
            key: value
            for key, value in {
                "family": family,
                "given": given,
                "birthdate": birthdate,
            }.items()
            if value
        }
        return self._request("GET", "/Patient", params=params)

    def get_patient(self, patient_id: str) -> dict[str, Any]:
        return self._request("GET", f"/Patient/{self._safe_id(patient_id)}")

    def create_patient(self, given_name: str, family_name: str, gender: str, birth_date: str) -> dict[str, Any]:
        return self._request("POST", "/Patient", json={
            "name": [{"family": family_name.strip(), "given": [given_name.strip()]}],
            "gender": gender,
            "birthDate": birth_date,
        })

    def update_patient(
        self,
        patient_id: str,
        given_name: str,
        family_name: str,
        gender: str,
        birth_date: str,
    ) -> dict[str, Any]:
        return self._request("PUT", f"/Patient/{self._safe_id(patient_id)}", json={
            "name": [{"family": family_name.strip(), "given": [given_name.strip()]}],
            "gender": gender,
            "birthDate": birth_date,
        })

    def delete_patient(self, patient_id: str) -> None:
        self._request("DELETE", f"/Patient/{self._safe_id(patient_id)}")

    def list_observations(
        self,
        patient_id: str = "",
        patient_name: str = "",
    ) -> dict[str, Any]:
        params = {}
        if patient_id:
            params["subject"] = f"Patient/{self._safe_id(patient_id)}"
        if patient_name:
            params["patient_name"] = patient_name
        return self._request("GET", "/Observation", params=params)

    def get_observation(self, observation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/Observation/{self._safe_id(observation_id)}")

    def create_observation(self, patient_id: str, code: str, display: str, value: float, unit: str, effective: str) -> dict[str, Any]:
        return self._request("POST", "/Observation", json={
            "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}]},
            "subject": {"reference": f"Patient/{self._safe_id(patient_id)}"},
            "effectiveDateTime": effective,
            "valueQuantity": {"value": value, "unit": unit, "system": "http://unitsofmeasure.org", "code": unit},
        })

    def create_blood_pressure(
        self,
        patient_id: str,
        systolic: float,
        diastolic: float,
        effective: str,
    ) -> dict[str, Any]:
        safe_patient_id = self._safe_id(patient_id)
        return self._request("POST", "/Observation", json={
            "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9", "display": "Blutdruck"}]},
            "subject": {"reference": f"Patient/{safe_patient_id}"},
            "effectiveDateTime": effective,
            "component": [
                {"code": {"coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolisch"}]}, "valueQuantity": {"value": systolic, "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"}},
                {"code": {"coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolisch"}]}, "valueQuantity": {"value": diastolic, "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"}},
            ],
        })

    def patch_observation_status(self, observation_id: str, status: str) -> dict[str, Any]:
        return self._request("PATCH", f"/Observation/{self._safe_id(observation_id)}", json=[
            {"op": "replace", "path": "/status", "value": status},
        ])

    def delete_observation(self, observation_id: str) -> None:
        self._request("DELETE", f"/Observation/{self._safe_id(observation_id)}")

    def list_clinical_records(
        self,
        patient_id: str,
        record_type: str,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/Patient/{self._safe_id(patient_id)}/clinical-records/{record_type}",
        )

    def create_clinical_record(
        self,
        patient_id: str,
        record_type: str,
        display: str,
        code: str,
        system: str,
        status: str,
        details: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/Patient/{self._safe_id(patient_id)}/clinical-records/{record_type}",
            json={
                "display": display.strip(),
                "code": code.strip() or None,
                "system": system.strip(),
                "status": status,
                "details": details.strip() or None,
            },
        )

    def assess_risks(self, patient_id: str) -> dict[str, Any]:
        return self._request("GET", f"/Patient/{self._safe_id(patient_id)}/nursing-risk-assessment")
