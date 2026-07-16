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

State machine (V1 + verification)::

    (none)    --handoff_create-->                    OPEN
    OPEN      --handoff_claim-->                     CLAIMED
    OPEN      --handoff_reject (direct)-->           REJECTED
    OPEN      --handoff_cancel (creator)-->          CANCELLED
    CLAIMED   --handoff_complete (owner)-->          COMPLETED
    CLAIMED   --handoff_complete (with criteria)-->  VERIFYING
    CLAIMED   --handoff_reject (owner)-->            REJECTED
    CLAIMED   --expire_old_leases-->                 OPEN
    VERIFYING --handoff_verify pass-->               COMPLETED
    VERIFYING --handoff_verify fail-->               CLAIMED

``IN_PROGRESS``, ``BLOCKED`` and ``EXPIRED`` are reserved forward-compatible
names with NO producer. ``COMPLETED``, ``REJECTED`` and ``CANCELLED`` are
terminal; ``VERIFYING`` is NOT terminal and only the verify verb leaves it
(cancel/reject are invalid there and lease expiry never touches it). Any
transition outside the table is an ``INVALID_TRANSITION``.

Dependencies (I5, ``depends_on``) deliberately add NO status: a handoff whose
dependencies are not yet satisfied REMAINS ``OPEN`` and its blocked-ness is
derived on-read from the dependency rows (``BLOCKED`` stays reserved with no
producer). Satisfaction is STRICT ``COMPLETED`` - ``VERIFYING`` does not
satisfy (a delivered-but-unjudged dependency is not done). ``REJECTED`` and
``CANCELLED`` dependencies are permanently failed: the dependent is retained
(never cascaded) and needs manual intervention.

