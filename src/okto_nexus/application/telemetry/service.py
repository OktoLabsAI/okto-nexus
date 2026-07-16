"""Telemetry facade used by Nexus adapters."""

from __future__ import annotations

from typing import Any, Mapping

from ..ports import Clock
from .ports import TelemetryEventStore, TelemetrySink
from .schema import CURRENT_SCHEMA_VERSION, TelemetrySchemaError, normalize_event

MODE_DISABLED = "disabled"
MODE_LOCAL_ONLY = "local_only"
MODE_ANONYMOUS_BEACON = "anonymous_beacon"
PUBLISHING_MODES = frozenset({MODE_ANONYMOUS_BEACON})


class TelemetryService:
    """Small, best-effort telemetry facade.

    Errors never escape this service. Runtime paths should treat telemetry as an
    observational side effect, not as business logic.
    """

    def __init__(
        self,
        *,
        config: Any,
        store: TelemetryEventStore,
        clock: Clock,
        sink: TelemetrySink | None = None,
        runtime: str = "okto-nexus",
        app_version: str = "dev",
    ) -> None:
        self._config = config
        self._store = store
        self._clock = clock
        self._sink = sink
        self._runtime = runtime
        self._app_version = app_version

    @property
    def mode(self) -> str:
        return str(getattr(self._config, "metrics_mode", MODE_DISABLED) or MODE_DISABLED)

    @property
    def enabled(self) -> bool:
        return self.mode != MODE_DISABLED

    def record_event(self, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {"written": False, "reason": "disabled"}
        try:
            event = normalize_event(
                event_type=event_type,
                payload=payload,
                occurred_at=self._clock.now_iso(),
                runtime=self._runtime,
                app_version=self._app_version,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
            self._store.append_event(event)
            return {"written": True, "event_type": event_type}
        except TelemetrySchemaError as exc:
            return {"written": False, "reason": exc.code}
        except Exception:
            return {"written": False, "reason": "telemetry_unavailable"}

    def publish_pending(self) -> dict[str, Any]:
        if self.mode not in PUBLISHING_MODES:
            return {"sent": False, "reason": self.mode}
        if self._sink is None:
            return {"sent": False, "reason": "sink_unavailable"}
        try:
            return self._sink.send_pending(self._store)
        except Exception:
            return {"sent": False, "reason": "publish_failed"}

    def summary(self) -> dict[str, Any]:
        try:
            data = self._store.summary()
        except Exception:
            data = {"event_count": 0, "pending_count": 0, "error": "summary_unavailable"}
        data["mode"] = self.mode
        data["schema_version"] = CURRENT_SCHEMA_VERSION
        return data

    def publish_health(self) -> dict[str, Any]:
        try:
            state = self._store.load_state()
        except Exception:
            return {
                "status": "unavailable",
                "mode": self.mode,
                "reason": "state_unavailable",
                "redaction_applied": True,
            }
        failure = state.get("failure_state") if isinstance(state, dict) else None
        failure = failure if isinstance(failure, dict) else {}
        if self.mode == MODE_DISABLED:
            status = "disabled"
        elif failure.get("status"):
            status = str(failure["status"])
        else:
            status = "unknown"
        install_id = str(state.get("install_id") or "") if isinstance(state, dict) else ""
        redacted = f"{install_id[:8]}..." if install_id else None
        return {
            "status": status,
            "mode": self.mode,
            "last_success_at": failure.get("last_success_at"),
            "last_failure_at": failure.get("last_failure_at"),
            "reason_code": failure.get("reason_code"),
            "http_status": failure.get("http_status"),
            "next_retry_at": failure.get("next_retry_at"),
            "retry_count": int(failure.get("retry_count") or 0),
            "install_id_redacted": redacted,
            "redaction_applied": True,
        }
