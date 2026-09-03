from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


audit_logger = logging.getLogger("uvicorn.audit")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _request_id(request: Request) -> str:
    supplied = request.headers.get("X-Request-ID", "")
    if REQUEST_ID_PATTERN.fullmatch(supplied):
        return supplied
    return str(uuid.uuid4())


def _audit_entry(
    request: Request,
    *,
    request_id: str,
    status_code: int,
    duration_ms: float,
) -> dict[str, Any]:
    claims = getattr(request.state, "user_claims", {})
    route = request.scope.get("route")
    route_template = getattr(route, "path", "<unmatched>")
    return {
        "event": "api_access",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "method": request.method,
        "route": route_template,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        "user_id": claims.get("sub"),
        "username": claims.get("preferred_username"),
        "client_id": claims.get("azp"),
    }


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = _request_id(request)
        request.state.request_id = request_id
        started_at = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started_at) * 1000
            audit_logger.info(
                json.dumps(
                    _audit_entry(
                        request,
                        request_id=request_id,
                        status_code=500,
                        duration_ms=duration_ms,
                    ),
                    ensure_ascii=False,
                )
            )
            raise

        duration_ms = (time.perf_counter() - started_at) * 1000
        response.headers["X-Request-ID"] = request_id
        audit_logger.info(
            json.dumps(
                _audit_entry(
                    request,
                    request_id=request_id,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                ),
                ensure_ascii=False,
            )
        )
        return response
