from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests
from dotenv import load_dotenv


# ============================================================
# Configuration
# ============================================================

load_dotenv()

FHIR_SERVER_URL = os.getenv(
    "FHIR_SERVER_URL",
    "http://localhost:8080/fhir",
).rstrip("/")

FHIR_TIMEOUT = float(
    os.getenv("FHIR_TIMEOUT", "30")
)

FHIR_RETRIES = int(
    os.getenv("FHIR_RETRIES", "3")
)

FHIR_BATCH_SIZE = int(
    os.getenv("FHIR_BATCH_SIZE", "10")
)

PATIENT_IDENTIFIER_SYSTEM = os.getenv(
    "PATIENT_IDENTIFIER_SYSTEM",
    "https://monitoring-pflege.local/identifier/patient",
).strip()

ENCOUNTER_IDENTIFIER_SYSTEM = os.getenv(
    "ENCOUNTER_IDENTIFIER_SYSTEM",
    "https://monitoring-pflege.local/identifier/encounter",
).strip()

if not PATIENT_IDENTIFIER_SYSTEM or not ENCOUNTER_IDENTIFIER_SYSTEM:
    raise RuntimeError("FHIR identifier systems must not be empty.")


# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("fhir-seed")


# ============================================================
# Terminology systems
# ============================================================

LOINC_SYSTEM = "http://loinc.org"
SNOMED_SYSTEM = "http://snomed.info/sct"
ATC_SYSTEM = "http://www.whocc.no/atc"
UCUM_SYSTEM = "http://unitsofmeasure.org"
RISK_LABEL_SYSTEM = "http://example.org/fhir/CodeSystem/nursing-risk-label"

RISK_LABEL_CODES = {
    "fall": "nursing-risk-fall",
    "pressure_ulcer": "nursing-risk-pressure-ulcer",
    "pain_escalation": "nursing-risk-pain-escalation",
    "clinical_deterioration": "nursing-risk-clinical-deterioration",
}


# ============================================================
# LOINC
# ============================================================

LOINC = {
    "HEART_RATE": "8867-4",
    "SYSTOLIC_BP": "8480-6",
    "DIASTOLIC_BP": "8462-4",
    "BLOOD_PRESSURE": "85354-9",
    "TEMPERATURE": "8310-5",
    "RESPIRATORY_RATE": "9279-1",
    "OXYGEN_SATURATION": "2708-6",

    "MOBILITY": "83186-7",

    "MORSE_FALL_TOTAL": "59460-6",
    "MORSE_FALL_LEVEL": "59461-4",
    "MORSE_GAIT": "59458-0",

    # Pain
    "PAIN_SEVERITY": "72514-3",
}


# ============================================================
# Example clinical terminology
#
# These are synthetic/demo mappings for the generator.
# Validate terminology against your organization's required
# terminology version before using these in production.
# ============================================================

CONDITIONS = [
    {
        "code": "73211009",
        "display": "Diabetes mellitus",
        "system": SNOMED_SYSTEM,
    },
    {
        "code": "429271000124103",
        "display": "Pressure ulcer",
        "system": SNOMED_SYSTEM,
    },
    {
        "code": "38341003",
        "display": "Hypertensive disorder",
        "system": SNOMED_SYSTEM,
    },
]


ALLERGIES = [
    {
        "code": "7986",
        "display": "Penicillin",
        "system": "http://snomed.info/sct",
    },
    {
        "code": "227493005",
        "display": "Shellfish",
        "system": SNOMED_SYSTEM,
    },
]


MEDICATIONS = [
    {
        "code": "A10BA02",
        "display": "Metformin",
        "system": ATC_SYSTEM,
    },
    {
        "code": "C09AA05",
        "display": "Ramipril",
        "system": ATC_SYSTEM,
    },
]


# ============================================================
# Patient names
# ============================================================

MALE_FIRST_NAMES = [
    "Max",
    "Peter",
    "Thomas",
    "Michael",
    "Daniel",
    "Stefan",
    "Alexander",
    "Markus",
    "Andreas",
    "Christian",
]

FEMALE_FIRST_NAMES = [
    "Anna",
    "Sophie",
    "Laura",
    "Julia",
    "Marie",
    "Clara",
    "Sarah",
    "Lisa",
    "Katharina",
    "Nina",
]

LAST_NAMES = [
    "Mustermann",
    "Schmidt",
    "Müller",
    "Weber",
    "Fischer",
    "Wagner",
    "Becker",
    "Schulz",
    "Hoffmann",
    "Koch",
    "Richter",
    "Bauer",
    "Klein",
    "Wolf",
    "Schröder",
]

