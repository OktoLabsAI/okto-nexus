"""Pure domain helpers for the Event Log slice.

This module owns the *pure* (IO-free, stdlib-only) rules that govern how the
append-only event log is consumed by ``event_get`` / ``event_wait``:

* the closed set of consumable ``stream`` values (workspace / agent / task /
  handoff) and its validation (:func:`validate_stream` -> ``INVALID_STREAM``);
* input normalisation for ``cursor`` (non-negative INTEGER), ``limit`` (clamped
  to a configured maximum) and ``filters`` (an object with the enumerated keys
  ``type`` / ``agent_id`` / ``task_id`` / ``handoff_id``);
* the *equality-AND* filter predicate (:func:`event_matches_filters`) and the
  response serialisation of an :class:`~okto_nexus.domain.models.Event`.

It never imports ``sqlite3`` nor ``mcp`` (enforced by the import-boundary test)
and never performs IO; visibility (``can_agent_see_event``) lives in
:mod:`okto_nexus.domain.routing` and is layered on top by the application
service. Malformed inputs raise :class:`OktoNexusError` with the canonical
catalogue codes so callers never have to special-case them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors import ErrorCode, OktoNexusError
from .models import Event

__all__ = [
    "VALID_STREAMS",
    "FILTER_KEYS",
    "validate_stream",
    "normalize_cursor",
    "clamp_limit",
    "normalize_filters",
    "event_matches_filters",
    "event_to_dict",
]

#: The closed domain of consumable streams. Streams are *semantic filters* over
#: a single global log, not physical partitions.
VALID_STREAMS: frozenset[str] = frozenset({"workspace", "agent", "task", "handoff"})

#: The closed set of enumerated filter keys (equality, combined with AND).
FILTER_KEYS: frozenset[str] = frozenset({"type", "agent_id", "task_id", "handoff_id"})


def validate_stream(stream: Any) -> str:
    """Return ``stream`` if it is one of :data:`VALID_STREAMS`.

    Raises ``INVALID_STREAM`` (canonical code) for any other value, BEFORE any
    scan of the log is performed (the caller must invoke this first).
    """
    if isinstance(stream, str) and stream in VALID_STREAMS:
        return stream
    raise OktoNexusError(
        ErrorCode.INVALID_STREAM,
        "stream must be one of {agent, handoff, task, workspace}.",
        {"stream": stream, "supported": sorted(VALID_STREAMS)},
    )


def normalize_cursor(cursor: Any) -> int:
    """Coerce ``cursor`` to a non-negative INTEGER (``None`` -> ``0``).

    ``cursor`` is the *last consumed* ``event_id``; the scan selects
    ``event_id > cursor``. A non-integer (``bool`` is rejected explicitly, as it
    is an ``int`` subclass) or a negative value raises ``VALIDATION_ERROR``.
    """
    if cursor is None:
        return 0
    if isinstance(cursor, bool) or not isinstance(cursor, int):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "cursor must be a non-negative integer.",
            {"cursor": cursor},
        )
    if cursor < 0:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "cursor must be a non-negative integer.",
            {"cursor": cursor},
        )
    return cursor


def clamp_limit(limit: Any, *, default: int, maximum: int) -> int:
    """Resolve the page size: ``None`` -> ``default``, then clamp to ``maximum``.

    A non-integer (``bool`` rejected) or a value ``< 1`` raises
    ``VALIDATION_ERROR``. Values above ``maximum`` are clamped to ``maximum``.
    """
    if limit is None:
        return min(default, maximum)
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "limit must be a positive integer.",
            {"limit": limit},
        )
    if limit < 1:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "limit must be a positive integer.",
            {"limit": limit},
        )
    return min(limit, maximum)


def normalize_filters(filters: Any) -> dict[str, str]:
    """Validate and normalise the ``filters`` object.

    ``None`` -> ``{}``. ``filters`` must be a mapping whose keys are a subset of
    :data:`FILTER_KEYS`; keys mapped to ``None`` are dropped (no constraint).
    Any unknown key, or a non-mapping value, raises ``VALIDATION_ERROR``. The
    remaining values are coerced to ``str`` for exact-equality matching.
    """
    if filters is None:
        return {}
    if not isinstance(filters, Mapping):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "filters must be an object with keys in "
            "{type, agent_id, task_id, handoff_id}.",
            {"filters_type": type(filters).__name__},
        )
    normalized: dict[str, str] = {}
    for key, value in filters.items():
        if key not in FILTER_KEYS:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"Unknown filter key: {key!r}.",
                {"filter_key": key, "supported": sorted(FILTER_KEYS)},
            )
        if value is None:
            continue
        normalized[str(key)] = str(value)
    return normalized


def _event_filter_value(event: Event, key: str) -> Any:
    """Return the value an :class:`Event` exposes for filter ``key``.

    ``type`` / ``agent_id`` map to columns (``type`` / ``actor_agent_id``);
    ``task_id`` / ``handoff_id`` are read from the event ``payload`` (they are
    not first-class columns in V1).
    """
    if key == "type":
        return event.type
    if key == "agent_id":
        return event.actor_agent_id
    payload = event.payload if isinstance(event.payload, Mapping) else None
    if payload is None:
        return None
    return payload.get(key)


def event_matches_filters(event: Event, filters: Mapping[str, str]) -> bool:
    """Return whether ``event`` matches every filter (equality, AND-combined).

    An event matches iff, for each provided key, its corresponding value equals
    the filter value (compared as strings). Empty ``filters`` matches every
    event.
    """
    for key, wanted in filters.items():
        actual = _event_filter_value(event, key)
        if actual is None or str(actual) != str(wanted):
            return False
    return True


def event_to_dict(event: Event) -> dict[str, Any]:
    """Serialise an :class:`Event` to the canonical ``event_get`` payload shape.

    ``task_id`` / ``handoff_id`` are surfaced from the ``payload`` (or ``None``).
    """
    payload = event.payload if isinstance(event.payload, Mapping) else None
    return {
        "event_id": event.event_id,
        "workspace_id": event.workspace_id,
        "stream": event.stream,
        "type": event.type,
        "payload": dict(payload) if payload is not None else event.payload,
        "actor_agent_id": event.actor_agent_id,
        "task_id": payload.get("task_id") if payload is not None else None,
        "handoff_id": payload.get("handoff_id") if payload is not None else None,
        "created_at": event.created_at,
    }
