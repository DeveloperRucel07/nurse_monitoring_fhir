from __future__ import annotations

import re
import threading
from collections.abc import Collection
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.app.core.config import (
    BASE_URL,
    FHIR_CONNECT_TIMEOUT,
    FHIR_MAX_RESPONSE_BYTES,
    FHIR_READ_TIMEOUT,
    FHIR_RETRY_TOTAL,
)
from backend.app.core.exceptions import (
    FhirBadGatewayError,
    FhirClientError,
    FhirConflictError,
    FhirNotFoundError,
    FhirPreconditionFailedError,
    FhirRateLimitError,
    FhirRequestError,
    FhirTimeoutError,
    FhirUnavailableError,
    FhirValidationError,
)

FHIR_ID_PATTERN = re.compile(r"^[A-Za-z0-9.-]{1,64}$")
FHIR_RESOURCE_TYPE_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9]{0,63}$")
PATIENT_SEARCH_PARAMETERS = frozenset({"subject", "patient"})
FHIR_JSON_MEDIA_TYPES = frozenset({"application/fhir+json", "application/json"})


def _safe_diagnostics(response: requests.Response) -> list[str]:
    """Extract bounded OperationOutcome diagnostics without exposing raw bodies."""
    try:
        payload = response.json()
    except ValueError:
        return []
    if (
        not isinstance(payload, dict)
        or payload.get("resourceType") != "OperationOutcome"
    ):
        return []

    diagnostics: list[str] = []
    for issue in payload.get("issue", []):
        if not isinstance(issue, dict):
            continue
        text = issue.get("diagnostics") or (issue.get("details") or {}).get("text")
        if isinstance(text, str) and text.strip():
            diagnostics.append(text.strip()[:1000])
    return diagnostics


