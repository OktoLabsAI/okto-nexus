"""Coordination-health domain core (spec 7df9b1e0, I7).

Pure computation behind the ``coordination_health`` MCP tool and the
``GET /api/v1/workspaces/{id}/health`` REST read: given pre-fetched inputs and
an explicit ``now_epoch``, :func:`compute_health` assembles the ENTIRE payload
deterministically - both adapters share it, so tool/REST parity holds by
construction (same shape, same numbers).

Strictly side-effect-free and stdlib-only (import boundary test): no SQL and
no clock reads here - the application layer fetches the rows and injects the
instant.

Design locks honoured:

* Windows are a CLOSED enum (:data:`HEALTH_WINDOWS`) - the SINGLE source both
  the tool and the REST route validate against, fail-closed. Every window
  fits inside the 30-day event retention, so event-derived metrics never read
  past pruned history.
* Claim->complete durations are DERIVED BY EVENT CORRELATION per handoff_id
  (dec_e7bd8ac7): handoff rows keep no claimed_at/completed_at - every
  transition overwrites the same ``updated_at`` - so the events are the only
  faithful record. Only pairs whose claimed AND completed events BOTH fall
  inside the scanned window count; incomplete pairs are EXCLUDED, never
  approximated.
* Thresholds are FIXED V1 constants (:data:`DEFAULT_THRESHOLDS`) and are
  ALWAYS echoed in the payload, so the dashboard renders them from the
  response and never hardcodes a copy.
* Warn boundary: a value EQUAL to its threshold is ``ok``; only STRICTLY
  above warns. Volumes are informative (never warn); a null average is
  ``ok``; the rejection rate may warn only with at least
  :data:`REJECTION_MIN_CREATED` creations in the window; ``stale`` agents
  warn, ``offline`` never does (absence is normal, staleness is a smell).
* Determinism residuals fixed HERE (gate ambiguity closeout): durations and
  ages round to 1 decimal, the rejection rate to 4; the per-agent breakdown
  orders by unread DESC then agent_id ASC; ``others_unread`` is always
  present (0 when nothing folds).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .handoff import EVENT_CLAIMED, EVENT_COMPLETED, EVENT_CREATED, EVENT_REJECTED

#: window label -> span in seconds. CLOSED enum (fail-closed validation on
#: both adapters); the max span (7d) stays well inside the 30-day default
#: event retention, so correlation never reads a pruned window.
HEALTH_WINDOWS: dict[str, int] = {
    "1h": 3_600,
    "24h": 86_400,
    "7d": 604_800,
}

#: The default window when the caller does not specify one.
DEFAULT_WINDOW = "24h"

#: Fixed V1 thresholds (5 keys, ALWAYS echoed in the payload). Not
#: configurable in V1 - a future opt-in can widen this without changing the
#: payload shape, because consumers already read thresholds from the response.
DEFAULT_THRESHOLDS: dict[str, int | float] = {
    "unclaimed_handoff_age_seconds": 1800,
    "avg_claim_to_complete_seconds": 3600,
    "rejection_rate": 0.25,
    "per_agent_unread": 25,
    "stale_agents": 0,
}

#: Minimum ``handoff.created`` events in the window before the rejection rate
#: may warn - below this the sample is too small to be a signal.
REJECTION_MIN_CREATED = 4

#: Per-agent inbox breakdown cap: the top-N agents by unread count; everyone
#: else folds into the ``others_unread`` aggregate.
PER_AGENT_TOP = 20


def is_valid_window(window: Any) -> bool:
    """Whether ``window`` is a supported label (single enum source for both
    the tool's VALIDATION_ERROR and the route's INVALID_WINDOW)."""
    return window in HEALTH_WINDOWS


@dataclass(frozen=True)
class HandoffLifecycleEvent:
    """One windowed ``handoff.*`` event, already parsed by the caller."""

    handoff_id: str
    event_type: str
    created_at_epoch: float


@dataclass(frozen=True)
class UnclaimedHandoff:
    """One OPEN handoff snapshot row - the creation instant is all age needs."""

    handoff_id: str
    created_at_epoch: float


@dataclass(frozen=True)
class AgentUnread:
    """One agent's unread delivery count in THIS workspace (snapshot)."""

    agent_id: str
    unread: int


@dataclass(frozen=True)
class PresenceCounts:
    """Read-time presence buckets (``classify_presence`` output, aggregated)."""

    present: int = 0
    stale: int = 0
    offline: int = 0


@dataclass(frozen=True)
class HealthInputs:
    """Everything :func:`compute_health` needs, pre-fetched by the caller."""

    workspace_id: str
    window: str
    message_count: int
    event_count: int
    lifecycle_events: Sequence[HandoffLifecycleEvent]
    lifecycle_truncated: bool
    unclaimed: Sequence[UnclaimedHandoff]
    unread: Sequence[AgentUnread]
    presence: PresenceCounts


