"""Sentry initialization and event scrubbing for server processes."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
except ImportError:  # pragma: no cover - exercised only before dependencies are installed
    sentry_sdk = None
    FastApiIntegration = None

_SENSITIVE_HEADERS = {"authorization", "api-key", "x-api-key", "x-auth-token"}
_SENSITIVE_QUERY_PARAMS = {
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "password",
    "secret",
    "token",
}


def _scrub_query_string(value: str) -> str:
    """Remove sensitive values while retaining safe request context."""
    pairs = parse_qsl(value, keep_blank_values=True)
    return urlencode(
        [(key, "[Filtered]" if key.lower() in _SENSITIVE_QUERY_PARAMS else item) for key, item in pairs]
    )


def _scrub_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.query:
        return value
    return urlunsplit(parsed._replace(query=_scrub_query_string(parsed.query)))


def scrub_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    """Remove credentials and request payloads before Sentry receives an event."""
    request = event.get("request")
    if not isinstance(request, dict):
        return event

    headers = request.get("headers")
    if isinstance(headers, dict):
        request["headers"] = {
            key: value for key, value in headers.items() if key.lower() not in _SENSITIVE_HEADERS
        }
    if "data" in request:
        request["data"] = "[Filtered]"
    if isinstance(request.get("query_string"), str):
        request["query_string"] = _scrub_query_string(request["query_string"])
    if isinstance(request.get("url"), str):
        request["url"] = _scrub_url(request["url"])
    return event


def _init_sentry(*, integrations: list[Any]) -> bool:
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn or sentry_sdk is None:
        return False

    sentry_sdk.init(
        dsn=dsn,
        integrations=integrations,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        release=os.environ.get("SENTRY_RELEASE") or None,
        traces_sample_rate=0.1,
        send_default_pii=False,
        before_send=scrub_event,
    )
    return True


def init_fastapi_sentry() -> bool:
    """Initialize Sentry for the FastAPI process when an operator configures a DSN."""
    return _init_sentry(integrations=[FastApiIntegration()] if FastApiIntegration else [])


def init_worker_sentry() -> bool:
    """Initialize Sentry for a background worker when an operator configures a DSN."""
    return _init_sentry(integrations=[])
