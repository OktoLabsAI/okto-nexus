"""Telemetry decorator for the coordination event emitter."""

from __future__ import annotations

from typing import Any, Mapping

from ....application.ports import EventEmitter, UnitOfWork
from ....application.telemetry.ports import TelemetryPort
from ....application.telemetry.schema import EVENT_COORDINATION


class TelemetryEventEmitter:
    """Record bounded coordination telemetry after successful event appends."""

    def __init__(self, inner: EventEmitter, telemetry: TelemetryPort) -> None:
        self._inner = inner
        self._telemetry = telemetry

    def emit(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        stream: str,
        type: str,
        payload: Mapping[str, Any] | None = None,
        actor_agent_id: str | None = None,
        visibility: str | None = None,
        target: str | None = None,
    ) -> int:
        event_id = self._inner.emit(
            uow,
            workspace_id=workspace_id,
            stream=stream,
            type=type,
            payload=payload,
            actor_agent_id=actor_agent_id,
            visibility=visibility,
            target=target,
        )
        self._telemetry.record_event(
            EVENT_COORDINATION,
            {
                "coordination_type": type,
                "stream": stream,
                "visibility": visibility or "unknown",
                "status": "ok",
            },
        )
        return event_id
