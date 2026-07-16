"""Telemetry ports for the hexagonal application boundary."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class TelemetryEventStore(Protocol):
    """Local, install-owned telemetry persistence."""

    def append_event(self, event: Mapping[str, Any]) -> None:
        """Persist one normalized telemetry event."""
        ...

    def iter_events(self) -> list[dict[str, Any]]:
        """Return locally persisted events in stable order."""
        ...

    def confirmed_event_ids(self) -> set[str]:
        """Event ids already acknowledged by the remote ingest."""
        ...

    def append_sent(
        self,
        *,
        batch_seq: int,
        event_ids: list[str],
        sent_at: str,
        response: Mapping[str, Any] | None = None,
    ) -> None:
        """Persist a remote acknowledgement for local audit/watermarking."""
        ...

    def load_state(self) -> dict[str, Any]:
        """Read full local telemetry state."""
        ...

    def save_state(self, state: Mapping[str, Any]) -> None:
        """Replace full local telemetry state atomically."""
        ...

    def summary(self) -> dict[str, Any]:
        """Return an allowlisted, secret-free local summary."""
        ...

    def export_local(self) -> dict[str, Any]:
        """Return a local diagnostic export without install tokens."""
        ...


@runtime_checkable
class TelemetrySink(Protocol):
    """Remote publisher for pending telemetry."""

    def send_pending(self, store: TelemetryEventStore) -> dict[str, Any]:
        """Publish pending events and return a bounded outcome."""
        ...


@runtime_checkable
class TelemetryPort(Protocol):
    """Facade consumed by inbound adapters and composition roots."""

    def record_event(self, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Capture a bounded telemetry event."""
        ...

    def publish_pending(self) -> dict[str, Any]:
        """Trigger one best-effort publish cycle."""
        ...

    def summary(self) -> dict[str, Any]:
        """Return local metrics summary."""
        ...

    def publish_health(self) -> dict[str, Any]:
        """Return the local publish-health projection."""
        ...
