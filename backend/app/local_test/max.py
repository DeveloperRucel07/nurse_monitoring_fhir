import requests
import json
import os

BASE_URL = os.getenv("FHIR_SERVER_URL", "http://localhost:8080/fhir")

headers = {
    "Content-Type": "application/fhir+json",
    "Accept": "application/fhir+json"
}


# ============================================================
# Patient
# ============================================================

patient_data = {
    "resourceType": "Patient",
    "name": [
        {
            "family": "Mustermann",
            "given": ["Max"]
        }
    ],
    "gender": "male",
    "birthDate": "1990-05-15"
}

response = requests.post(
    f"{BASE_URL}/Patient",
    json=patient_data,
    headers=headers
)

print("Patient Status:", response.status_code)

if response.status_code == 201:
    patient_id = response.json()["id"]
    print("Patient erfolgreich angelegt:", patient_id)
else:
    print(json.dumps(response.json(), indent=2))
    exit()


# ============================================================
# Blutdruck
# LOINC 85354-9 = Blood pressure panel
# ============================================================

blood_pressure = {
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
        "reference": f"Patient/{patient_id}"
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

requests.post(
    f"{BASE_URL}/Observation",
    json=blood_pressure,
    headers=headers
)


# ============================================================
# Vitalwerte
# ============================================================

observations = [
    {
        "code": "8867-4",
        "display": "Heart rate",
        "value": 72,
        "unit": "/min",
        "system": "http://unitsofmeasure.org"
    },
    {
        "code": "8310-5",
        "display": "Body temperature",
        "value": 36.7,
        "unit": "Cel",
        "system": "http://unitsofmeasure.org"
    },
    {
        "code": "9279-1",
        "display": "Respiratory rate",
        "value": 16,
        "unit": "/min",
        "system": "http://unitsofmeasure.org"
    },
    {
        "code": "2708-6",
        "display": "Oxygen saturation",
        "value": 98,
        "unit": "%",
        "system": "http://unitsofmeasure.org"
    }
]


for data in observations:

    observation = {
        "resourceType": "Observation",
        "status": "final",

        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": data["code"],
                    "display": data["display"]
                }
            ]
        },

        "subject": {
            "reference": f"Patient/{patient_id}"
        },

        "effectiveDateTime": "2026-08-21T09:05:00+02:00",

        "valueQuantity": {
            "value": data["value"],
            "unit": data["unit"],
            "system": data["system"],
            "code": data["unit"]
        }
    }

    response = requests.post(
        f"{BASE_URL}/Observation",
        json=observation,
        headers=headers
    )

    print(
        data["display"],
        "→",
        response.status_code
    )