from __future__ import annotations

import re
import threading
from collections.abc import Collection
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.app.core.config import (
    BASE_URL,
    FHIR_CONNECT_TIMEOUT,
    FHIR_MAX_PAGES,
    FHIR_MAX_RESPONSE_BYTES,
    FHIR_MAX_SEARCH_RESOURCES,
    FHIR_PAGE_SIZE,
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
        page_size: int = FHIR_PAGE_SIZE,
        max_pages: int = FHIR_MAX_PAGES,
        max_search_resources: int = FHIR_MAX_SEARCH_RESOURCES,
        session: requests.Session | None = None,
    ) -> None:
        if connect_timeout <= 0 or read_timeout <= 0:
            raise ValueError("FHIR timeouts must be greater than zero")
        if retries < 0:
            raise ValueError("FHIR retries cannot be negative")
        if max_response_bytes < 1024:
            raise ValueError("FHIR_MAX_RESPONSE_BYTES must be at least 1024")
        if not 1 <= page_size <= 1000:
            raise ValueError("FHIR_PAGE_SIZE must be between 1 and 1000")
        if max_pages < 1:
            raise ValueError("FHIR_MAX_PAGES must be greater than zero")
        if max_search_resources < 1:
            raise ValueError("FHIR_MAX_SEARCH_RESOURCES must be greater than zero")

        self.base_url = base_url.rstrip("/")
        self.timeout = (connect_timeout, read_timeout)
        self.max_response_bytes = max_response_bytes
        self.page_size = page_size
        self.max_pages = max_pages
        self.max_search_resources = max_search_resources
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

    def _request_url(
        self,
        method: str,
        url: str,
        *,
        expected_resource_types: Collection[str] | None = None,
        validation_request: bool = False,
        expect_body: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
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

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        return self._request_url(
            method,
            f"{self.base_url}/{endpoint.lstrip('/')}",
            **kwargs,
        )

    def _safe_next_url(self, value: str, current_url: str) -> str:
        """Resolve a server-provided next link without allowing cross-origin access."""
        candidate = urlsplit(urljoin(current_url, value))
        base = urlsplit(self.base_url)
        if (
            candidate.scheme.lower() != base.scheme.lower()
            or candidate.netloc.lower() != base.netloc.lower()
        ):
            raise FhirBadGatewayError(
                "Der FHIR-Server hat einen unsicheren Pagination-Link geliefert."
            )

        base_path = base.path.rstrip("/")
        candidate_path = candidate.path.rstrip("/")
        if candidate_path != base_path and not candidate_path.startswith(
            f"{base_path}/"
        ):
            raise FhirBadGatewayError(
                "Der FHIR-Server hat einen ungültigen Pagination-Link geliefert."
            )
        return urlunsplit(
            (base.scheme, base.netloc, candidate.path, candidate.query, "")
        )

    @staticmethod
    def _bundle_entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
        entries = bundle.get("entry", [])
        if not isinstance(entries, list) or not all(
            isinstance(entry, dict) for entry in entries
        ):
            raise FhirBadGatewayError(
                "Der FHIR-Server hat ein ungültiges Such-Bundle geliefert."
            )
        return entries

    def _next_page_url(
        self,
        bundle: dict[str, Any],
        current_url: str,
    ) -> str | None:
        links = bundle.get("link", [])
        if not isinstance(links, list):
            raise FhirBadGatewayError(
                "Der FHIR-Server hat ungültige Bundle-Links geliefert."
            )
        next_links = [
            link.get("url")
            for link in links
            if isinstance(link, dict) and link.get("relation") == "next"
        ]
        if not next_links:
            return None
        if len(next_links) != 1 or not isinstance(next_links[0], str):
            raise FhirBadGatewayError(
                "Der FHIR-Server hat einen ungültigen Pagination-Link geliefert."
            )
        return self._safe_next_url(next_links[0], current_url)

    def _search_all_pages(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        search_params = dict(params or {})
        search_params["_count"] = str(self.page_size)
        first_url = f"{self.base_url}/{endpoint.lstrip('/')}"
        first_page = self._request_url(
            "GET",
            first_url,
            params=search_params,
            expected_resource_types={"Bundle"},
        )
        assert first_page is not None

        entries = list(self._bundle_entries(first_page))
        if len(entries) > self.max_search_resources:
            raise FhirBadGatewayError(
                "Die FHIR-Suche überschreitet die konfigurierte Ressourcengrenze."
            )

        page_count = 1
        next_url = self._next_page_url(first_page, first_url)
        visited_urls: set[str] = set()
        while next_url is not None:
            if page_count >= self.max_pages:
                raise FhirBadGatewayError(
                    "Die FHIR-Suche überschreitet die konfigurierte Seitengrenze."
                )
            if next_url in visited_urls:
                raise FhirBadGatewayError(
                    "Der FHIR-Server hat eine Pagination-Schleife geliefert."
                )
            visited_urls.add(next_url)

            page = self._request_url(
                "GET",
                next_url,
                expected_resource_types={"Bundle"},
            )
            assert page is not None
            entries.extend(self._bundle_entries(page))
            if len(entries) > self.max_search_resources:
                raise FhirBadGatewayError(
                    "Die FHIR-Suche überschreitet die konfigurierte Ressourcengrenze."
                )
            page_count += 1
            next_url = self._next_page_url(page, next_url)

        result = dict(first_page)
        if entries:
            result["entry"] = entries
        else:
            result.pop("entry", None)
        links = [
            link
            for link in first_page.get("link", [])
            if isinstance(link, dict) and link.get("relation") != "next"
        ]
        if links:
            result["link"] = links
        else:
            result.pop("link", None)
        return result

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

    def get_resource(
        self,
        resource_type: str,
        resource_id: str,
    ) -> dict[str, Any]:
        safe_type = self._safe_resource_type(resource_type)
        result = self._request(
            "GET",
            f"{safe_type}/{self._safe_id(resource_id)}",
            expected_resource_types={safe_type},
        )
        assert result is not None
        return result

    def update_resource(
        self,
        resource_type: str,
        resource_id: str,
        resource_data: dict[str, Any],
        *,
        expected_version_id: str,
    ) -> dict[str, Any]:
        safe_type = self._safe_resource_type(resource_type)
        safe_id = self._safe_id(resource_id)
        safe_version = self._safe_id(expected_version_id)
        self.validate_resource(safe_type, resource_data)
        result = self._request(
            "PUT",
            f"{safe_type}/{safe_id}",
            json=resource_data,
            headers={"If-Match": f'W/"{safe_version}"'},
            expected_resource_types={safe_type},
        )
        assert result is not None
        return result

    def transaction(self, bundle: dict[str, Any]) -> dict[str, Any]:
        """Execute a small, server-constructed atomic FHIR transaction."""
        if (
            bundle.get("resourceType") != "Bundle"
            or bundle.get("type") != "transaction"
        ):
            raise FhirRequestError("Ungültiges FHIR-Transaktions-Bundle.")
        entries = bundle.get("entry")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 20:
            raise FhirRequestError("Ungültige Anzahl von Transaktionseinträgen.")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(
                entry.get("resource"), dict
            ):
                raise FhirRequestError("Ungültiger FHIR-Transaktionseintrag.")
            resource = entry["resource"]
            resource_type = resource.get("resourceType")
            if not isinstance(resource_type, str):
                raise FhirRequestError("FHIR-Ressourcentyp fehlt.")
            self.validate_resource(resource_type, resource)
        result = self._request(
            "POST",
            "",
            json=bundle,
            headers={"Prefer": "return=representation"},
            expected_resource_types={"Bundle"},
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
        return self._search_all_pages("Patient", params)

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
        return self._search_all_pages("Observation", params)

    def search_resources(
        self,
        resource_type: str,
        patient_id: str,
        patient_parameter: str = "subject",
    ) -> dict[str, Any]:
        safe_type = self._safe_resource_type(resource_type)
        if patient_parameter not in PATIENT_SEARCH_PARAMETERS:
            raise FhirRequestError("Ungültiger FHIR-Suchparameter.")
        return self._search_all_pages(
            safe_type,
            {patient_parameter: f"Patient/{self._safe_id(patient_id)}"},
        )

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
