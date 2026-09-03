from __future__ import annotations

from typing import Any


class FhirClientError(RuntimeError):
    """Base error for safe, classified failures of the upstream FHIR server."""

    http_status = 502
    issue_code = "exception"

    def __init__(self, message: str, *, diagnostics: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or []

    def operation_outcome(self) -> dict[str, Any]:
        issues = [
            {"severity": "error", "code": self.issue_code, "diagnostics": self.message}
        ]
        issues.extend(
            {
                "severity": "error",
                "code": self.issue_code,
                "diagnostics": detail,
            }
            for detail in self.diagnostics[:10]
            if detail and detail != self.message
        )
        return {"resourceType": "OperationOutcome", "issue": issues}


class FhirUnavailableError(FhirClientError):
    http_status = 503
    issue_code = "transient"


class FhirTimeoutError(FhirClientError):
    http_status = 504
    issue_code = "timeout"


class FhirBadGatewayError(FhirClientError):
    http_status = 502
    issue_code = "exception"


class FhirRequestError(FhirClientError):
    http_status = 400
    issue_code = "invalid"


class FhirValidationError(FhirClientError):
    http_status = 422
    issue_code = "invalid"


class FhirNotFoundError(FhirClientError):
    http_status = 404
    issue_code = "not-found"


class FhirConflictError(FhirClientError):
    http_status = 409
    issue_code = "conflict"


class FhirPreconditionFailedError(FhirClientError):
    http_status = 412
    issue_code = "conflict"


class FhirRateLimitError(FhirClientError):
    http_status = 429
    issue_code = "throttled"
