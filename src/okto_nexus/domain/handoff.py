"""Pure domain logic for the handoff lifecycle slice.

This module owns the *handoff state machine* for Okto Nexus V1: the canonical
status vocabulary, the explicit V1 transition table, and the small validators
used by the application service (target descriptor + visibility + direct-target
ownership for the pre-claim reject path).

It is strictly side-effect free (stdlib + the error catalogue only) and NEVER
imports ``sqlite3`` or ``mcp`` (enforced by the import-boundary test). The
routing/eligibility decisions themselves live in
:mod:`okto_nexus.domain.routing` (imported by the application layer), and the
target GRAMMAR (parse + exhaustive validation) is IMPORTED from
:mod:`okto_nexus.domain.targets` - the single shared definition; this module
only adds the handoff-specific requirement that a descriptor is mandatory.

State machine (V1)::

    (none)   --handoff_create-->            OPEN
    OPEN     --handoff_claim-->             CLAIMED
    OPEN     --handoff_reject (direct)-->   REJECTED
    OPEN     --handoff_cancel (creator)-->  CANCELLED
    CLAIMED  --handoff_complete (owner)-->  COMPLETED
    CLAIMED  --handoff_reject (owner)-->    REJECTED
    CLAIMED  --expire_old_leases-->         OPEN

``IN_PROGRESS``, ``BLOCKED`` and ``EXPIRED`` are reserved forward-compatible
names with NO producer in V1. ``COMPLETED``, ``REJECTED`` and ``CANCELLED``
are terminal. Any transition outside the table is an ``INVALID_TRANSITION``.
"""

from __future__ import annotations

from typing import Any

from ..errors import ErrorCode, OktoNexusError
from .targets import (
    VALID_STRATEGIES,
    is_direct_target,
    normalize_strategy,
)
from .targets import validate_target as _validate_target_grammar

__all__ = [
    "STATUS_OPEN",
    "STATUS_CLAIMED",
    "STATUS_COMPLETED",
    "STATUS_REJECTED",
    "STATUS_CANCELLED",
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
    "EVENT_CANCELLED",
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
STATUS_CANCELLED = "CANCELLED"

#: Reserved forward-compatible statuses with NO producer in V1.
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_BLOCKED = "BLOCKED"
STATUS_EXPIRED = "EXPIRED"

RESERVED_STATUSES: frozenset[str] = frozenset(
    {STATUS_IN_PROGRESS, STATUS_BLOCKED, STATUS_EXPIRED}
)
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {STATUS_COMPLETED, STATUS_REJECTED, STATUS_CANCELLED}
)
V1_STATUSES: frozenset[str] = frozenset(
    {STATUS_OPEN, STATUS_CLAIMED, STATUS_COMPLETED, STATUS_REJECTED, STATUS_CANCELLED}
)
ALL_STATUSES: frozenset[str] = V1_STATUSES | RESERVED_STATUSES


# --------------------------------------------------------------------------- #
# Visibility vocabulary (the strategies live in domain.targets, re-exported)
# --------------------------------------------------------------------------- #
VALID_VISIBILITIES: frozenset[str] = frozenset({"private", "eligible", "public"})


# --------------------------------------------------------------------------- #
# Event vocabulary (the Event Log owns event_id assignment; we only name them)
# --------------------------------------------------------------------------- #
HANDOFF_STREAM = "handoff"
EVENT_CREATED = "handoff.created"
EVENT_CLAIMED = "handoff.claimed"
EVENT_COMPLETED = "handoff.completed"
EVENT_REJECTED = "handoff.rejected"
EVENT_CANCELLED = "handoff.cancelled"
EVENT_EXPIRED = "handoff.expired"


# --------------------------------------------------------------------------- #
# Explicit V1 transition table (structural guard)
# --------------------------------------------------------------------------- #
_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (STATUS_OPEN, STATUS_CLAIMED),
        (STATUS_OPEN, STATUS_REJECTED),
        (STATUS_OPEN, STATUS_CANCELLED),
        (STATUS_CLAIMED, STATUS_COMPLETED),
        (STATUS_CLAIMED, STATUS_REJECTED),
        (STATUS_CLAIMED, STATUS_OPEN),
    }
)


def can_transition(src: str | None, dst: str) -> bool:
    """Return whether ``src -> dst`` is a permitted V1 lifecycle transition.

    ``src`` of ``None``/``""`` models creation (``-> OPEN``). Terminal states
    (``COMPLETED``/``REJECTED``/``CANCELLED``) never permit a further
    transition.
    """
    if src is None or src == "":
        return dst == STATUS_OPEN
    return (src, dst) in _TRANSITIONS


# --------------------------------------------------------------------------- #
# Validators
# --------------------------------------------------------------------------- #
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


def validate_target(target: Any) -> dict[str, Any]:
    """Validate a target descriptor and return it as a plain ``dict``.

    Delegates the full grammar (known strategies, per-strategy required fields,
    recursive ``mixed``/``fallback`` validation) to the SINGLE definition in
    :func:`okto_nexus.domain.targets.validate_target`, with the handoff-specific
    rule that a descriptor is REQUIRED (a handoff always carries an explicit
    routing rule). Does NOT decide eligibility (that is routing's job at
    claim/list time); it only guarantees a well-formed descriptor for storage.

    Raises ``VALIDATION_ERROR`` for any structural problem.
    """
    validated = _validate_target_grammar(target, required=True)
    assert validated is not None  # required=True never returns None
    return validated
