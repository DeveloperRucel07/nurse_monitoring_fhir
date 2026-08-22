import requests
from typing import Optional, Dict, Any

class FHIRClient:
    """Wrapper für den HAPI FHIR Server."""

    def __init__(self, base_url: str = "http://localhost:8080/fhir"):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json"
        }

    def create_patient(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """Legt einen neuen Patienten an und gibt die Antwort als Dict zurück."""
        url = f"{self.base_url}/Patient"
        response = requests.post(url, json=patient_data, headers=self.headers)
        response.raise_for_status()  # Wirft Exception bei 4xx/5xx
        return response.json()

    def get_patient(self, patient_id: str) -> Dict[str, Any]:
        """Liest einen Patienten anhand seiner ID."""
        url = f"{self.base_url}/Patient/{patient_id}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def search_patients(self, family: Optional[str] = None) -> Dict[str, Any]:
        """Sucht Patienten, optional nach Familienname."""
        url = f"{self.base_url}/Patient"
        params = {}
        if family:
            params["family"] = family
        response = requests.get(url, params=params, headers=self.headers)
        response.raise_for_status()
        return response.json()