This module also owns the verification-contract grammar (acceptance
criteria + verify_by descriptor) and the PURE verifier-eligibility rule with
its non-negotiable core: the executor (``claimed_by``) can never verify their
own delivery, even when the resolved verifier would otherwise include them.
The ``depends_on`` grammar and the pure dependency-satisfaction evaluator
live here too; id EXISTENCE (same workspace) is the application layer's gate.
"""

from __future__ import annotations

from collections.abc import Iterable
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
    "STATUS_VERIFYING",
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
    "EVENT_VERIFICATION_REQUESTED",
    "EVENT_VERIFICATION_FAILED",
    "EVENT_UNBLOCKED",
    "EVENT_DEPENDENCY_FAILED",
    "MAX_DEPENDENCIES",
    "DEPENDENCY_SATISFYING_STATUSES",
    "DEPENDENCY_FAILED_STATUSES",
    "MAX_ACCEPTANCE_CRITERIA",
    "MAX_CRITERION_LENGTH",
    "MAX_VERIFICATION_FEEDBACK_LENGTH",
    "VERDICT_PASS",
    "VERDICT_FAIL",
    "VALID_VERDICTS",
    "VERIFY_BY_KINDS",
    "validate_target",
    "normalize_visibility",
    "normalize_strategy",
    "is_direct_target",
    "can_transition",
    "validate_depends_on",
    "summarize_dependencies",
    "dependencies_satisfied",
    "validate_acceptance_criteria",
    "validate_verify_by",
    "validate_verdict",
    "is_eligible_verifier",
    "static_verifier_for",
    "is_degenerate_self_claim",
]


# --------------------------------------------------------------------------- #
# Status vocabulary
# --------------------------------------------------------------------------- #
STATUS_OPEN = "OPEN"
STATUS_CLAIMED = "CLAIMED"
STATUS_VERIFYING = "VERIFYING"
STATUS_COMPLETED = "COMPLETED"
STATUS_REJECTED = "REJECTED"
STATUS_CANCELLED = "CANCELLED"

#: Reserved forward-compatible statuses with NO producer.
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
    {
        STATUS_OPEN,
        STATUS_CLAIMED,
        STATUS_VERIFYING,
        STATUS_COMPLETED,
        STATUS_REJECTED,
        STATUS_CANCELLED,
    }
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
#: Verification adds exactly TWO event types. A verify "pass" does NOT get its
#: own event: it emits the canonical EVENT_COMPLETED enriched with
#: ``verified_by`` so consumers keep a single terminal signal.
EVENT_VERIFICATION_REQUESTED = "handoff.verification_requested"
EVENT_VERIFICATION_FAILED = "handoff.verification_failed"
#: Dependencies (I5) add exactly TWO event types. ``handoff.unblocked`` fires
#: exactly once per dependent, when its LAST dependency reaches COMPLETED
#: (actor = whoever completed; the event rides the DEPENDENT's trace).
#: ``handoff.dependency_failed`` fires when a dependency lands REJECTED or
#: CANCELLED - the dependent is retained, never cascaded.
EVENT_UNBLOCKED = "handoff.unblocked"
EVENT_DEPENDENCY_FAILED = "handoff.dependency_failed"


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
        # Verification (I4): only the verify verb leaves VERIFYING.
        (STATUS_CLAIMED, STATUS_VERIFYING),
        (STATUS_VERIFYING, STATUS_COMPLETED),
        (STATUS_VERIFYING, STATUS_CLAIMED),
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
            f"visibility is required and must be one of {sorted(VALID_VISIBILITIES)}.",
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


# --------------------------------------------------------------------------- #
# Verification contract (I4) - grammar + pure eligibility
# --------------------------------------------------------------------------- #
MAX_ACCEPTANCE_CRITERIA = 20
MAX_CRITERION_LENGTH = 500
MAX_VERIFICATION_FEEDBACK_LENGTH = 2000

VERDICT_PASS = "pass"
VERDICT_FAIL = "fail"
VALID_VERDICTS: frozenset[str] = frozenset({VERDICT_PASS, VERDICT_FAIL})

VERIFY_BY_KINDS: frozenset[str] = frozenset({"creator", "agent", "capability"})


def validate_acceptance_criteria(raw: Any) -> list[str]:
    """Validate + normalise an acceptance-criteria list (fail-closed).

    Grammar: a JSON list of 1..MAX_ACCEPTANCE_CRITERIA strings, each non-empty
    after strip and at most MAX_CRITERION_LENGTH chars, with NO exact
    duplicates (a duplicate is a caller mistake, never silently deduped).
    Order is preserved; items are returned stripped. An empty list is invalid:
    callers that do not want verification OMIT the parameter entirely.
    """
    if not isinstance(raw, (list, tuple)):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "acceptance_criteria must be a list of non-empty strings.",
            {"acceptance_criteria": raw},
        )
    if len(raw) == 0:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "acceptance_criteria cannot be empty - omit the parameter when no "
            "verification is wanted.",
            {"acceptance_criteria": []},
        )
    if len(raw) > MAX_ACCEPTANCE_CRITERIA:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"acceptance_criteria accepts at most {MAX_ACCEPTANCE_CRITERIA} "
            f"items (got {len(raw)}).",
            {"count": len(raw), "max": MAX_ACCEPTANCE_CRITERIA},
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"acceptance_criteria[{index}] must be a non-empty string.",
                {"index": index, "item": item},
            )
        criterion = item.strip()
        if len(criterion) > MAX_CRITERION_LENGTH:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"acceptance_criteria[{index}] exceeds "
                f"{MAX_CRITERION_LENGTH} characters.",
                {"index": index, "length": len(criterion)},
            )
        if criterion in seen:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"acceptance_criteria[{index}] is an exact duplicate.",
                {"index": index, "item": criterion},
            )
        seen.add(criterion)
        normalized.append(criterion)
    return normalized


def validate_verify_by(raw: Any) -> dict[str, str]:
    """Validate + normalise a verify_by descriptor (fail-closed grammar).

    Exactly three forms are accepted - any unknown ``kind``, missing value or
    EXTRA field is rejected (never accept-and-ignore a verification contract)::

        {"kind": "creator"}
        {"kind": "agent", "agent_id": "<id>"}
        {"kind": "capability", "capability": "<name>"}

    EXISTENCE of the agent / catalog capability is the application layer's
    fail-closed gate (it needs I/O); this validator owns only the shape.
    """

    def _bad(message: str) -> OktoNexusError:
        return OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{message} Supported forms: {{'kind': 'creator'}}, "
            "{'kind': 'agent', 'agent_id': ...}, "
            "{'kind': 'capability', 'capability': ...}.",
            {"verify_by": raw},
        )

    if not isinstance(raw, dict):
        raise _bad("verify_by must be an object.")
    kind_raw = raw.get("kind")
    if not isinstance(kind_raw, str) or kind_raw.strip().lower() not in VERIFY_BY_KINDS:
        raise _bad(f"Unknown verify_by kind: {kind_raw!r}.")
    kind = kind_raw.strip().lower()
    value_field = {"creator": None, "agent": "agent_id", "capability": "capability"}[
        kind
    ]
    allowed_keys = {"kind"} | ({value_field} if value_field else set())
    extra = set(raw) - allowed_keys
    if extra:
        raise _bad(f"verify_by has unsupported field(s): {sorted(extra)}.")
    if value_field is None:
        return {"kind": kind}
    value = raw.get(value_field)
    if not isinstance(value, str) or not value.strip():
        raise _bad(f"verify_by kind {kind!r} requires a non-empty {value_field!r}.")
    return {"kind": kind, value_field: value.strip()}


def validate_verdict(verdict: Any, feedback: Any) -> tuple[str, str | None]:
    """Validate a verify verdict + optional feedback (fail-closed).

    ``verdict`` must be exactly ``pass`` or ``fail`` (lowercase, closed
    vocabulary). ``feedback`` (<= MAX_VERIFICATION_FEEDBACK_LENGTH chars) is
    only meaningful on ``fail`` - it exists to direct rework, so accepting it
    on ``pass`` and silently discarding it would break the fail-closed spirit
    of the feature: that is rejected too.
    """
    if verdict not in VALID_VERDICTS:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"verdict must be one of {sorted(VALID_VERDICTS)} (got {verdict!r}).",
            {"verdict": verdict},
        )
    if feedback is None or (isinstance(feedback, str) and feedback == ""):
        return verdict, None
    if not isinstance(feedback, str):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "feedback must be a string.",
            {"feedback": feedback},
        )
    if verdict == VERDICT_PASS:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "feedback is only accepted with verdict 'fail' - it directs rework.",
            {"verdict": verdict},
        )
    if len(feedback) > MAX_VERIFICATION_FEEDBACK_LENGTH:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"feedback exceeds {MAX_VERIFICATION_FEEDBACK_LENGTH} characters.",
            {"length": len(feedback)},
        )
    return verdict, feedback


def is_eligible_verifier(
    caller: str,
    *,
    creator: str,
    verify_by: dict[str, Any],
    caller_capabilities: Any = (),
) -> bool:
    """Pure eligibility of ``caller`` under a VALIDATED verify_by descriptor.

    ``capability`` resolves DYNAMICALLY at verify time (mirrors claim
    eligibility): the caller qualifies if they advertise the capability NOW.
    This function does NOT apply the anti-self-verification rule - callers
    must check ``caller == claimed_by`` FIRST (it wins over eligibility).
    """
    kind = verify_by.get("kind")
    if kind == "creator":
        return caller == creator
    if kind == "agent":
        return caller == verify_by.get("agent_id")
    if kind == "capability":
        return str(verify_by.get("capability")) in {
            str(cap) for cap in (caller_capabilities or ())
        }
    return False


def static_verifier_for(verify_by: dict[str, Any], creator: str) -> str | None:
    """Return the STATICALLY resolvable verifier agent_id, or ``None``.

    ``creator`` and ``agent`` descriptors name exactly one agent at creation
    time; ``capability`` is dynamic (resolved at verify time) and returns
    ``None``.
    """
    kind = verify_by.get("kind")
    if kind == "creator":
        return creator
    if kind == "agent":
        agent_id = verify_by.get("agent_id")
        return str(agent_id) if agent_id else None
    return None


def is_degenerate_self_claim(
    target: Any, *, creator: str, verify_by: dict[str, Any]
) -> bool:
    """Detect the statically unsolvable criteria + self-claim combination.

    A ``direct`` target whose ONLY possible claimant is also the statically
    resolved verifier can never be verified (the executor may not verify their
    own delivery), so the handoff must be rejected at creation. Only the pure
    ``direct`` strategy qualifies - ``direct_with_fallback`` and broad targets
    resolve claimants dynamically and are policed at verify time instead.
    """
    verifier = static_verifier_for(verify_by, creator)
    if verifier is None:
        return False
    return is_direct_target(target, verifier)


# --------------------------------------------------------------------------- #
# Dependencies (I5) - depends_on grammar + pure satisfaction evaluator
# --------------------------------------------------------------------------- #
MAX_DEPENDENCIES = 20

#: Satisfaction is STRICT: only a terminal, judged COMPLETED satisfies a
#: dependency. VERIFYING deliberately does NOT (the I4 gate - delivered but
#: unjudged work is not done yet).
DEPENDENCY_SATISFYING_STATUSES: frozenset[str] = frozenset({STATUS_COMPLETED})
#: Permanently failed dependencies: the dependent can NEVER become claimable
#: and is retained for manual intervention (cancel or operator action).
DEPENDENCY_FAILED_STATUSES: frozenset[str] = frozenset(
    {STATUS_REJECTED, STATUS_CANCELLED}
)


def validate_depends_on(raw: Any) -> list[str]:
    """Validate + normalise a ``depends_on`` id list (fail-closed grammar).

    Grammar: a JSON list of 1..MAX_DEPENDENCIES handoff ids (non-empty
    strings after strip), with NO exact duplicates (a duplicate is a caller
    mistake, never silently deduped). Order is preserved; ids are returned
    stripped. An empty list is invalid: callers that want no dependencies
    OMIT the parameter entirely.

    EXISTENCE of the ids (same workspace, not permanently failed) is the
    application layer's fail-closed gate (it needs I/O). Self-reference and
    cycles are impossible BY CONSTRUCTION: every id must already exist while
    the depending handoff does not yet, and the list is immutable after
    creation - the grammar therefore never needs a cycle check.
    """
    if not isinstance(raw, (list, tuple)):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "depends_on must be a list of handoff ids.",
            {"depends_on": raw},
        )
    if len(raw) == 0:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "depends_on cannot be empty - omit the parameter when the handoff "
            "has no dependencies.",
            {"depends_on": []},
        )
    if len(raw) > MAX_DEPENDENCIES:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"depends_on accepts at most {MAX_DEPENDENCIES} ids (got {len(raw)}).",
            {"count": len(raw), "max": MAX_DEPENDENCIES},
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"depends_on[{index}] must be a non-empty handoff id.",
                {"index": index, "item": item},
            )
        handoff_id = item.strip()
        if handoff_id in seen:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"depends_on[{index}] is an exact duplicate.",
                {"index": index, "item": handoff_id},
            )
        seen.add(handoff_id)
        normalized.append(handoff_id)
    return normalized


def summarize_dependencies(statuses: Iterable[str]) -> dict[str, int]:
    """Aggregate dependency statuses into the canonical counters.

    Returns ``{"total", "satisfied", "pending", "failed"}`` where satisfied
    counts strict COMPLETED, failed counts REJECTED|CANCELLED and pending is
    everything else (OPEN, CLAIMED, VERIFYING). These aggregates are the ONLY
    dependency detail ever exposed in a DEPENDENCY_NOT_MET error - the ids
    and statuses themselves stay private to reads of the handoff.
    """
    total = satisfied = failed = 0
    for status in statuses:
        total += 1
        if status in DEPENDENCY_SATISFYING_STATUSES:
            satisfied += 1
        elif status in DEPENDENCY_FAILED_STATUSES:
            failed += 1
    return {
        "total": total,
        "satisfied": satisfied,
        "pending": total - satisfied - failed,
        "failed": failed,
    }


def dependencies_satisfied(statuses: Iterable[str]) -> bool:
    """Whether EVERY dependency is strictly COMPLETED (no deps qualifies).

    This is the single claimability rule for the DAG: a handoff with any
    pending OR failed dependency is not claimable. It is evaluated on-read -
    nothing is ever materialised on the dependent's row.
    """
    return all(status in DEPENDENCY_SATISFYING_STATUSES for status in statuses)