def _epoch_to_iso(epoch: float) -> str:
    """Render an epoch as the canonical fixed-width UTC ISO string."""
    return (
        datetime.fromtimestamp(epoch, timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _threshold_status(value: float | None, threshold: float) -> str:
    """Derive ok|warn: ``None`` and ``value == threshold`` are ok; only
    STRICTLY above the threshold warns."""
    if value is None:
        return "ok"
    return "warn" if value > threshold else "ok"


def correlate_claim_to_complete(
    events: Sequence[HandoffLifecycleEvent],
) -> list[float]:
    """Durations of COMPLETE claimed->completed pairs, correlated per handoff.

    For each handoff whose window slice carries BOTH events, the duration is
    ``earliest completed - latest claimed at or before it`` (a handoff may be
    claimed, released and re-claimed; the claim that produced the completion
    is the last one). A handoff missing either side inside the window (e.g.
    claimed before the window opened) is an INCOMPLETE pair and is excluded -
    excluded, never approximated (dec_e7bd8ac7).
    """
    by_handoff: dict[str, dict[str, list[float]]] = {}
    for ev in events:
        by_handoff.setdefault(ev.handoff_id, {}).setdefault(ev.event_type, []).append(
            ev.created_at_epoch
        )
    durations: list[float] = []
    for slots in by_handoff.values():
        completed = slots.get(EVENT_COMPLETED)
        claimed = slots.get(EVENT_CLAIMED)
        if not completed or not claimed:
            continue
        done_at = min(completed)
        candidates = [c for c in claimed if c <= done_at]
        if not candidates:
            continue
        durations.append(done_at - max(candidates))
    return durations


def compute_health(inputs: HealthInputs, *, now_epoch: float) -> dict[str, Any]:
    """Assemble the FULL coordination-health payload from pre-fetched inputs.

    Deterministic: the same inputs + ``now_epoch`` always yield the same
    payload (the injected instant also renders ``generated_at``). ``window``
    MUST be a :data:`HEALTH_WINDOWS` member - callers validate fail-closed
    first, so an unknown value here is a wiring bug and fails loud.
    """
    window = inputs.window
    if window not in HEALTH_WINDOWS:
        raise ValueError(f"unknown health window: {window!r}")
    thresholds = dict(DEFAULT_THRESHOLDS)

    # Windowed volumes: informative only, never warn.
    message_volume = {
        "scope": "windowed",
        "status": "ok",
        "count": int(inputs.message_count),
    }
    event_volume = {
        "scope": "windowed",
        "status": "ok",
        "count": int(inputs.event_count),
    }

    # Unclaimed handoffs (snapshot): age of the OLDEST open handoff.
    oldest_age: float | None = None
    if inputs.unclaimed:
        oldest = min(h.created_at_epoch for h in inputs.unclaimed)
        oldest_age = round(max(now_epoch - oldest, 0.0), 1)
    unclaimed_handoffs = {
        "scope": "snapshot",
        "status": _threshold_status(
            oldest_age, thresholds["unclaimed_handoff_age_seconds"]
        ),
        "count": len(inputs.unclaimed),
        "oldest_age_seconds": oldest_age,
    }

    # Handoff completion (windowed): correlated COMPLETE pairs only.
    durations = correlate_claim_to_complete(inputs.lifecycle_events)
    avg: float | None = round(sum(durations) / len(durations), 1) if durations else None
    handoff_completion = {
        "scope": "windowed",
        "status": _threshold_status(avg, thresholds["avg_claim_to_complete_seconds"]),
        "completed_pairs": len(durations),
        "avg_claim_to_complete_seconds": avg,
        "truncated": bool(inputs.lifecycle_truncated),
    }

    # Handoff rejections (windowed): plain event counts over the same scan.
    created = sum(1 for ev in inputs.lifecycle_events if ev.event_type == EVENT_CREATED)
    rejected = sum(
        1 for ev in inputs.lifecycle_events if ev.event_type == EVENT_REJECTED
    )
    rate: float | None = round(rejected / created, 4) if created else None
    rejection_status = "ok"
    if rate is not None and created >= REJECTION_MIN_CREATED:
        rejection_status = _threshold_status(rate, thresholds["rejection_rate"])
    handoff_rejections = {
        "scope": "windowed",
        "status": rejection_status,
        "created": created,
        "rejected": rejected,
        "rejection_rate": rate,
        "truncated": bool(inputs.lifecycle_truncated),
    }

    # Inbox backlog (snapshot): bounded per-agent breakdown, deterministic
    # order (unread DESC, then agent_id ASC on ties).
    ranked = sorted(inputs.unread, key=lambda row: (-row.unread, row.agent_id))
    per_agent = [
        {"agent_id": row.agent_id, "unread": int(row.unread)}
        for row in ranked[:PER_AGENT_TOP]
    ]
    others_unread = sum(int(row.unread) for row in ranked[PER_AGENT_TOP:])
    max_unread = int(ranked[0].unread) if ranked else None
    inbox_backlog = {
        "scope": "snapshot",
        "status": _threshold_status(max_unread, thresholds["per_agent_unread"]),
        "total_unread": sum(int(row.unread) for row in ranked),
        "per_agent": per_agent,
        "others_unread": others_unread,
    }

    # Agent presence (snapshot): stale warns, offline never does.
    presence = inputs.presence
    agent_presence = {
        "scope": "snapshot",
        "status": _threshold_status(int(presence.stale), thresholds["stale_agents"]),
        "present": int(presence.present),
        "stale": int(presence.stale),
        "offline": int(presence.offline),
    }

    metrics = {
        "message_volume": message_volume,
        "event_volume": event_volume,
        "unclaimed_handoffs": unclaimed_handoffs,
        "handoff_completion": handoff_completion,
        "handoff_rejections": handoff_rejections,
        "inbox_backlog": inbox_backlog,
        "agent_presence": agent_presence,
    }
    status = "warn" if any(m["status"] == "warn" for m in metrics.values()) else "ok"

    return {
        "workspace_id": inputs.workspace_id,
        "window": window,
        "window_seconds": HEALTH_WINDOWS[window],
        "generated_at": _epoch_to_iso(now_epoch),
        "status": status,
        "metrics": metrics,
        "thresholds": thresholds,
    }