STREETS = [
    "Hauptstraße",
    "Bahnhofstraße",
    "Dorfstraße",
    "Gartenstraße",
    "Schulstraße",
    "Bergstraße",
    "Lindenstraße",
]

CITIES = [
    ("Berlin", "10115"),
    ("Hamburg", "20095"),
    ("München", "80331"),
    ("Köln", "50667"),
    ("Frankfurt", "60311"),
    ("Leipzig", "04109"),
    ("Kiel", "24103"),
]


# ============================================================
# Data classes
# ============================================================

@dataclass
class ClinicalProfile:

    first_name: str
    last_name: str
    gender: str
    birth_date: str

    street: str
    house_number: int
    postal_code: str
    city: str

    systolic: int
    diastolic: int
    heart_rate: int
    temperature: float
    respiratory_rate: int
    oxygen_saturation: int

    pain_score: int

    mobility_score: int

    morse_score: int
    morse_level: str
    gait_score: int
    gait_display: str

    risk_labels: dict[str, int] = field(
        default_factory=dict
    )

    conditions: list[dict[str, Any]] = field(
        default_factory=list
    )

    allergies: list[dict[str, Any]] = field(
        default_factory=list
    )

    medications: list[dict[str, Any]] = field(
        default_factory=list
    )

    has_wound_procedure: bool = False


# ============================================================
# Utility
# ============================================================

def make_uuid() -> str:
    return str(uuid.uuid4())


def seed_identifier(prefix: str, sequence: int) -> str:
    if sequence < 1:
        raise ValueError("Seed identifier sequence must be positive.")
    return f"{prefix}-SEED-{sequence:06d}"


def random_birth_date(
    rng: random.Random,
) -> str:

    today = date.today()

    age = rng.randint(18, 95)

    year = today.year - age

    month = rng.randint(1, 12)

    if month == 2:
        day = rng.randint(1, 28)

    elif month in {4, 6, 9, 11}:
        day = rng.randint(1, 30)

    else:
        day = rng.randint(1, 28)

    return date(
        year,
        month,
        day,
    ).isoformat()


def effective_datetime(
    rng: random.Random,
) -> str:

    now = datetime.now(
        timezone.utc
    )

    minutes_ago = rng.randint(
        0,
        24 * 60,
    )

    timestamp = (
        now
        - timedelta(minutes=minutes_ago)
    )

    return timestamp.isoformat()


# ============================================================
# FHIR helpers
# ============================================================

def make_coding(
    code: str,
    display: str,
    system: str,
) -> dict[str, str]:

    return {
        "system": system,
        "code": code,
        "display": display,
    }


def make_quantity(
    value: int | float,
    unit: str,
    code: str | None = None,
) -> dict[str, Any]:

    return {
        "value": value,
        "unit": unit,
        "system": UCUM_SYSTEM,
        "code": code or unit,
    }


# ============================================================
# Patient generator
# ============================================================

