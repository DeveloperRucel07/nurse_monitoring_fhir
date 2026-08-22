import requests
import json

# Unser lokaler HAPI FHIR Server
BASE_URL = "http://localhost:8080/fhir"

# Patientendaten (Testpatient)
patient_data = {
    "resourceType": "Patient",
    "name": [
        {
            "family": "Mustermann",
            "given": ["Erika"]
        }
    ],
    "gender": "female",
    "birthDate": "1990-05-15"
}

headers = {
    "Content-Type": "application/fhir+json",
    "Accept": "application/fhir+json"
}

# POST /Patient
response = requests.post(f"{BASE_URL}/Patient", json=patient_data, headers=headers)

print("Status Code:", response.status_code)
if response.status_code == 201:
    print("Patient erfolgreich angelegt!")
    print("Location:", response.headers.get("Location"))
    # ID extrahieren
    patient_id = response.json().get("id")
    print("Patienten-ID:", patient_id)
else:
    print("Fehler:")
    print(json.dumps(response.json(), indent=2))


# Falls der Patient erfolgreich angelegt wurde, verwenden wir die extrahierte ID
# Ansonsten verwenden wir eine Standard-ID
if 'patient_id' not in locals():
    patient_id = "1"

response = requests.get(f"{BASE_URL}/Patient/{patient_id}", headers=headers)
print("Status:", response.status_code)
print(json.dumps(response.json(), indent=2))