from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time
import uuid
from dataclasses import dataclass
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

FHIR_TIMEOUT = float(os.getenv("FHIR_TIMEOUT", "30"))
FHIR_BATCH_SIZE = int(os.getenv("FHIR_BATCH_SIZE", "10"))
FHIR_RETRIES = int(os.getenv("FHIR_RETRIES", "3"))


# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("fhir-seed")


# ============================================================
# FHIR constants
# ============================================================

LOINC_SYSTEM = "http://loinc.org"
UCUM_SYSTEM = "http://unitsofmeasure.org"


LOINC = {
    # Vital signs
    "HEART_RATE": "8867-4",
    "SYSTOLIC_BP": "8480-6",
    "DIASTOLIC_BP": "8462-4",
    "BLOOD_PRESSURE_PANEL": "85354-9",
    "TEMPERATURE": "8310-5",
    "RESPIRATORY_RATE": "9279-1",
    "OXYGEN_SATURATION": "2708-6",

    # Mobility / fall risk
    "MOBILITY": "83186-7",
    "MORSE_FALL_TOTAL": "59460-6",
    "MORSE_FALL_LEVEL": "59461-4",
    "MORSE_GAIT": "59458-0",
}


# ============================================================
# Patient names
# ============================================================

FIRST_NAMES_MALE = [
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

FIRST_NAMES_FEMALE = [
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


# ============================================================
# Dataclasses
# ============================================================

@dataclass
class PatientProfile:
    first_name: str
    last_name: str
    gender: str
    birth_date: str

    systolic: int
    diastolic: int
    heart_rate: int
    temperature: float
    respiratory_rate: int
    oxygen_saturation: int

    mobility_score: int

    morse_fall_score: int
    morse_fall_level: str
    gait_score: int
    gait_display: str


# ============================================================
# FHIR client
# ============================================================

class FHIRClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 30,
        retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

        self.session = requests.Session()

        self.session.headers.update(
            {
                "Accept": "application/fhir+json",
                "Content-Type": "application/fhir+json",
            }
        )

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> requests.Response:

        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        last_exception: Exception | None = None

        for attempt in range(1, self.retries + 1):

            try:
                response = self.session.request(
                    method,
                    url,
                    timeout=self.timeout,
                    **kwargs,
                )

                # Retry only transient server errors.
                if response.status_code >= 500:

                    logger.warning(
                        "FHIR server returned %s. Attempt %s/%s",
                        response.status_code,
                        attempt,
                        self.retries,
                    )

                    if attempt < self.retries:
                        time.sleep(2 ** (attempt - 1))
                        continue

                return response

            except requests.RequestException as exc:

                last_exception = exc

                logger.warning(
                    "FHIR request failed: %s. Attempt %s/%s",
                    exc,
                    attempt,
                    self.retries,
                )

                if attempt < self.retries:
                    time.sleep(2 ** (attempt - 1))

        raise RuntimeError(
            f"FHIR request failed after {self.retries} attempts"
        ) from last_exception

    def health_check(self) -> None:

        response = self._request(
            "GET",
            "metadata",
        )

        if not response.ok:
            raise RuntimeError(
                "HAPI FHIR server is not reachable.\n"
                f"URL: {self.base_url}\n"
                f"Status: {response.status_code}\n"
                f"Response: {response.text[:1000]}"
            )

        logger.info(
            "HAPI FHIR server reachable: %s",
            self.base_url,
        )

    def transaction(
        self,
        bundle: dict[str, Any],
    ) -> dict[str, Any]:

        response = self._request(
            "POST",
            "",
            json=bundle,
        )

        if not response.ok:

            logger.error(
                "FHIR transaction failed: HTTP %s",
                response.status_code,
            )

            logger.error(
                "FHIR response: %s",
                response.text[:3000],
            )

            response.raise_for_status()

        return response.json()


# ============================================================
# Utility functions
# ============================================================

def make_uuid() -> str:
    return str(uuid.uuid4())


def random_birth_date(
    rng: random.Random,
    minimum_age: int = 18,
    maximum_age: int = 95,
) -> str:

    today = date.today()

    age = rng.randint(
        minimum_age,
        maximum_age,
    )

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

    now = datetime.now(timezone.utc)

    minutes_ago = rng.randint(
        0,
        24 * 60,
    )

    timestamp = now - timedelta(
        minutes=minutes_ago
    )

    return timestamp.isoformat()


# ============================================================
# Clinical data generation
# ============================================================

def generate_blood_pressure(
    rng: random.Random,
) -> tuple[int, int]:

    systolic = int(
        rng.gauss(125, 15)
    )

    diastolic = int(
        rng.gauss(78, 10)
    )

    systolic = max(90, min(180, systolic))
    diastolic = max(55, min(110, diastolic))

    return systolic, diastolic


def generate_profile(
    rng: random.Random,
) -> PatientProfile:

    gender = rng.choice(
        ["male", "female"]
    )

    if gender == "male":
        first_name = rng.choice(
            FIRST_NAMES_MALE
        )
    else:
        first_name = rng.choice(
            FIRST_NAMES_FEMALE
        )

    last_name = rng.choice(
        LAST_NAMES
    )

    birth_date = random_birth_date(
        rng
    )

    systolic, diastolic = (
        generate_blood_pressure(rng)
    )

    heart_rate = int(
        rng.gauss(74, 10)
    )

    heart_rate = max(
        45,
        min(130, heart_rate)
    )

    temperature = round(
        rng.gauss(36.7, 0.35),
        1,
    )

    temperature = max(
        35.5,
        min(39.5, temperature)
    )

    respiratory_rate = int(
        rng.gauss(16, 3)
    )

    respiratory_rate = max(
        10,
        min(30, respiratory_rate)
    )

    oxygen_saturation = int(
        rng.gauss(97, 2)
    )

    oxygen_saturation = max(
        88,
        min(100, oxygen_saturation)
    )

    # --------------------------------------------------------
    # Mobility
    #
    # Simple demo score:
    #
    # 0 = independent
    # 1 = needs assistance/device
    # 2 = impaired mobility
    # --------------------------------------------------------

    mobility_score = rng.choices(
        [0, 1, 2],
        weights=[60, 30, 10],
    )[0]

    # --------------------------------------------------------
    # Morse Fall Scale
    #
    # We generate a score from 0-125 but constrain it
    # to realistic/common ranges for this demo.
    # --------------------------------------------------------

    fall_score = rng.choices(
        [
            rng.randint(0, 24),
            rng.randint(25, 45),
            rng.randint(50, 85),
        ],
        weights=[55, 30, 15],
    )[0]

    if fall_score <= 24:
        fall_level = "Low Risk"
    elif fall_score <= 45:
        fall_level = "Moderate Risk"
    else:
        fall_level = "High Risk"

    # Morse gait categories:
    #
    # 0 = Normal/bedrest/immobile
    # 10 = Weak
    # 20 = Impaired
    gait_score = rng.choices(
        [0, 10, 20],
        weights=[60, 25, 15],
    )[0]

    gait_display = {
        0: "Normal/bedrest/immobile",
        10: "Weak",
        20: "Impaired",
    }[gait_score]

    return PatientProfile(
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        birth_date=birth_date,
        systolic=systolic,
        diastolic=diastolic,
        heart_rate=heart_rate,
        temperature=temperature,
        respiratory_rate=respiratory_rate,
        oxygen_saturation=oxygen_saturation,
        mobility_score=mobility_score,
        morse_fall_score=fall_score,
        morse_fall_level=fall_level,
        gait_score=gait_score,
        gait_display=gait_display,
    )


# ============================================================
# FHIR resource builders
# ============================================================

def coding(
    code: str,
    display: str,
    system: str = LOINC_SYSTEM,
) -> dict[str, str]:

    return {
        "system": system,
        "code": code,
        "display": display,
    }


def quantity(
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


def observation_quantity(
    *,
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
                coding(code, display)
            ]
        },

        "subject": {
            "reference": patient_ref,
        },

        "effectiveDateTime": effective,

        "valueQuantity": quantity(
            value=value,
            unit=unit,
        ),
    }


def observation_codeable(
    *,
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
                coding(code, display)
            ]
        },

        "subject": {
            "reference": patient_ref,
        },

        "effectiveDateTime": effective,

        "valueCodeableConcept": {
            "coding": [
                {
                    "system": LOINC_SYSTEM,
                    "code": value_code,
                    "display": value_display,
                }
            ]
        },
    }