class PatientGenerator:

    def __init__(
        self,
        rng: random.Random,
    ):
        self.rng = rng

    def generate(
        self,
    ) -> ClinicalProfile:

        gender = self.rng.choice(
            ["male", "female"]
        )

        if gender == "male":
            first_name = self.rng.choice(
                MALE_FIRST_NAMES
            )
        else:
            first_name = self.rng.choice(
                FEMALE_FIRST_NAMES
            )

        last_name = self.rng.choice(
            LAST_NAMES
        )

        city, postal_code = self.rng.choice(
            CITIES
        )

        street = self.rng.choice(
            STREETS
        )

        # ----------------------------------------------------
        # Vital signs
        # ----------------------------------------------------

        systolic = int(
            self.rng.gauss(125, 15)
        )

        diastolic = int(
            self.rng.gauss(78, 10)
        )

        systolic = max(
            90,
            min(180, systolic),
        )

        diastolic = max(
            55,
            min(110, diastolic),
        )

        heart_rate = int(
            self.rng.gauss(74, 10)
        )

        heart_rate = max(
            45,
            min(130, heart_rate),
        )

        temperature = round(
            self.rng.gauss(36.7, 0.35),
            1,
        )

        temperature = max(
            35.5,
            min(39.5, temperature),
        )

        respiratory_rate = int(
            self.rng.gauss(16, 3)
        )

        respiratory_rate = max(
            10,
            min(30, respiratory_rate),
        )

        oxygen_saturation = int(
            self.rng.gauss(97, 2)
        )

        oxygen_saturation = max(
            88,
            min(100, oxygen_saturation),
        )

        pain_score = self.rng.randint(
            0,
            7,
        )

        # ----------------------------------------------------
        # Mobility
        # ----------------------------------------------------

        mobility_score = self.rng.choices(
            [0, 1, 2],
            weights=[
                60,
                30,
                10,
            ],
        )[0]

        # ----------------------------------------------------
        # Morse Fall Scale
        # ----------------------------------------------------

        morse_score = self.rng.choices(
            [
                self.rng.randint(0, 24),
                self.rng.randint(25, 45),
                self.rng.randint(50, 85),
            ],
            weights=[
                55,
                30,
                15,
            ],
        )[0]

        if morse_score <= 24:
            morse_level = "Low Risk"

        elif morse_score <= 45:
            morse_level = "Moderate Risk"

        else:
            morse_level = "High Risk"

        gait_score = self.rng.choices(
            [0, 10, 20],
            weights=[
                60,
                25,
                15,
            ],
        )[0]

        gait_display = {
            0: "Normal/bedrest/immobile",
            10: "Weak",
            20: "Impaired",
        }[gait_score]

        risk_labels = {
            "fall": int(morse_score >= 45),
            "pressure_ulcer": int(mobility_score >= 2),
            "pain_escalation": int(pain_score >= 5),
            "clinical_deterioration": int(
                temperature >= 38.0
                or heart_rate >= 100
                or respiratory_rate >= 24
                or oxygen_saturation <= 92
            ),
        }

        # ----------------------------------------------------
        # Conditions
        # ----------------------------------------------------

        conditions = []

        if self.rng.random() < 0.20:

            conditions.append(
                self.rng.choice(
                    CONDITIONS
                )
            )

        if self.rng.random() < 0.10:

            condition = self.rng.choice(
                CONDITIONS
            )

            if condition not in conditions:
                conditions.append(
                    condition
                )

        # ----------------------------------------------------
        # Allergies
        # ----------------------------------------------------

        allergies = []

        if self.rng.random() < 0.15:

            allergies.append(
                self.rng.choice(
                    ALLERGIES
                )
            )

        # ----------------------------------------------------
        # Medications
        # ----------------------------------------------------

        medications = []

        if self.rng.random() < 0.20:

            medications.append(
                self.rng.choice(
                    MEDICATIONS
                )
            )

        # ----------------------------------------------------
        # Wound procedure
        # ----------------------------------------------------

        has_wound_procedure = any(
            c["display"] == "Pressure ulcer"
            for c in conditions
        )

        return ClinicalProfile(
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            birth_date=random_birth_date(
                self.rng
            ),
            street=street,
            house_number=self.rng.randint(
                1,
                150,
            ),
            postal_code=postal_code,
            city=city,
            systolic=systolic,
            diastolic=diastolic,
            heart_rate=heart_rate,
            temperature=temperature,
            respiratory_rate=respiratory_rate,
            oxygen_saturation=oxygen_saturation,
            pain_score=pain_score,
            mobility_score=mobility_score,
            morse_score=morse_score,
            morse_level=morse_level,
            gait_score=gait_score,
            gait_display=gait_display,
            risk_labels=risk_labels,
            conditions=conditions,
            allergies=allergies,
            medications=medications,
            has_wound_procedure=has_wound_procedure,
        )


# ============================================================
# Patient resource
# ============================================================

class PatientResourceGenerator:

    @staticmethod
    def generate(
        profile: ClinicalProfile,
        patient_number: str,
    ) -> dict[str, Any]:

        return {
            "resourceType": "Patient",

            "identifier": [
                {
                    "use": "official",
                    "system": PATIENT_IDENTIFIER_SYSTEM,
                    "value": patient_number,
                }
            ],

            "name": [
                {
                    "use": "official",
                    "family": profile.last_name,
                    "given": [
                        profile.first_name
                    ],
                }
            ],

            "gender": profile.gender,

            "birthDate": profile.birth_date,

            "address": [
                {
                    "use": "home",
                    "line": [
                        f"{profile.street} "
                        f"{profile.house_number}"
                    ],
                    "postalCode": profile.postal_code,
                    "city": profile.city,
                    "country": "DE",
                }
            ],
        }


# ============================================================
# Encounter resource
# ============================================================

class EncounterResourceGenerator:

    @staticmethod
    def generate(
        patient_ref: str,
        encounter_number: str,
        admitted_at: str,
    ) -> dict[str, Any]:

        return {
            "resourceType": "Encounter",
            "identifier": [
                {
                    "use": "official",
                    "system": ENCOUNTER_IDENTIFIER_SYSTEM,
                    "value": encounter_number,
                }
            ],
            "status": "in-progress",
            "class": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": "IMP",
                "display": "inpatient encounter",
            },
            "subject": {
                "reference": patient_ref,
            },
            "period": {
                "start": admitted_at,
            },
        }


