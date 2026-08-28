import requests
from typing import List, Optional, Dict, Any
from backend.app.core.config import BASE_URL

class FHIRClient:
    """Wrapper für den HAPI FHIR Server."""

    def __init__(self, base_url: str = BASE_URL):
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

    def update_patient(
        self,
        patient_id: str,
        patient_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        response = requests.put(
            f"{self.base_url}/Patient/{patient_id}",
            json=patient_data,
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def delete_patient(self, patient_id: str) -> None:
        response = requests.delete(
            f"{self.base_url}/Patient/{patient_id}",
            headers=self.headers,
        )
        response.raise_for_status()

    def search_patients(self, family: Optional[str] = None, given: Optional[str] = None, birthdate: Optional[str] = None ) -> Dict[str, Any]:
        """
        Sucht Patienten, optional nach Familienname, Vorname und/oder Geburtsdatum.
        Alle Parameter sind optional und werden kombiniert (UND-Verknüpfung).
        """
        url = f"{self.base_url}/Patient"
        params = {}
        if family:
            params["family"] = family
        if given:
            params["given"] = given
        if birthdate:
            params["birthdate"] = birthdate
        response = requests.get(url, params=params, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def create_observation(self, observation_data: Dict[str, Any]) -> Dict[str, Any]:
        """Legt eine neue Observation an und gibt die Antwort als Dict zurück."""
        url = f"{self.base_url}/Observation"
        response = requests.post(url, json=observation_data, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def create_resource(
        self,
        resource_type: str,
        resource_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/{resource_type}",
            json=resource_data,
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def search_resources(
        self,
        resource_type: str,
        patient_id: str,
        patient_parameter: str = "subject",
    ) -> Dict[str, Any]:
        response = requests.get(
            f"{self.base_url}/{resource_type}",
            params={patient_parameter: f"Patient/{patient_id}"},
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    def get_observation(self, observation_id: str) -> Dict[str, Any]:
        """Liest eine Observation anhand ihrer ID."""
        url = f"{self.base_url}/Observation/{observation_id}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()


    def search_observations(self,subject_reference: Optional[str] = None, patient_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Sucht Observationen, optional gefiltert nach subject (z. B. "Patient/123")
        oder nach Patientenname (Chaining, z. B. "Mustermann").
        """
        url = f"{self.base_url}/Observation"
        params = {}
        if subject_reference:
            params["subject"] = subject_reference
        if patient_name:
            # Chaining: Suche über die Patient-Referenz hinweg nach dem Namen
            params["subject:Patient.name"] = patient_name
        response = requests.get(url, params=params, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def delete_observation(self, observation_id: str) -> None:
        """
        Löscht eine Observation anhand ihrer ID.
        Wirft eine Exception bei Fehler (z. B. 404).
        """
        url = f"{self.base_url}/Observation/{observation_id}"
        response = requests.delete(url, headers=self.headers)
        response.raise_for_status()
        # Erfolgreich: 204 No Content

    def patch_observation(self, observation_id: str, patch_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Führt ein JSON Patch (RFC 6902) auf eine Observation aus.
        patch_data ist eine Liste von Operationen, z. B.:
        [{"op": "replace", "path": "/status", "value": "corrected"}]
        """
        headers = {
            "Content-Type": "application/json-patch+json",
            "Accept": "application/fhir+json"
        }

        url = f"{self.base_url}/Observation/{observation_id}"
        response = requests.patch(url, json=patch_data, headers=headers)
        response.raise_for_status()
        return response.json()