import os

BASE_URL = os.getenv("FHIR_SERVER_URL", "http://localhost:8080/fhir")
FHIR_CONNECT_TIMEOUT = float(os.getenv("FHIR_CONNECT_TIMEOUT", "3.05"))
FHIR_READ_TIMEOUT = float(os.getenv("FHIR_READ_TIMEOUT", "15"))
FHIR_RETRY_TOTAL = int(os.getenv("FHIR_RETRY_TOTAL", "2"))
FHIR_MAX_RESPONSE_BYTES = int(
    os.getenv("FHIR_MAX_RESPONSE_BYTES", str(10 * 1024 * 1024))
)
