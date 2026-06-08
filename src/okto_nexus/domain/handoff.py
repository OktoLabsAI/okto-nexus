"""Pure domain logic for the handoff lifecycle slice.

This module owns the *handoff state machine* for Okto Nexus V1: the canonical
status vocabulary, the explicit V1 transition table, and the small validators
used by the application service (target descriptor + visibility + direct-target
ownership for the pre-claim reject path).

It is strictly side-effect free (stdlib + the error catalogue only) and NEVER
imports ``sqlite3`` or ``mcp`` (enforced by the import-boundary test). The
routing/eligibility decisions themselves live in
:mod:`okto_nexus.domain.routing` (imported by the application layer); this
module only validates the *shape* of a target descriptor at creation time.

State machine (V1)::

    (none)   --handoff_create-->            OPEN
    OPEN     --handoff_claim-->             CLAIMED
    OPEN     --handoff_reject (direct)-->   REJECTED
    CLAIMED  --handoff_complete (owner)-->  COMPLETED
    CLAIMED  --handoff_reject (owner)-->    REJECTED
    CLAIMED  --expire_old_leases-->         OPEN

``IN_PROGRESS``, ``BLOCKED``, ``CANCELLED`` and ``EXPIRED`` are reserved
forward-compatible names with NO producer in V1. ``COMPLETED`` and ``REJECTED``
are terminal. Any transition outside the table is an ``INVALID_TRANSITION``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from ..errors import ErrorCode, OktoNexusError

__all__ = [
    "STATUS_OPEN",
    "STATUS_CLAIMED",
    "STATUS_COMPLETED",
    "STATUS_REJECTED",
    "RESERVED_STATUSES",
    "TERMINAL_STATUSES",
    "V1_STATUSES",
    "ALL_STATUSES",
    "VALID_STRATEGIES",
    "VALID_VISIBILITIES",
    "HANDOFF_STREAM",
    "EVENT_CREATED",
    "EVENT_CLAIMED",
    "EVENT_COMPLETED",
    "EVENT_REJECTED",
    "EVENT_EXPIRED",
    "validate_target",
    "normalize_visibility",
    "normalize_strategy",
    "is_direct_target",
    "can_transition",
]


# --------------------------------------------------------------------------- #
# Status vocabulary
# --------------------------------------------------------------------------- #
STATUS_OPEN = "OPEN"
STATUS_CLAIMED = "CLAIMED"
STATUS_COMPLETED = "COMPLETED"
STATUS_REJECTED = "REJECTED"

#: Reserved forward-compatible statuses with NO producer in V1.
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_BLOCKED = "BLOCKED"
STATUS_CANCELLED = "CANCELLED"
STATUS_EXPIRED = "EXPIRED"

RESERVED_STATUSES: frozenset[str] = frozenset(
    {STATUS_IN_PROGRESS, STATUS_BLOCKED, STATUS_CANCELLED, STATUS_EXPIRED}
)
TERMINAL_STATUSES: frozenset[str] = frozenset({STATUS_COMPLETED, STATUS_REJECTED})
V1_STATUSES: frozenset[str] = frozenset(
    {STATUS_OPEN, STATUS_CLAIMED, STATUS_COMPLETED, STATUS_REJECTED}
)
ALL_STATUSES: frozenset[str] = V1_STATUSES | RESERVED_STATUSES


# --------------------------------------------------------------------------- #
# Target / visibility vocabularies (mirrors routing)
# --------------------------------------------------------------------------- #
VALID_STRATEGIES: frozenset[str] = frozenset(
    {
        "direct",
        "capability",
        "role",
        "broadcast",
        "mixed",
        "direct_with_fallback",
    }
)

VALID_VISIBILITIES: frozenset[str] = frozenset({"private", "eligible", "public"})

#: Required descriptor fields per strategy (after normalisation).
_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "direct": ("agent_id",),
    "direct_with_fallback": ("agent_id", "fallback_after_seconds"),
    "capability": ("capability",),
    "role": ("role",),
    "broadcast": (),
    "mixed": ("rules",),
}


# --------------------------------------------------------------------------- #
# Event vocabulary (the Event Log owns event_id assignment; we only name them)
# --------------------------------------------------------------------------- #
HANDOFF_STREAM = "handoff"
EVENT_CREATED = "handoff.created"
EVENT_CLAIMED = "handoff.claimed"
EVENT_COMPLETED = "handoff.completed"
EVENT_REJECTED = "handoff.rejected"
EVENT_EXPIRED = "handoff.expired"


# --------------------------------------------------------------------------- #
# Explicit V1 transition table (structural guard)
# --------------------------------------------------------------------------- #
_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (STATUS_OPEN, STATUS_CLAIMED),
        (STATUS_OPEN, STATUS_REJECTED),
        (STATUS_CLAIMED, STATUS_COMPLETED),
        (STATUS_CLAIMED, STATUS_REJECTED),
        (STATUS_CLAIMED, STATUS_OPEN),
    }
)


def can_transition(src: str | None, dst: str) -> bool:
    """Return whether ``src -> dst`` is a permitted V1 lifecycle transition.

    ``src`` of ``None``/``""`` models creation (``-> OPEN``). Terminal states
    (``COMPLETED``/``REJECTED``) never permit a further transition.
    """
    if src is None or src == "":
        return dst == STATUS_OPEN
    return (src, dst) in _TRANSITIONS


# --------------------------------------------------------------------------- #
# Validators
# --------------------------------------------------------------------------- #
def normalize_strategy(raw: Any) -> str:
    """Normalise + validate a strategy token (case-insensitive, ``-``/space -> ``_``).

    Raises ``VALIDATION_ERROR`` for an unknown strategy.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "Target is missing the 'strategy' discriminator.",
            {"strategy": raw},
        )
    token = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    if token not in VALID_STRATEGIES:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"Unknown routing strategy: {raw!r}.",
            {"strategy": raw, "supported": sorted(VALID_STRATEGIES)},
        )
    return token