# ============================================================
# Observation generator
# ============================================================

class ObservationGenerator:

    @staticmethod
    def quantity_observation(
        code: str,
        display: str,
        value: int | float,
        unit: str,
        patient_ref: str,
        effective: str,
    ) -> dict[str, Any]:

        return {
            "resourceType": "Observation",
            "status": "final",

            "code": {
                "coding": [
                    make_coding(
                        code,
                        display,
                        LOINC_SYSTEM,
                    )
                ]
            },

            "subject": {
                "reference": patient_ref,
            },

            "effectiveDateTime": effective,

            "valueQuantity": make_quantity(
                value,
                unit,
            ),
        }

    @staticmethod
    def codeable_observation(
        code: str,
        display: str,
        value_code: str,
        value_display: str,
        patient_ref: str,
        effective: str,
    ) -> dict[str, Any]:

        return {
            "resourceType": "Observation",
            "status": "final",

            "code": {
                "coding": [
                    make_coding(
                        code,
                        display,
                        LOINC_SYSTEM,
                    )
                ]
            },

            "subject": {
                "reference": patient_ref,
            },

            "effectiveDateTime": effective,

            "valueCodeableConcept": {
                "coding": [
                    make_coding(
                        value_code,
                        value_display,
                        LOINC_SYSTEM,
                    )
                ]
            },
        }

    @staticmethod
    def risk_label_observation(
        risk_type: str,
        value: int,
        patient_ref: str,
        effective: str,
    ) -> dict[str, Any]:

        return {
            "resourceType": "Observation",
            "status": "final",
            "code": {
                "coding": [
                    make_coding(
                        RISK_LABEL_CODES[risk_type],
                        f"Synthetic label: {risk_type}",
                        RISK_LABEL_SYSTEM,
                    )
                ]
            },
            "subject": {
                "reference": patient_ref,
            },
            "effectiveDateTime": effective,
            "valueCodeableConcept": {
                "coding": [
                    make_coding(
                        "positive" if value else "negative",
                        "Positive" if value else "Negative",
                        RISK_LABEL_SYSTEM,
                    )
                ]
            },
        }

    @classmethod
    def generate(
        cls,
        profile: ClinicalProfile,
        patient_ref: str,
        effective: str,
    ) -> list[dict[str, Any]]:

        observations = []

        # Heart rate
        observations.append(
            cls.quantity_observation(
                LOINC["HEART_RATE"],
                "Heart rate",
                profile.heart_rate,
                "/min",
                patient_ref,
                effective,
            )
        )

        # Blood pressure
        observations.append(
            {
                "resourceType": "Observation",
                "status": "final",

                "code": {
                    "coding": [
                        make_coding(
                            LOINC["BLOOD_PRESSURE"],
                            "Blood pressure panel",
                            LOINC_SYSTEM,
                        )
                    ]
                },

                "subject": {
                    "reference": patient_ref,
                },

                "effectiveDateTime": effective,

                "component": [
                    {
                        "code": {
                            "coding": [
                                make_coding(
                                    LOINC["SYSTOLIC_BP"],
                                    "Systolic blood pressure",
                                    LOINC_SYSTEM,
                                )
                            ]
                        },

                        "valueQuantity": make_quantity(
                            profile.systolic,
                            "mmHg",
                            "mm[Hg]",
                        ),
                    },
                    {
                        "code": {
                            "coding": [
                                make_coding(
                                    LOINC["DIASTOLIC_BP"],
                                    "Diastolic blood pressure",
                                    LOINC_SYSTEM,
                                )
                            ]
                        },

                        "valueQuantity": make_quantity(
                            profile.diastolic,
                            "mmHg",
                            "mm[Hg]",
                        ),
                    },
                ],
            }
        )

        # Temperature
        observations.append(
            cls.quantity_observation(
                LOINC["TEMPERATURE"],
                "Body temperature",
                profile.temperature,
                "Cel",
                patient_ref,
                effective,
            )
        )

        # Respiratory rate
        observations.append(
            cls.quantity_observation(
                LOINC["RESPIRATORY_RATE"],
                "Respiratory rate",
                profile.respiratory_rate,
                "/min",
                patient_ref,
                effective,
            )
        )

        # SpO2
        observations.append(
            cls.quantity_observation(
                LOINC["OXYGEN_SATURATION"],
                "Oxygen saturation",
                profile.oxygen_saturation,
                "%",
                patient_ref,
                effective,
            )
        )

        # Pain
        observations.append(
            cls.quantity_observation(
                LOINC["PAIN_SEVERITY"],
                "Pain severity",
                profile.pain_score,
                "{score}",
                patient_ref,
                effective,
            )
        )

        # Mobility
        mobility_display = {
            0: "Independent mobility",
            1: "Mobility with assistance/device",
            2: "Impaired mobility",
        }[profile.mobility_score]

        observations.append(
            cls.codeable_observation(
                LOINC["MOBILITY"],
                "Mobility",
                str(profile.mobility_score),
                mobility_display,
                patient_ref,
                effective,
            )
        )

        # Morse score
        observations.append(
            cls.quantity_observation(
                LOINC["MORSE_FALL_TOTAL"],
                "Fall risk total [Morse Fall Scale]",
                profile.morse_score,
                "{score}",
                patient_ref,
                effective,
            )
        )

        # Morse risk level
        risk_code = {
            "Low Risk": "LA13038-7",
            "Moderate Risk": "LA13039-5",
            "High Risk": "LA13040-3",
        }[profile.morse_level]

        observations.append(
            cls.codeable_observation(
                LOINC["MORSE_FALL_LEVEL"],
                "Fall risk level [Morse Fall Scale]",
                risk_code,
                profile.morse_level,
                patient_ref,
                effective,
            )
        )

        # Morse gait
        gait_code = {
            0: "LA13033-8",
            10: "LA13034-6",
            20: "LA13035-3",
        }[profile.gait_score]

        observations.append(
            cls.codeable_observation(
                LOINC["MORSE_GAIT"],
                "Gait [Morse Fall Scale]",
                gait_code,
                profile.gait_display,
                patient_ref,
                effective,
            )
        )

        for risk_type, value in profile.risk_labels.items():
            observations.append(
                cls.risk_label_observation(
                    risk_type,
                    value,
                    patient_ref,
                    effective,
                )
            )

        return observations


