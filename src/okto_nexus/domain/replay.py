"""Pure NDJSON replay/export core (spec c7c1f834, I8 — the meta-harness outer
loop closer).

This module owns the *pure* (IO-free, stdlib-only) rules that turn the
append-only event log into a re-executable coordination benchmark:

* the versioned NDJSON wire format — a single canonical serializer
  (:func:`serialize_manifest` / :func:`serialize_event`) shared verbatim by the
  CLI ``admin export`` and the REST download so both emit BYTE-IDENTICAL output
  (modulo the manifest ``generated_at``);
* a fail-closed parser (:func:`parse_manifest` rejects an unknown
  ``format_version``; :func:`parse_line` reconstructs an event);
* the structural coordination invariants (:func:`coordination_invariants`) an
  eval asserts against — histogram, handoff lifecycle (transitions / re-claim
  cycles / terminal), claim->complete latencies (REUSING the I7 correlator),
  message fan-out and per-actor activity, plus range aggregates.

It never imports ``sqlite3`` nor ``mcp`` (enforced by the import-boundary
test) and performs no IO: it serializes/parses dicts and computes over lists of
already-parsed event dicts (the 9 raw columns ``observability_repo.events_after``
projects). The claim->complete correlation is DELEGATED to
:func:`okto_nexus.domain.health.correlate_claim_to_complete` (I7) — one
definition of "a complete claimed->completed pair", never re-implemented.

Fan-out note: the ``message.created`` event payload carries the ``target``
descriptor echo (with its ``strategy``) but NOT ``recipients`` /
``delivered_count`` (those ride the ``message_create`` return, never the log).
So :func:`message_fanout` is derived faithfully from what the log actually holds
— the fan-out STRATEGY breadth per message — not from a delivered count the
event never recorded.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from ..errors import ErrorCode, OktoNexusError
from .handoff import (
    EVENT_CANCELLED,
    EVENT_CLAIMED,
    EVENT_COMPLETED,
    EVENT_CREATED,
    EVENT_REJECTED,
    HANDOFF_STREAM,
)
from .health import HandoffLifecycleEvent, correlate_claim_to_complete

__all__ = [
    "FORMAT_VERSION",
    "MANIFEST_KIND",
    "EVENT_COLUMNS",
    "canonical_filters",
    "serialize_manifest",
    "serialize_event",
    "parse_line",
    "parse_manifest",
    "event_type_histogram",
    "stream_histogram",
    "actor_activity",
    "handoff_lifecycle",
    "claim_to_complete_latencies",
    "message_fanout",
    "coordination_invariants",
]

#: Bumped only on a breaking change to the wire shape. :func:`parse_manifest`
#: rejects any other value fail-closed (BR8) rather than guessing a layout.
FORMAT_VERSION = 1

#: The first NDJSON line is a manifest, tagged so a consumer never mistakes it
#: for an event row.
MANIFEST_KIND = "manifest"

#: The 9 raw event columns, in a FIXED order. A serialized event line is these
#: keys in exactly this sequence — the byte-identity contract (BR3) depends on
#: the order never varying between the CLI and REST callers.
EVENT_COLUMNS: tuple[str, ...] = (
    "event_id",
    "workspace_id",
    "stream",
    "type",
    "actor_agent_id",
    "payload",
    "visibility",
    "target",
    "created_at",
)

#: Message-stream event type prefix and the created type (kept as a string
#: match so domain/replay stays decoupled from the messaging slice's module).
_MESSAGE_PREFIX = "message."
_MESSAGE_CREATED = "message.created"

#: Handoff transitions that END a handoff's life (for the terminal-reached
#: count in :func:`handoff_lifecycle`).
_TERMINAL_HANDOFF_EVENTS: frozenset[str] = frozenset(
    {EVENT_COMPLETED, EVENT_REJECTED, EVENT_CANCELLED}
)


def _dumps(obj: Any) -> str:
    """The ONE canonical JSON rendering: UTF-8 (ensure_ascii=False), compact
    separators, insertion-order keys. Shared by both export vias so their bytes
    match."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def canonical_filters(
    *,
    stream: str | None,
    trace_id: str | None,
    since_event_id: int,
    until_event_id: int | None,
) -> dict[str, Any]:
    """Build the manifest's ``filters`` object with a FIXED key order.

    A stable shape/order keeps the manifest line byte-identical across callers
    that applied the same recipe; absent filters are echoed as ``None`` (never
    dropped) so the manifest always documents every filter dimension.
    """
    return {
        "stream": stream,
        "trace_id": trace_id,
        "since_event_id": int(since_event_id),
        "until_event_id": None if until_event_id is None else int(until_event_id),
    }


