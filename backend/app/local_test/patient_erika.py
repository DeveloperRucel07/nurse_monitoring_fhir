import requests
import json
import os

BASE_URL = os.getenv("FHIR_SERVER_URL", "http://localhost:8080/fhir")

patient_id = None  # Variable zum Speichern der Patienten-ID nach dem Anlegen
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



if 'patient_id' not in locals():
    patient_id = "1"


###Observation anlegen
observation_data = {
  "resourceType": "Observation",
  "status": "final",
  "code": {
    "coding": [
      {
        "system": "http://loinc.org",
        "code": "85354-9",
        "display": "Blood pressure panel"
      }
    ]
  },
  "subject": {
    "reference": f"Patient/{patient_id}" if 'patient_id' in locals() else "Patient/1"
  },
  "effectiveDateTime": "2026-08-21T09:05:00+02:00",
  "component": [
    {
      "code": {
        "coding": [
          {
            "system": "http://loinc.org",
            "code": "8480-6",
            "display": "Systolic blood pressure"
          }
        ]
      },
      "valueQuantity": {
        "value": 125,
        "unit": "mmHg",
        "system": "http://unitsofmeasure.org",
        "code": "mm[Hg]"
      }
    },
    {
      "code": {
        "coding": [
          {
            "system": "http://loinc.org",
            "code": "8462-4",
            "display": "Diastolic blood pressure"
          }
        ]
      },
      "valueQuantity": {
        "value": 80,
        "unit": "mmHg",
        "system": "http://unitsofmeasure.org",
        "code": "mm[Hg]"
      }
    }
  ]
}

###Observation create
response = requests.post(f"{BASE_URL}/Observation", json=observation_data, headers=headers)


print("Status:", response.status_code)
if response.status_code == 201:
    print("Observation erfolgreich angelegt!")
    print("Location:", response.headers.get("Location"))
    # ID extrahieren
    observation_id = response.json().get("id")
    print("Observation-ID:", observation_id)
else:
    print("Fehler:")
    print(json.dumps(response.json(), indent=2))