# ============================================================
# Condition generator
# ============================================================

class ConditionGenerator:

    @staticmethod
    def generate(
        condition: dict[str, Any],
        patient_ref: str,
        recorded: str,
    ) -> dict[str, Any]:

        return {
            "resourceType": "Condition",

            "clinicalStatus": {
                "coding": [
                    {
                        "system":
                            "http://terminology.hl7.org/"
                            "CodeSystem/condition-clinical",
                        "code": "active",
                        "display": "Active",
                    }
                ]
            },

            "verificationStatus": {
                "coding": [
                    {
                        "system":
                            "http://terminology.hl7.org/"
                            "CodeSystem/condition-ver-status",
                        "code": "confirmed",
                        "display": "Confirmed",
                    }
                ]
            },

            "code": {
                "coding": [
                    make_coding(
                        condition["code"],
                        condition["display"],
                        condition["system"],
                    )
                ],

                "text": condition["display"],
            },

            "subject": {
                "reference": patient_ref,
            },

            "recordedDate": recorded,
        }


# ============================================================
# Allergy generator
# ============================================================

class AllergyGenerator:

    @staticmethod
    def generate(
        allergy: dict[str, Any],
        patient_ref: str,
        recorded: str,
    ) -> dict[str, Any]:

        return {
            "resourceType": "AllergyIntolerance",

            "clinicalStatus": {
                "coding": [
                    {
                        "system":
                            "http://terminology.hl7.org/"
                            "CodeSystem/allergyintolerance-clinical",
                        "code": "active",
                        "display": "Active",
                    }
                ]
            },

            "verificationStatus": {
                "coding": [
                    {
                        "system":
                            "http://terminology.hl7.org/"
                            "CodeSystem/allergyintolerance-verification",
                        "code": "confirmed",
                        "display": "Confirmed",
                    }
                ]
            },

            "type": "allergy",

            "category": [
                "medication"
            ],

            "code": {
                "coding": [
                    make_coding(
                        allergy["code"],
                        allergy["display"],
                        allergy["system"],
                    )
                ],

                "text": allergy["display"],
            },

            "patient": {
                "reference": patient_ref,
            },

            "recordedDate": recorded,
        }


# ============================================================
# MedicationRequest generator
# ============================================================

class MedicationRequestGenerator:

    @staticmethod
    def generate(
        medication: dict[str, Any],
        patient_ref: str,
        authored_on: str,
    ) -> dict[str, Any]:

        return {
            "resourceType": "MedicationRequest",

            "status": "active",

            "intent": "order",

            "medicationCodeableConcept": {
                "coding": [
                    make_coding(
                        medication["code"],
                        medication["display"],
                        medication["system"],
                    )
                ],

                "text": medication["display"],
            },

            "subject": {
                "reference": patient_ref,
            },

            "authoredOn": authored_on,

            "dosageInstruction": [
                {
                    "text": (
                        "1 Tablette morgens "
                        "nach ärztlicher Anordnung"
                    ),

                    "timing": {
                        "repeat": {
                            "frequency": 1,
                            "period": 1,
                            "periodUnit": "d",
                        }
                    },

                    "route": {
                        "coding": [
                            {
                                "system":
                                    "http://snomed.info/sct",
                                "code":
                                    "26643006",
                                "display":
                                    "Oral route",
                            }
                        ]
                    },
                }
            ],
        }