def serialize_manifest(
    *,
    workspace_id: str,
    filters: Mapping[str, Any],
    event_count: int,
    event_id_min: int | None,
    event_id_max: int | None,
    generated_at: str,
) -> str:
    """Render the leading manifest line (self-describing; parsed first)."""
    manifest = {
        "kind": MANIFEST_KIND,
        "format_version": FORMAT_VERSION,
        "workspace_id": workspace_id,
        "filters": dict(filters),
        "event_count": int(event_count),
        "event_id_min": event_id_min,
        "event_id_max": event_id_max,
        "generated_at": generated_at,
    }
    return _dumps(manifest)


def serialize_event(event: Mapping[str, Any]) -> str:
    """Render ONE event as an NDJSON line: the 9 raw columns in fixed order.

    ``payload`` / ``target`` are emitted as nested JSON (they are already parsed
    dicts coming from ``events_after``); any convenience keys the read layer
    adds (e.g. a derived ``trace_id``) are dropped — only the 9 columns ship.
    """
    row = {col: event.get(col) for col in EVENT_COLUMNS}
    return _dumps(row)


def parse_line(line: str) -> dict[str, Any]:
    """Parse ONE NDJSON line into a dict, fail-closed on malformed input."""
    try:
        obj = json.loads(line)
    except (TypeError, ValueError) as exc:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "replay line is not valid JSON.",
            {"error": str(exc)},
        ) from exc
    if not isinstance(obj, dict):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "replay line must be a JSON object.",
            {"parsed_type": type(obj).__name__},
        )
    return obj


def parse_manifest(line: str) -> dict[str, Any]:
    """Parse the leading manifest line, rejecting an unknown ``format_version``.

    Fail-closed (BR8): a manifest whose version this build does not recognise is
    rejected outright — the layout is not guessed. A first line that is not a
    manifest is equally rejected.
    """
    obj = parse_line(line)
    if obj.get("kind") != MANIFEST_KIND:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "first replay line must be a manifest (kind='manifest').",
            {"kind": obj.get("kind")},
        )
    version = obj.get("format_version")
    if version != FORMAT_VERSION:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"unsupported replay format_version {version!r}; this build reads "
            f"format_version {FORMAT_VERSION}.",
            {"got": version, "supported": FORMAT_VERSION},
        )
    return obj


# --------------------------------------------------------------------------- #
# Coordination invariants — structural, deterministic, over the raw event list
# --------------------------------------------------------------------------- #
def _payload_of(event: Mapping[str, Any]) -> Mapping[str, Any] | None:
    payload = event.get("payload")
    return payload if isinstance(payload, Mapping) else None