def create_patient(
    profile: PatientProfile,
) -> dict[str, Any]:

    return {
        "resourceType": "Patient",

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
    }


# ============================================================
# Observation generation
# ============================================================

def create_observations(
    profile: PatientProfile,
    patient_ref: str,
    effective: str,
) -> list[dict[str, Any]]:

    observations: list[dict[str, Any]] = []

    # --------------------------------------------------------
    # Heart rate
    # LOINC 8867-4
    # --------------------------------------------------------

    observations.append(
        observation_quantity(
            code=LOINC["HEART_RATE"],
            display="Heart rate",
            value=profile.heart_rate,
            unit="/min",
            patient_ref=patient_ref,
            effective=effective,
        )
    )

    # --------------------------------------------------------
    # Blood pressure
    # LOINC 85354-9
    # --------------------------------------------------------

    blood_pressure = {
        "resourceType": "Observation",
        "status": "final",

        "code": {
            "coding": [
                coding(
                    LOINC["BLOOD_PRESSURE_PANEL"],
                    "Blood pressure panel",
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
                        coding(
                            LOINC["SYSTOLIC_BP"],
                            "Systolic blood pressure",
                        )
                    ]
                },

                "valueQuantity": quantity(
                    profile.systolic,
                    "mmHg",
                    "mm[Hg]",
                ),
            },

            {
                "code": {
                    "coding": [
                        coding(
                            LOINC["DIASTOLIC_BP"],
                            "Diastolic blood pressure",
                        )
                    ]
                },

                "valueQuantity": quantity(
                    profile.diastolic,
                    "mmHg",
                    "mm[Hg]",
                ),
            },
        ],
    }

    observations.append(
        blood_pressure
    )

    # --------------------------------------------------------
    # Temperature
    # LOINC 8310-5
    # --------------------------------------------------------

    observations.append(
        observation_quantity(
            code=LOINC["TEMPERATURE"],
            display="Body temperature",
            value=profile.temperature,
            unit="Cel",
            patient_ref=patient_ref,
            effective=effective,
        )
    )

    # --------------------------------------------------------
    # Respiratory rate
    # LOINC 9279-1
    # --------------------------------------------------------

    observations.append(
        observation_quantity(
            code=LOINC["RESPIRATORY_RATE"],
            display="Respiratory rate",
            value=profile.respiratory_rate,
            unit="/min",
            patient_ref=patient_ref,
            effective=effective,
        )
    )

    # --------------------------------------------------------
    # Oxygen saturation
    # LOINC 2708-6
    # --------------------------------------------------------

    observations.append(
        observation_quantity(
            code=LOINC["OXYGEN_SATURATION"],
            display="Oxygen saturation",
            value=profile.oxygen_saturation,
            unit="%",
            patient_ref=patient_ref,
            effective=effective,
        )
    )

    # --------------------------------------------------------
    # Mobility
    #
    # Demo score represented as a Quantity.
    #
    # LOINC 83186-7 is "Mobility" and has ordinal answer
    # concepts in the Schmid fall risk assessment.
    # --------------------------------------------------------

    mobility_display = {
        0: "Independent mobility",
        1: "Mobility with assistance/device",
        2: "Impaired mobility",
    }[profile.mobility_score]

    observations.append(
        observation_codeable(
            code=LOINC["MOBILITY"],
            display="Mobility",
            value_code=str(
                profile.mobility_score
            ),
            value_display=mobility_display,
            patient_ref=patient_ref,
            effective=effective,
        )
    )

    # --------------------------------------------------------
    # Morse Fall Score
    # LOINC 59460-6
    # --------------------------------------------------------

    observations.append(
        observation_quantity(
            code=LOINC["MORSE_FALL_TOTAL"],
            display="Fall risk total [Morse Fall Scale]",
            value=profile.morse_fall_score,
            unit="{score}",
            patient_ref=patient_ref,
            effective=effective,
        )
    )

    # --------------------------------------------------------
    # Morse Fall Risk Level
    # LOINC 59461-4
    # --------------------------------------------------------

    observations.append(
        observation_codeable(
            code=LOINC["MORSE_FALL_LEVEL"],
            display="Fall risk level [Morse Fall Scale]",
            value_code={
                "Low Risk": "LA13038-7",
                "Moderate Risk": "LA13039-5",
                "High Risk": "LA13040-3",
            }[profile.morse_fall_level],
            value_display=profile.morse_fall_level,
            patient_ref=patient_ref,
            effective=effective,
        )
    )

    # --------------------------------------------------------
    # Gait
    # LOINC 59458-0
    # --------------------------------------------------------

    observations.append(
        observation_codeable(
            code=LOINC["MORSE_GAIT"],
            display="Gait [Morse Fall Scale]",
            value_code={
                0: "LA13033-8",
                10: "LA13034-6",
                20: "LA13035-3",
            }[profile.gait_score],
            value_display=profile.gait_display,
            patient_ref=patient_ref,
            effective=effective,
        )
    )

    return observations