# ============================================================
# Procedure generator
# ============================================================

class ProcedureGenerator:

    @staticmethod
    def generate(
        patient_ref: str,
        performed: str,
    ) -> dict[str, Any]:

        return {
            "resourceType": "Procedure",

            "status": "completed",

            "code": {
                "coding": [
                    {
                        "system":
                            SNOMED_SYSTEM,

                        # Demo terminology mapping.
                        "code":
                            "225358003",

                        "display":
                            "Wound care",
                    }
                ],

                "text": "Wound care",
            },

            "subject": {
                "reference": patient_ref,
            },

            "performedDateTime": performed,
        }


# ============================================================
# CarePlan generator
# ============================================================

class CarePlanGenerator:

    @staticmethod
    def generate(
        profile: ClinicalProfile,
        patient_ref: str,
        authored: str,
    ) -> dict[str, Any]:

        contained_goals = []

        goal_references = []

        activities = []

        def add_goal(goal_id: str, description: str) -> None:
            contained_goals.append(
                {
                    "resourceType": "Goal",
                    "id": goal_id,
                    "lifecycleStatus": "active",
                    "description": {"text": description},
                    "subject": {"reference": patient_ref},
                }
            )
            goal_references.append({"reference": f"#{goal_id}"})

        # ----------------------------------------------------
        # Generic nursing goals
        # ----------------------------------------------------

        add_goal(
            "goal-safety",
            "Maintain patient safety and prevent falls",
        )

        activities.append(
            {
                "detail": {
                    "status": "in-progress",
                    "description":
                        "Regular fall-risk assessment",
                }
            }
        )

        # ----------------------------------------------------
        # Mobility
        # ----------------------------------------------------

        if profile.mobility_score > 0:

            add_goal(
                "goal-mobility",
                "Improve and maintain mobility",
            )

            activities.append(
                {
                    "detail": {
                        "status": "in-progress",
                        "description":
                            "Mobilisation with "
                            "appropriate assistance",
                    }
                }
            )

        # ----------------------------------------------------
        # Diabetes
        # ----------------------------------------------------

        if any(
            c["display"] == "Diabetes mellitus"
            for c in profile.conditions
        ):

            add_goal(
                "goal-blood-glucose",
                "Maintain stable blood glucose",
            )

            activities.append(
                {
                    "detail": {
                        "status": "in-progress",
                        "description":
                            "Regular blood glucose "
                            "monitoring",
                    }
                }
            )

        # ----------------------------------------------------
        # Pressure ulcer
        # ----------------------------------------------------

        if any(
            c["display"] == "Pressure ulcer"
            for c in profile.conditions
        ):

            add_goal(
                "goal-wound-healing",
                "Support wound healing",
            )

            activities.append(
                {
                    "detail": {
                        "status": "in-progress",
                        "description":
                            "Regular wound assessment "
                            "and wound care",
                    }
                }
            )

        return {
            "resourceType": "CarePlan",

            "status": "active",

            "intent": "plan",

            "title": "Nursing care plan",

            "description":
                "Synthetic nursing care plan "
                "generated for testing.",

            "contained": contained_goals,

            "subject": {
                "reference": patient_ref,
            },

            "created": authored,

            "goal": goal_references,

            "activity": activities,
        }


# ============================================================
# Bundle generator
# ============================================================

