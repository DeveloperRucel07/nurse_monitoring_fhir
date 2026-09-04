import os

BASE_URL = os.getenv("FHIR_SERVER_URL", "http://localhost:8080/fhir")
FHIR_CONNECT_TIMEOUT = float(os.getenv("FHIR_CONNECT_TIMEOUT", "3.05"))
FHIR_READ_TIMEOUT = float(os.getenv("FHIR_READ_TIMEOUT", "15"))
FHIR_RETRY_TOTAL = int(os.getenv("FHIR_RETRY_TOTAL", "2"))
FHIR_MAX_RESPONSE_BYTES = int(
    os.getenv("FHIR_MAX_RESPONSE_BYTES", str(10 * 1024 * 1024))
)
FHIR_PAGE_SIZE = int(os.getenv("FHIR_PAGE_SIZE", "200"))
FHIR_MAX_PAGES = int(os.getenv("FHIR_MAX_PAGES", "100"))
FHIR_MAX_SEARCH_RESOURCES = int(os.getenv("FHIR_MAX_SEARCH_RESOURCES", "10000"))

ML_MODE = os.getenv("ML_MODE", "disabled").strip().lower()
if ML_MODE not in {"disabled", "synthetic-demo"}:
    raise RuntimeError("ML_MODE must be either 'disabled' or 'synthetic-demo'")

APP_ORIGIN = os.getenv("APP_ORIGIN", "http://localhost:8501").rstrip("/")
PATIENT_IDENTIFIER_SYSTEM = os.getenv(
    "PATIENT_IDENTIFIER_SYSTEM",
    "https://monitoring-pflege.local/identifier/patient",
)
ENCOUNTER_IDENTIFIER_SYSTEM = os.getenv(
    "ENCOUNTER_IDENTIFIER_SYSTEM",
    "https://monitoring-pflege.local/identifier/encounter",
)
NURSING_REPORT_IDENTIFIER_SYSTEM = os.getenv(
    "NURSING_REPORT_IDENTIFIER_SYSTEM",
    "https://monitoring-pflege.local/identifier/nursing-report",
)