# ============================================================
# Transaction Bundle
# ============================================================

def create_transaction_bundle(
    profile: PatientProfile,
    rng: random.Random,
) -> dict[str, Any]:

    patient_uuid = make_uuid()

    patient_full_url = (
        f"urn:uuid:{patient_uuid}"
    )

    patient_ref = patient_full_url

    patient = create_patient(
        profile
    )

    effective = effective_datetime(
        rng
    )

    observations = create_observations(
        profile=profile,
        patient_ref=patient_ref,
        effective=effective,
    )

    entries: list[dict[str, Any]] = []

    # --------------------------------------------------------
    # Patient
    # --------------------------------------------------------

    entries.append(
        {
            "fullUrl": patient_full_url,

            "resource": patient,

            "request": {
                "method": "POST",
                "url": "Patient",
            },
        }
    )

    # --------------------------------------------------------
    # Observations
    # --------------------------------------------------------

    for observation in observations:

        entries.append(
            {
                "fullUrl": (
                    f"urn:uuid:{make_uuid()}"
                ),

                "resource": observation,

                "request": {
                    "method": "POST",
                    "url": "Observation",
                },
            }
        )

    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": entries,
    }


# ============================================================
# Seed generation
# ============================================================

def seed_patients(
    client: FHIRClient,
    number_of_patients: int,
    batch_size: int,
    seed: int | None,
) -> None:

    if not 1 <= number_of_patients <= 1000:
        raise ValueError(
            "number_of_patients must be between 1 and 1000"
        )

    if batch_size < 1:
        raise ValueError(
            "batch_size must be >= 1"
        )

    rng = random.Random(seed)

    logger.info(
        "Starting FHIR seed"
    )

    logger.info(
        "FHIR server: %s",
        client.base_url,
    )

    logger.info(
        "Patients: %s",
        number_of_patients,
    )

    logger.info(
        "Batch size: %s",
        batch_size,
    )

    if seed is not None:
        logger.info(
            "Random seed: %s",
            seed,
        )

    successful = 0
    failed = 0

    for batch_start in range(
        0,
        number_of_patients,
        batch_size,
    ):

        batch_end = min(
            batch_start + batch_size,
            number_of_patients,
        )

        logger.info(
            "Processing patients %s-%s",
            batch_start + 1,
            batch_end,
        )

        for patient_number in range(
            batch_start + 1,
            batch_end + 1,
        ):

            profile = generate_profile(
                rng
            )

            bundle = create_transaction_bundle(
                profile,
                rng,
            )

            try:

                response = client.transaction(
                    bundle
                )

                successful += 1

                logger.info(
                    "[%s/%s] Created %s %s",
                    patient_number,
                    number_of_patients,
                    profile.first_name,
                    profile.last_name,
                )

                if response.get(
                    "resourceType"
                ) != "Bundle":

                    logger.warning(
                        "Unexpected FHIR response"
                    )

            except Exception as exc:

                failed += 1

                logger.exception(
                    "[%s/%s] Failed to create patient: %s",
                    patient_number,
                    number_of_patients,
                    exc,
                )

        logger.info(
            "Progress: %s successful / %s failed",
            successful,
            failed,
        )

    logger.info(
        "================================================"
    )

    logger.info(
        "Seed finished"
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
        "================================================"
    )

    if failed > 0:
        raise RuntimeError(
            f"{failed} patient transactions failed"
        )


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Generate synthetic patients and "
            "FHIR Observations for HAPI FHIR."
        )
    )

    parser.add_argument(
        "--patients",
        type=int,
        default=100,
        help="Number of patients to create.",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=FHIR_BATCH_SIZE,
        help="Number of patients processed per batch.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=(
            "Random seed for reproducible test data."
        ),
    )

    parser.add_argument(
        "--url",
        type=str,
        default=FHIR_SERVER_URL,
        help="HAPI FHIR base URL.",
    )

    return parser.parse_args()


# ============================================================
# Main
# ============================================================

def main() -> int:

    args = parse_args()

    client = FHIRClient(
        base_url=args.url,
        timeout=FHIR_TIMEOUT,
        retries=FHIR_RETRIES,
    )

    try:

        client.health_check()

        seed_patients(
            client=client,
            number_of_patients=args.patients,
            batch_size=args.batch_size,
            seed=args.seed,
        )

        return 0

    except KeyboardInterrupt:

        logger.warning(
            "Seed interrupted by user."
        )

        return 130

    except Exception as exc:

        logger.error(
            "Seed failed: %s",
            exc,
        )

        return 1


if __name__ == "__main__":
    sys.exit(main())