class BundleGenerator:

    def __init__(
        self,
        rng: random.Random,
    ):
        self.rng = rng

        self.patient_generator = (
            PatientGenerator(rng)
        )

    def generate(
        self,
        sequence: int,
    ) -> tuple[
        ClinicalProfile,
        dict[str, Any],
    ]:

        profile = (
            self.patient_generator.generate()
        )

        patient_uuid = make_uuid()

        patient_ref = (
            f"urn:uuid:{patient_uuid}"
        )

        patient_number = seed_identifier(
            "PAT",
            sequence,
        )

        encounter_number = seed_identifier(
            "FALL",
            sequence,
        )

        effective = effective_datetime(
            self.rng
        )

        entries = []

        # ----------------------------------------------------
        # Patient
        # ----------------------------------------------------

        patient = (
            PatientResourceGenerator.generate(
                profile,
                patient_number,
            )
        )

        entries.append(
            {
                "fullUrl": patient_ref,

                "resource": patient,

                "request": {
                    "method": "POST",
                    "url": "Patient",
                },
            }
        )

        # ----------------------------------------------------
        # Active inpatient encounter
        # ----------------------------------------------------

        encounter = EncounterResourceGenerator.generate(
            patient_ref,
            encounter_number,
            effective,
        )

        entries.append(
            {
                "fullUrl": f"urn:uuid:{make_uuid()}",
                "resource": encounter,
                "request": {
                    "method": "POST",
                    "url": "Encounter",
                },
            }
        )

        # ----------------------------------------------------
        # Observations
        # ----------------------------------------------------

        observations = (
            ObservationGenerator.generate(
                profile,
                patient_ref,
                effective,
            )
        )

        for observation in observations:

            entries.append(
                {
                    "fullUrl":
                        f"urn:uuid:{make_uuid()}",

                    "resource": observation,

                    "request": {
                        "method": "POST",
                        "url": "Observation",
                    },
                }
            )

        # ----------------------------------------------------
        # Conditions
        # ----------------------------------------------------

        for condition in profile.conditions:

            resource = (
                ConditionGenerator.generate(
                    condition,
                    patient_ref,
                    effective,
                )
            )

            entries.append(
                {
                    "fullUrl":
                        f"urn:uuid:{make_uuid()}",

                    "resource": resource,

                    "request": {
                        "method": "POST",
                        "url": "Condition",
                    },
                }
            )

        # ----------------------------------------------------
        # Allergies
        # ----------------------------------------------------

        for allergy in profile.allergies:

            resource = (
                AllergyGenerator.generate(
                    allergy,
                    patient_ref,
                    effective,
                )
            )

            entries.append(
                {
                    "fullUrl":
                        f"urn:uuid:{make_uuid()}",

                    "resource": resource,

                    "request": {
                        "method":
                            "POST",

                        "url":
                            "AllergyIntolerance",
                    },
                }
            )

        # ----------------------------------------------------
        # MedicationRequest
        # ----------------------------------------------------

        for medication in profile.medications:

            resource = (
                MedicationRequestGenerator.generate(
                    medication,
                    patient_ref,
                    effective,
                )
            )

            entries.append(
                {
                    "fullUrl":
                        f"urn:uuid:{make_uuid()}",

                    "resource": resource,

                    "request": {
                        "method":
                            "POST",

                        "url":
                            "MedicationRequest",
                    },
                }
            )

        # ----------------------------------------------------
        # Procedure
        # ----------------------------------------------------

        if profile.has_wound_procedure:

            procedure = (
                ProcedureGenerator.generate(
                    patient_ref,
                    effective,
                )
            )

            entries.append(
                {
                    "fullUrl":
                        f"urn:uuid:{make_uuid()}",

                    "resource": procedure,

                    "request": {
                        "method": "POST",
                        "url": "Procedure",
                    },
                }
            )

        # ----------------------------------------------------
        # CarePlan
        # ----------------------------------------------------

        care_plan = (
            CarePlanGenerator.generate(
                profile,
                patient_ref,
                effective,
            )
        )

        entries.append(
            {
                "fullUrl":
                    f"urn:uuid:{make_uuid()}",

                "resource": care_plan,

                "request": {
                    "method": "POST",
                    "url": "CarePlan",
                },
            }
        )

        bundle = {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": entries,
        }

        return profile, bundle


# ============================================================
# FHIR Client
# ============================================================

class FHIRClient:

    def __init__(
        self,
        base_url: str,
        timeout: float,
        retries: int,
    ):

        self.base_url = base_url.rstrip("/")

        self.timeout = timeout

        self.retries = retries

        self.session = requests.Session()

        self.session.headers.update(
            {
                "Accept":
                    "application/fhir+json",

                "Content-Type":
                    "application/fhir+json",
            }
        )

    def request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> requests.Response:

        url = (
            f"{self.base_url}/"
            f"{endpoint.lstrip('/')}"
        )

        last_exception = None

        for attempt in range(
            1,
            self.retries + 1,
        ):

            try:

                response = self.session.request(
                    method,
                    url,
                    timeout=self.timeout,
                    **kwargs,
                )

                if response.status_code >= 500:

                    if attempt < self.retries:

                        logger.warning(
                            "FHIR HTTP %s. "
                            "Retry %s/%s",
                            response.status_code,
                            attempt,
                            self.retries,
                        )

                        time.sleep(
                            2 ** (attempt - 1)
                        )

                        continue

                return response

            except requests.RequestException as exc:

                last_exception = exc

                if attempt < self.retries:

                    time.sleep(
                        2 ** (attempt - 1)
                    )

        raise RuntimeError(
            "FHIR request failed"
        ) from last_exception

    def health_check(self) -> None:

        response = self.request(
            "GET",
            "metadata",
        )

        if not response.ok:

            raise RuntimeError(
                "HAPI FHIR server unavailable:\n"
                f"Status: {response.status_code}\n"
                f"{response.text[:2000]}"
            )

        logger.info(
            "HAPI FHIR server is reachable."
        )

    def transaction(
        self,
        bundle: dict[str, Any],
    ) -> dict[str, Any]:

        response = self.request(
            "POST",
            "",
            json=bundle,
        )

        if not response.ok:

            logger.error(
                "FHIR transaction failed: %s",
                response.status_code,
            )

            logger.error(
                response.text[:5000]
            )

            response.raise_for_status()

        return response.json()