def _iso_to_epoch(value: Any) -> float | None:
    """Parse a canonical UTC ISO timestamp to epoch seconds, or ``None``."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def event_type_histogram(events: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Count events per ``type`` (deterministic, key-sorted)."""
    counts: dict[str, int] = {}
    for ev in events:
        key = str(ev.get("type"))
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def stream_histogram(events: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Count events per ``stream`` (deterministic, key-sorted)."""
    counts: dict[str, int] = {}
    for ev in events:
        key = str(ev.get("stream"))
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def actor_activity(events: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Count events per acting agent (``actor_agent_id``), skipping unattributed
    (null-actor) events. Deterministic, key-sorted."""
    counts: dict[str, int] = {}
    for ev in events:
        actor = ev.get("actor_agent_id")
        if actor is None:
            continue
        key = str(actor)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _handoff_lifecycle_events(
    events: Sequence[Mapping[str, Any]],
) -> list[HandoffLifecycleEvent]:
    """Project ``handoff.*`` rows (that carry a ``handoff_id`` and a parseable
    ``created_at``) into the I7 correlation input shape."""
    out: list[HandoffLifecycleEvent] = []
    for ev in events:
        if ev.get("stream") != HANDOFF_STREAM:
            continue
        payload = _payload_of(ev)
        handoff_id = payload.get("handoff_id") if payload is not None else None
        epoch = _iso_to_epoch(ev.get("created_at"))
        if handoff_id is None or epoch is None:
            continue
        out.append(
            HandoffLifecycleEvent(
                handoff_id=str(handoff_id),
                event_type=str(ev.get("type")),
                created_at_epoch=epoch,
            )
        )
    return out


def handoff_lifecycle(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Structural summary of the handoff lifecycle across the log.

    * ``distinct_handoffs`` — how many handoff ids appear;
    * ``created`` / ``claimed`` / ``completed`` / ``rejected`` / ``cancelled``
      — event-type counts (the lifecycle transitions);
    * ``terminal_reached`` — handoffs that hit a terminal event
      (completed/rejected/cancelled);
    * ``reclaim_cycles`` — handoffs claimed more than once (claimed, released
      via lease expiry, re-claimed) — the coordination "churn" signal.
    """
    by_handoff: dict[str, dict[str, int]] = {}
    counts = {
        EVENT_CREATED: 0,
        EVENT_CLAIMED: 0,
        EVENT_COMPLETED: 0,
        EVENT_REJECTED: 0,
        EVENT_CANCELLED: 0,
    }
    for ev in _handoff_lifecycle_events(events):
        slot = by_handoff.setdefault(ev.handoff_id, {})
        slot[ev.event_type] = slot.get(ev.event_type, 0) + 1
        if ev.event_type in counts:
            counts[ev.event_type] += 1
    terminal_reached = sum(
        1
        for slot in by_handoff.values()
        if any(slot.get(t, 0) > 0 for t in _TERMINAL_HANDOFF_EVENTS)
    )
    reclaim_cycles = sum(
        1 for slot in by_handoff.values() if slot.get(EVENT_CLAIMED, 0) > 1
    )
    return {
        "distinct_handoffs": len(by_handoff),
        "created": counts[EVENT_CREATED],
        "claimed": counts[EVENT_CLAIMED],
        "completed": counts[EVENT_COMPLETED],
        "rejected": counts[EVENT_REJECTED],
        "cancelled": counts[EVENT_CANCELLED],
        "terminal_reached": terminal_reached,
        "reclaim_cycles": reclaim_cycles,
    }


def claim_to_complete_latencies(
    events: Sequence[Mapping[str, Any]],
) -> list[float]:
    """Durations (seconds, rounded to 1 decimal) of COMPLETE claimed->completed
    pairs, correlated per handoff by the I7 rule — sorted for determinism."""
    durations = correlate_claim_to_complete(_handoff_lifecycle_events(events))
    return sorted(round(d, 1) for d in durations)


def message_fanout(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Fan-out breadth of the messages in the log, by target STRATEGY.

    The event payload carries the target descriptor echo (``target.strategy``)
    but never a delivered count, so the faithful signal is HOW BROADLY each
    message targeted: ``{"total_messages": N, "by_strategy": {direct: .., ...}}``
    (strategies key-sorted).
    """
    by_strategy: dict[str, int] = {}
    total = 0
    for ev in events:
        if str(ev.get("type")) != _MESSAGE_CREATED:
            continue
        total += 1
        payload = _payload_of(ev)
        target = payload.get("target") if payload is not None else None
        strategy = (
            str(target.get("strategy"))
            if isinstance(target, Mapping) and target.get("strategy") is not None
            else "unknown"
        )
        by_strategy[strategy] = by_strategy.get(strategy, 0) + 1
    return {"total_messages": total, "by_strategy": dict(sorted(by_strategy.items()))}


def coordination_invariants(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Assemble the full V1 invariant set — deterministic and structural.

    Compared field-by-field by an eval (never a payload snapshot), so volatile
    ids/timestamps inside payloads never cause a false regression. Aggregates
    (total, event_id range, distinct actors) frame the per-dimension breakdowns.
    """
    event_ids = [ev.get("event_id") for ev in events if ev.get("event_id") is not None]
    return {
        "total_events": len(events),
        "event_id_min": min(event_ids) if event_ids else None,
        "event_id_max": max(event_ids) if event_ids else None,
        "distinct_actors": len(actor_activity(events)),
        "event_type_histogram": event_type_histogram(events),
        "stream_histogram": stream_histogram(events),
        "actor_activity": actor_activity(events),
        "handoff_lifecycle": handoff_lifecycle(events),
        "claim_to_complete_latencies": claim_to_complete_latencies(events),
        "message_fanout": message_fanout(events),
    }