class FHIRClient:
    """Reliable, bounded HTTP adapter for a FHIR R4 server."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        *,
        connect_timeout: float = FHIR_CONNECT_TIMEOUT,
        read_timeout: float = FHIR_READ_TIMEOUT,
        retries: int = FHIR_RETRY_TOTAL,
        max_response_bytes: int = FHIR_MAX_RESPONSE_BYTES,
        session: requests.Session | None = None,
    ) -> None:
        if connect_timeout <= 0 or read_timeout <= 0:
            raise ValueError("FHIR timeouts must be greater than zero")
        if retries < 0:
            raise ValueError("FHIR retries cannot be negative")
        if max_response_bytes < 1024:
            raise ValueError("FHIR_MAX_RESPONSE_BYTES must be at least 1024")

        self.base_url = base_url.rstrip("/")
        self.timeout = (connect_timeout, read_timeout)
        self.max_response_bytes = max_response_bytes
        self._provided_session = session
        self._thread_local = threading.local()
        self._retry_policy = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            allowed_methods=frozenset({"GET", "HEAD", "OPTIONS"}),
            status_forcelist=(502, 503, 504),
            backoff_factor=0.25,
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        if session is not None:
            self._configure_session(session)

    def _configure_session(self, session: requests.Session) -> None:
        session.headers.update(
            {
                "Accept": "application/fhir+json",
                "Content-Type": "application/fhir+json",
            }
        )
        session.mount("http://", HTTPAdapter(max_retries=self._retry_policy))
        session.mount("https://", HTTPAdapter(max_retries=self._retry_policy))

    @property
    def session(self) -> requests.Session:
        if self._provided_session is not None:
            return self._provided_session
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            self._configure_session(session)
            self._thread_local.session = session
        return session

    @staticmethod
    def _safe_id(resource_id: str) -> str:
        if not FHIR_ID_PATTERN.fullmatch(resource_id):
            raise FhirRequestError("Ungültige FHIR-Ressourcen-ID.")
        return resource_id

    @staticmethod
    def _safe_resource_type(resource_type: str) -> str:
        if not FHIR_RESOURCE_TYPE_PATTERN.fullmatch(resource_type):
            raise FhirRequestError("Ungültiger FHIR-Ressourcentyp.")
        return resource_type

    @staticmethod
    def _error_for_response(
        response: requests.Response,
        *,
        validation_request: bool = False,
    ) -> FhirClientError:
        diagnostics = _safe_diagnostics(response)
        status_code = response.status_code
        if validation_request or status_code == 422:
            return FhirValidationError(
                "Die FHIR-Ressource ist nicht valide.", diagnostics=diagnostics
            )
        if status_code == 400:
            return FhirRequestError(
                "Die FHIR-Anfrage ist ungültig.", diagnostics=diagnostics
            )
        if status_code == 404:
            return FhirNotFoundError(
                "Die angeforderte FHIR-Ressource wurde nicht gefunden."
            )
        if status_code == 409:
            return FhirConflictError(
                "Die FHIR-Ressource steht im Konflikt mit dem aktuellen Datenbestand.",
                diagnostics=diagnostics,
            )
        if status_code == 412:
            return FhirPreconditionFailedError(
                "Die Vorbedingung für die FHIR-Änderung ist nicht mehr erfüllt."
            )
        if status_code == 429:
            return FhirRateLimitError(
                "Der FHIR-Server begrenzt derzeit die Anfragerate."
            )
        return FhirBadGatewayError(
            "Der FHIR-Server hat die Anfrage nicht korrekt verarbeitet."
        )

    def _read_body(self, response: requests.Response) -> None:
        """Consume a streamed response while enforcing the configured size limit."""
        content_length = response.headers.get("Content-Length")
        if content_length and content_length.isdigit():
            if int(content_length) > self.max_response_bytes:
                response.close()
                raise FhirBadGatewayError("Die Antwort des FHIR-Servers ist zu groß.")

        body = bytearray()
        try:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                body.extend(chunk)
                if len(body) > self.max_response_bytes:
                    response.close()
                    raise FhirBadGatewayError(
                        "Die Antwort des FHIR-Servers ist zu groß."
                    )
        except requests.Timeout as exc:
            response.close()
            raise FhirTimeoutError(
                "Der FHIR-Server hat nicht rechtzeitig geantwortet."
            ) from exc
        except requests.RequestException as exc:
            response.close()
            raise FhirBadGatewayError(
                "Die Antwort des FHIR-Servers wurde unvollständig übertragen."
            ) from exc
        response._content = bytes(body)
        response._content_consumed = True

    def _decode_json(
        self,
        response: requests.Response,
        *,
        expected_resource_types: Collection[str] | None,
    ) -> dict[str, Any]:
        media_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if media_type and media_type not in FHIR_JSON_MEDIA_TYPES:
            raise FhirBadGatewayError(
                "Der FHIR-Server hat keinen JSON-Inhalt geliefert."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise FhirBadGatewayError(
                "Der FHIR-Server hat eine ungültige JSON-Antwort geliefert."
            ) from exc
        if not isinstance(payload, dict):
            raise FhirBadGatewayError(
                "Der FHIR-Server hat keine FHIR-Ressource geliefert."
            )
        if (
            expected_resource_types
            and payload.get("resourceType") not in expected_resource_types
        ):
            raise FhirBadGatewayError(
                "Der FHIR-Server hat einen unerwarteten Ressourcentyp geliefert."
            )
        return payload

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        expected_resource_types: Collection[str] | None = None,
        validation_request: bool = False,
        expect_body: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = self.session.request(
                method,
                url,
                timeout=self.timeout,
                stream=True,
                **kwargs,
            )
        except requests.Timeout as exc:
            raise FhirTimeoutError(
                "Der FHIR-Server hat nicht rechtzeitig geantwortet."
            ) from exc
        except requests.ConnectionError as exc:
            raise FhirUnavailableError(
                "Der FHIR-Server ist momentan nicht erreichbar."
            ) from exc
        except requests.RequestException as exc:
            raise FhirBadGatewayError(
                "Die FHIR-Anfrage konnte nicht ausgeführt werden."
            ) from exc

        if response.status_code < 200 or response.status_code >= 300:
            self._read_body(response)
            raise self._error_for_response(
                response,
                validation_request=validation_request,
            )
        if not expect_body or response.status_code == 204:
            response.close()
            return None
        self._read_body(response)
        return self._decode_json(
            response,
            expected_resource_types=expected_resource_types,
        )

    def validate_resource(self, resource_type: str, resource: dict[str, Any]) -> None:
        safe_type = self._safe_resource_type(resource_type)
        if resource.get("resourceType") != safe_type:
            raise FhirValidationError(
                "resourceType stimmt nicht mit dem angeforderten FHIR-Ressourcentyp überein."
            )
        outcome = self._request(
            "POST",
            f"{safe_type}/$validate",
            json=resource,
            validation_request=True,
            expected_resource_types={"OperationOutcome"},
        )
        assert outcome is not None
        issues = outcome.get("issue", [])
        errors = [
            issue
            for issue in issues
            if isinstance(issue, dict) and issue.get("severity") in {"fatal", "error"}
        ]
        if errors:
            diagnostics = [
                str(
                    issue.get("diagnostics")
                    or (issue.get("details") or {}).get("text")
                    or ""
                )[:1000]
                for issue in errors
            ]
            raise FhirValidationError(
                "Die FHIR-Ressource ist nicht valide.", diagnostics=diagnostics
            )

    def create_resource(
        self,
        resource_type: str,
        resource_data: dict[str, Any],
    ) -> dict[str, Any]:
        safe_type = self._safe_resource_type(resource_type)
        self.validate_resource(safe_type, resource_data)
        result = self._request(
            "POST",
            safe_type,
            json=resource_data,
            expected_resource_types={safe_type},
        )
        assert result is not None
        return result

    def create_patient(self, patient_data: dict[str, Any]) -> dict[str, Any]:
        return self.create_resource("Patient", patient_data)

    def get_patient(self, patient_id: str) -> dict[str, Any]:
        result = self._request(
            "GET",
            f"Patient/{self._safe_id(patient_id)}",
            expected_resource_types={"Patient"},
        )
        assert result is not None
        return result

    def update_patient(
        self,
        patient_id: str,
        patient_data: dict[str, Any],
    ) -> dict[str, Any]:
        safe_id = self._safe_id(patient_id)
        self.validate_resource("Patient", patient_data)
        result = self._request(
            "PUT",
            f"Patient/{safe_id}",
            json=patient_data,
            expected_resource_types={"Patient"},
        )
        assert result is not None
        return result

    def delete_patient(self, patient_id: str) -> None:
        self._request(
            "DELETE",
            f"Patient/{self._safe_id(patient_id)}",
            expect_body=False,
        )

    def search_patients(
        self,
        family: str | None = None,
        given: str | None = None,
        birthdate: str | None = None,
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
        result = self._request(
            "GET",
            "Patient",
            params=params,
            expected_resource_types={"Bundle"},
        )
        assert result is not None
        return result

    def create_observation(self, observation_data: dict[str, Any]) -> dict[str, Any]:
        return self.create_resource("Observation", observation_data)

    def get_observation(self, observation_id: str) -> dict[str, Any]:
        result = self._request(
            "GET",
            f"Observation/{self._safe_id(observation_id)}",
            expected_resource_types={"Observation"},
        )
        assert result is not None
        return result

    def search_observations(
        self,
        subject_reference: str | None = None,
        patient_name: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if subject_reference:
            params["subject"] = subject_reference
        if patient_name:
            params["subject:Patient.name"] = patient_name
        result = self._request(
            "GET",
            "Observation",
            params=params,
            expected_resource_types={"Bundle"},
        )
        assert result is not None
        return result

    def search_resources(
        self,
        resource_type: str,
        patient_id: str,
        patient_parameter: str = "subject",
    ) -> dict[str, Any]:
        safe_type = self._safe_resource_type(resource_type)
        if patient_parameter not in PATIENT_SEARCH_PARAMETERS:
            raise FhirRequestError("Ungültiger FHIR-Suchparameter.")
        result = self._request(
            "GET",
            safe_type,
            params={patient_parameter: f"Patient/{self._safe_id(patient_id)}"},
            expected_resource_types={"Bundle"},
        )
        assert result is not None
        return result

    def delete_observation(self, observation_id: str) -> None:
        self._request(
            "DELETE",
            f"Observation/{self._safe_id(observation_id)}",
            expect_body=False,
        )

    def patch_observation(
        self,
        observation_id: str,
        patch_data: list[dict[str, Any]],
    ) -> dict[str, Any]:
        result = self._request(
            "PATCH",
            f"Observation/{self._safe_id(observation_id)}",
            json=patch_data,
            headers={
                "Content-Type": "application/json-patch+json",
                "Accept": "application/fhir+json",
            },
            expected_resource_types={"Observation"},
        )
        assert result is not None
        return result