# ============================================================
# Seed service
# ============================================================

class SeedService:

    def __init__(
        self,
        client: FHIRClient,
        seed: int | None,
    ):

        self.client = client

        self.rng = random.Random(
            seed
        )

        self.bundle_generator = (
            BundleGenerator(self.rng)
        )

    def run(
        self,
        number_of_patients: int,
        batch_size: int,
    ) -> None:

        successful = 0
        failed = 0

        for start in range(
            0,
            number_of_patients,
            batch_size,
        ):

            end = min(
                start + batch_size,
                number_of_patients,
            )

            logger.info(
                "Processing patients %s-%s",
                start + 1,
                end,
            )

            for index in range(
                start,
                end,
            ):

                patient_number = index + 1

                try:

                    profile, bundle = (
                        self.bundle_generator.generate(
                            patient_number
                        )
                    )

                    response = (
                        self.client.transaction(
                            bundle
                        )
                    )

                    successful += 1

                    logger.info(
                        "[%s/%s] Created %s %s "
                        "| conditions=%s "
                        "| allergies=%s "
                        "| medications=%s "
                        "| patient_number=%s "
                        "| encounter_number=%s",
                        patient_number,
                        number_of_patients,
                        profile.first_name,
                        profile.last_name,
                        len(profile.conditions),
                        len(profile.allergies),
                        len(profile.medications),
                        seed_identifier("PAT", patient_number),
                        seed_identifier("FALL", patient_number),
                    )

                except Exception as exc:

                    failed += 1

                    logger.error(
                        "[%s/%s] FAILED: %s",
                        patient_number,
                        number_of_patients,
                        exc,
                    )

        logger.info(
            "=========================================="
        )

        logger.info(
            "FHIR seed finished"
        )

        logger.info(
            "Successful: %s",
            successful,
        )

        logger.info(
            "Failed: %s",
            failed,
        )

        logger.info(
            "=========================================="
        )

        if failed:
            raise RuntimeError(
                f"{failed} patient transactions failed."
            )


# ============================================================
# CLI
# ============================================================

def parse_args():

    parser = argparse.ArgumentParser(
        description=(
            "Generate synthetic clinical "
            "FHIR data for HAPI FHIR."
        )
    )

    parser.add_argument(
        "--patients",
        type=int,
        default=100,
        help="Number of patients.",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=FHIR_BATCH_SIZE,
        help="Patients per processing batch.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Reproducible random seed.",
    )

    parser.add_argument(
        "--url",
        type=str,
        default=FHIR_SERVER_URL,
        help="FHIR server base URL.",
    )

    return parser.parse_args()


# ============================================================
# Main
# ============================================================

def main() -> int:

    args = parse_args()

    if not 1 <= args.patients <= 1000:

        logger.error(
            "--patients must be between 1 and 1000."
        )

        return 2

    if args.batch_size < 1:

        logger.error(
            "--batch-size must be >= 1."
        )

        return 2

    client = FHIRClient(
        base_url=args.url,
        timeout=FHIR_TIMEOUT,
        retries=FHIR_RETRIES,
    )

    try:

        client.health_check()

        logger.info(
            "FHIR URL: %s",
            args.url,
        )

        logger.info(
            "Patients: %s",
            args.patients,
        )

        logger.info(
            "Batch size: %s",
            args.batch_size,
        )

        if args.seed is not None:

            logger.info(
                "Random seed: %s",
                args.seed,
            )

        service = SeedService(
            client=client,
            seed=args.seed,
        )

        service.run(
            number_of_patients=args.patients,
            batch_size=args.batch_size,
        )

        return 0

    except KeyboardInterrupt:

        logger.warning(
            "Seed interrupted."
        )

        return 130

    except Exception as exc:

        logger.exception(
            "Seed failed: %s",
            exc,
        )

        return 1


if __name__ == "__main__":
    sys.exit(main())
