"""Closed telemetry schema and anti-exfiltration checks.

The schema is deliberately small. Nexus publishes aggregate usage signals, never
message bodies, prompts, paths from the operator machine, raw ids, API keys, or
stack traces.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Mapping

CURRENT_SCHEMA_VERSION = "1.0.0"

EVENT_CLI = "cli"
EVENT_HTTP = "http"
EVENT_MCP = "mcp"
EVENT_COORDINATION = "coordination"
EVENT_LIFECYCLE = "lifecycle"
EVENT_TYPES = frozenset(
    {EVENT_CLI, EVENT_HTTP, EVENT_MCP, EVENT_COORDINATION, EVENT_LIFECYCLE}
)

ALLOWED_PAYLOAD_KEYS: dict[str, frozenset[str]] = {
    EVENT_CLI: frozenset({"command", "status", "error_class", "duration_ms"}),
    EVENT_HTTP: frozenset(
        {"method", "route_template", "status_code", "error_class", "duration_ms"}
    ),
    EVENT_MCP: frozenset({"tool_name", "status", "error_code", "duration_ms"}),
    EVENT_COORDINATION: frozenset(
        {"coordination_type", "stream", "visibility", "status"}
    ),
    EVENT_LIFECYCLE: frozenset({"action", "status", "error_class", "duration_ms"}),
}

BOUNDED_STRING_KEYS = frozenset(
    {
        "command",
        "status",
        "error_class",
        "method",
        "route_template",
        "tool_name",
        "error_code",
        "coordination_type",
        "stream",
        "visibility",
        "action",
    }
)

FORBIDDEN_KEY_FRAGMENTS = (
    "api_key",
    "body",
    "content",
    "email",
    "file",
    "id",
    "ip",
    "message",
    "name",
    "password",
    "path",
    "payload",
    "prompt",
    "query",
    "secret",
    "stack",
    "subject",
    "target",
    "title",
    "token",
    "traceback",
    "url",
    "uri",
)
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


class TelemetrySchemaError(ValueError):
    """Raised when an event would violate the public telemetry contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _reject_forbidden_key(key: str) -> None:
    lowered = key.lower()
    if key == "tool_name":
        return
    if any(fragment in lowered for fragment in FORBIDDEN_KEY_FRAGMENTS):
        raise TelemetrySchemaError(
            "FORBIDDEN_PAYLOAD_KEY",
            f"Telemetry payload key is not allowed: {key}",
        )


def _coerce_bounded_string(key: str, value: Any) -> str:
    if not isinstance(value, str):
        raise TelemetrySchemaError(
            "INVALID_PAYLOAD_VALUE", f"Telemetry value for {key} must be a string."
        )
    text = value.strip()
    if not text or len(text) > 128:
        raise TelemetrySchemaError(
            "INVALID_PAYLOAD_VALUE",
            f"Telemetry value for {key} must be 1..128 characters.",
        )
    if _EMAIL_RE.search(text) or _WINDOWS_PATH_RE.search(text) or _UUID_RE.search(text):
        raise TelemetrySchemaError(
            "SENSITIVE_PAYLOAD_VALUE",
            f"Telemetry value for {key} looks sensitive.",
        )
    if "://" in text and key != "route_template":
        raise TelemetrySchemaError(
            "SENSITIVE_PAYLOAD_VALUE",
            f"Telemetry value for {key} must not contain URLs.",
        )
    return text


def _coerce_int(key: str, value: Any, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise TelemetrySchemaError(
            "INVALID_PAYLOAD_VALUE", f"Telemetry value for {key} must be an integer."
        )
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise TelemetrySchemaError(
            "INVALID_PAYLOAD_VALUE", f"Telemetry value for {key} must be an integer."
        ) from None
    if number < minimum or number > maximum:
        raise TelemetrySchemaError(
            "INVALID_PAYLOAD_VALUE",
            f"Telemetry value for {key} must be between {minimum} and {maximum}.",
        )
    return number


def normalize_payload(event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise TelemetrySchemaError("INVALID_EVENT_TYPE", "Unknown telemetry event type.")
    if not isinstance(payload, Mapping):
        raise TelemetrySchemaError("INVALID_PAYLOAD", "Telemetry payload must be an object.")
    allowed = ALLOWED_PAYLOAD_KEYS[event_type]
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in allowed:
            raise TelemetrySchemaError(
                "UNSUPPORTED_PAYLOAD_KEY",
                f"Telemetry payload key is not supported for {event_type}: {key}",
            )
        _reject_forbidden_key(key)
        if value is None:
            continue
        if key in BOUNDED_STRING_KEYS:
            out[key] = _coerce_bounded_string(key, value)
        elif key == "status_code":
            out[key] = _coerce_int(key, value, minimum=100, maximum=599)
        elif key == "duration_ms":
            out[key] = _coerce_int(key, value, minimum=0, maximum=3_600_000)
        else:
            raise TelemetrySchemaError(
                "UNSUPPORTED_PAYLOAD_KEY",
                f"Telemetry payload key is not supported: {key}",
            )
    return out


def normalize_event(
    *,
    event_type: str,
    payload: Mapping[str, Any],
    occurred_at: str,
    runtime: str,
    app_version: str,
    schema_version: str = CURRENT_SCHEMA_VERSION,
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "event_id": uuid.uuid4().hex,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "runtime": runtime,
        "app_version": app_version,
        "payload": normalize_payload(event_type, payload),
    }
