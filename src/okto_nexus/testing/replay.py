"""Replay reconstruction + export helpers for evals (spec c7c1f834, I8).

The re-executable coordination benchmark closes here: :func:`load_replay` parses
an NDJSON export (fail-closed via the domain parser), :func:`replay`
RECONSTRUCTS those raw events into a fresh, empty hub — preserving each
``event_id`` and ``created_at`` verbatim, seeding the ``workspaces`` FK row
first — and :func:`export_lines` re-exports from any booted hub through the same
production producer. An eval asserts the reconstructed log re-exports to the SAME
event bytes and yields the SAME :func:`coordination_invariants` as the original
(modulo the manifest ``generated_at``), proving the log is a faithful,
replayable record.

Outside the import boundary, so it is free to touch sqlite through the injected
``deps`` and re-export ``coordination_invariants`` from the pure domain core (one
definition of the invariants, never re-implemented).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.replay import (
    coordination_invariants as coordination_invariants,  # re-export (single source)
)
from ..domain.replay import parse_line, parse_manifest
from ..errors import ErrorCode, OktoNexusError

__all__ = [
    "ReplayBundle",
    "load_replay",
    "replay",
    "export_lines",
    "coordination_invariants",
]

_FALLBACK_CREATED_AT = "1970-01-01T00:00:00.000000Z"


@dataclass(frozen=True)
class ReplayBundle:
    """A parsed export: the leading ``manifest`` and the ordered ``events``."""

    manifest: dict[str, Any]
    events: list[dict[str, Any]]


def load_replay(path: str | Path) -> ReplayBundle:
    """Parse an NDJSON export file into a :class:`ReplayBundle` (fail-closed).

    The first line MUST be a manifest of a recognised ``format_version`` (the
    domain parser rejects otherwise); every remaining non-blank line is one
    event. Read as UTF-8 so non-ASCII payloads round-trip intact.
    """
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR, "replay file is empty.", {"path": str(path)}
        )
    manifest = parse_manifest(lines[0])
    events = [parse_line(line) for line in lines[1:] if line.strip()]
    return ReplayBundle(manifest=manifest, events=events)


def _as_text(value: Any) -> str | None:
    """Serialise a parsed payload/target dict back to the stored JSON text.

    ``None`` stays ``NULL``; an already-serialised string passes through; a dict
    is dumped with the canonical compact/UTF-8 recipe. Fidelity does not depend
    on matching the ORIGINAL bytes — the read path re-normalises through
    ``_loads`` -> ``serialize_event``, so any JSON that parses to the same dict
    re-exports identically.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _earliest_created_at(
    events: Sequence[dict[str, Any]], workspace_id: str
) -> str | None:
    stamps = [
        ev["created_at"]
        for ev in events
        if ev.get("workspace_id") == workspace_id and ev.get("created_at")
    ]
    return min(stamps) if stamps else None


def replay(deps: Any, events: Sequence[dict[str, Any]]) -> set[str]:
    """Reconstruct ``events`` into a fresh hub's store; return the workspace ids.

    Seeds a ``workspaces`` row for every distinct ``workspace_id`` BEFORE the
    events (the events FK references it), then raw-INSERTs each event with its
    ORIGINAL ``event_id`` and ``created_at`` so the reconstructed log is
    byte-faithful. Intended for an EMPTY hub (freshly bootstrapped); inserting a
    duplicate ``event_id`` is a programming error the sqlite PK will surface.
    """
    workspace_ids = {
        str(ev["workspace_id"]) for ev in events if ev.get("workspace_id") is not None
    }
    ordered = sorted(events, key=lambda ev: ev["event_id"])
    with deps.connection_factory.unit_of_work(write=True) as uow:
        conn = uow.connection
        for wid in sorted(workspace_ids):
            exists = conn.execute(
                "SELECT 1 FROM workspaces WHERE workspace_id = ?", (wid,)
            ).fetchone()
            if exists is None:
                created = _earliest_created_at(events, wid) or _FALLBACK_CREATED_AT
                conn.execute(
                    "INSERT INTO workspaces (workspace_id, display_name, "
                    "root_realpath, created_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
                    (wid, None, None, created, None),
                )
        for ev in ordered:
            conn.execute(
                "INSERT INTO events (event_id, workspace_id, stream, type, "
                "actor_agent_id, payload, visibility, target, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ev["event_id"],
                    ev["workspace_id"],
                    ev["stream"],
                    ev["type"],
                    ev.get("actor_agent_id"),
                    _as_text(ev.get("payload")),
                    ev.get("visibility"),
                    _as_text(ev.get("target")),
                    ev["created_at"],
                ),
            )
    return workspace_ids


def export_lines(
    deps: Any,
    workspace_id: str,
    *,
    generated_at: str | None = None,
    stream: str | None = None,
    trace_id: str | None = None,
    since_event_id: int = 0,
    until_event_id: int | None = None,
) -> list[str]:
    """Export a booted hub's event log via the production producer.

    Centralises the "how to export from a ``deps``" wiring so an eval never
    re-derives it: builds the same ``ObservabilityService`` + ``ReplayExportService``
    the CLI/REST use, over one read snapshot. ``generated_at`` defaults to the
    hub clock; pin it to make even the manifest line reproducible.
    """
    from ..adapters.outbound.sqlite.observability_repo import SqliteObservabilityQueries
    from ..application.observability import ObservabilityService
    from ..application.replay import ReplayExportService

    observability = ObservabilityService(
        SqliteObservabilityQueries(), deps.clock, deps.config
    )
    service = ReplayExportService(observability, deps.config)
    stamp = generated_at if generated_at is not None else deps.clock.now_iso()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return list(
            service.export_lines(
                uow,
                workspace_id=workspace_id,
                generated_at=stamp,
                stream=stream,
                trace_id=trace_id,
                since_event_id=since_event_id,
                until_event_id=until_event_id,
            )
        )