def normalize_visibility(raw: Any) -> str:
    """Normalise + validate a visibility token (case-insensitive).

    Unlike routing's read-time default, ``handoff_create`` REQUIRES an explicit,
    valid visibility: a missing/blank/unknown value raises ``VALIDATION_ERROR``.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "visibility is required and must be one of "
            f"{sorted(VALID_VISIBILITIES)}.",
            {"visibility": raw},
        )
    token = str(raw).strip().lower()
    if token not in VALID_VISIBILITIES:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"Unknown visibility: {raw!r}.",
            {"visibility": raw, "supported": sorted(VALID_VISIBILITIES)},
        )
    return token


def _coerce_target(target: Any) -> Mapping[str, Any]:
    """Return ``target`` as a mapping (parsing a JSON-object string if needed).

    Raises ``VALIDATION_ERROR`` for a missing/blank target or one that does not
    resolve to a JSON object (a handoff always carries an explicit routing rule).
    """
    if target is None or (isinstance(target, str) and not target.strip()):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "target descriptor is required.",
            {"target": target},
        )
    if isinstance(target, Mapping):
        return target
    if isinstance(target, str):
        try:
            parsed = json.loads(target)
        except (ValueError, TypeError):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "target string is not valid JSON.",
                {"target": target},
            ) from None
        if isinstance(parsed, Mapping):
            return parsed
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "target JSON must be an object.",
            {"target": target},
        )
    raise OktoNexusError(
        ErrorCode.VALIDATION_ERROR,
        "target must be a mapping, a JSON object string, or null.",
        {"target_type": type(target).__name__},
    )


def validate_target(target: Any) -> dict[str, Any]:
    """Validate a target descriptor and return it as a plain ``dict``.

    Checks that the ``strategy`` discriminator is one of
    :data:`VALID_STRATEGIES` and that the per-strategy required fields are
    present and non-empty. Does NOT decide eligibility (that is routing's job at
    claim/list time); it only guarantees a well-formed descriptor for storage.

    Raises ``VALIDATION_ERROR`` for any structural problem.
    """
    resolved = _coerce_target(target)
    strategy = normalize_strategy(resolved.get("strategy", resolved.get("kind")))

    for field in _REQUIRED_FIELDS[strategy]:
        value = resolved.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"target strategy {strategy!r} requires field {field!r}.",
                {"strategy": strategy, "missing_field": field},
            )

    if strategy == "mixed":
        rules = resolved.get("rules", resolved.get("targets"))
        if not isinstance(rules, Sequence) or isinstance(rules, (str, bytes)) or not rules:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "mixed target requires a non-empty 'rules' list of sub-targets.",
                {"strategy": strategy},
            )

    if strategy == "direct_with_fallback":
        after = resolved.get("fallback_after_seconds")
        if isinstance(after, bool) or not isinstance(after, (int, float)) or after < 0:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "fallback_after_seconds must be a non-negative number.",
                {"fallback_after_seconds": after},
            )

    out = dict(resolved)
    out["strategy"] = strategy
    return out


def is_direct_target(target: Any, agent_id: str) -> bool:
    """Return whether ``agent_id`` is the *direct* named recipient of ``target``.

    Used by the pre-claim reject path (a ``direct`` target may reject an OPEN
    handoff before claiming it). Only the ``direct`` strategy qualifies; any
    malformed/other descriptor returns ``False`` (never raises).
    """
    if not agent_id:
        return False
    try:
        resolved = _coerce_target(target)
    except OktoNexusError:
        return False
    raw_strategy = resolved.get("strategy", resolved.get("kind"))
    if raw_strategy is None:
        return False
    token = str(raw_strategy).strip().lower().replace("-", "_").replace(" ", "_")
    if token != "direct":
        return False
    return str(resolved.get("agent_id")) == str(agent_id)
