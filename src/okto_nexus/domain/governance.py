"""Pure domain rules for governance policies (deny rules + quotas + HITL).

V1 of the policy engine (spec ffef15bf): the operator declares *deny-only*
policies - subject (agent | role | capability | star) x action (message_create,
broadcast, handoff_create, artifact_put) x limit (categorical deny, max_count
per sliding window, max_bytes, max_open_handoffs). Spec 2948b2a2 (HITL) adds a
fifth limit kind, ``require_approval``: a binary, parameterless kind valid only
for ``message_create`` / ``handoff_create`` that asks the application to
intercept the action into an approvals queue instead of denying it. This module
owns the IO-free half: the closed vocabularies, policy form validation
(fail-closed), subject / action matching, the deterministic ordering and the
three-stage verdict over PRE-fetched consumption numbers. It never imports
``sqlite3`` nor ``mcp`` (enforced by the import-boundary test).

The evaluator is only ever invoked with the relevant feature flag ON - flag OFF
is accept-and-ignore at the application layer (spec a9a2c856 decision D4, the
canonical gating pattern), so nothing here needs to know about the flags.

Matching semantics (BR2):

* subject ``agent`` matches on exact ``agent_id``; ``role`` on the agent's
  registered role; ``capability`` when the caller advertises the capability;
  ``star`` always.
* action ``message_create`` matches EVERY message creation including
  broadcasts; ``broadcast`` matches only broadcast-strategy sends.
* Disabled policies never match. No matching policy means implicit allow.
* Verdict precedence: a categorical deny beats any quota, and both beat
  ``require_approval`` - only an action that would have PASSED is intercepted
  (spec 2948b2a2 BR8). Among violated quotas (and among matching
  ``require_approval`` policies) the FIRST in deterministic
  ``(created_at, policy_id)`` order is reported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ..errors import ErrorCode, OktoNexusError

__all__ = [
    "SUBJECT_AGENT",
    "SUBJECT_ROLE",
    "SUBJECT_CAPABILITY",
    "SUBJECT_STAR",
    "SUBJECT_KINDS",
    "ACTION_MESSAGE_CREATE",
    "ACTION_BROADCAST",
    "ACTION_HANDOFF_CREATE",
    "ACTION_ARTIFACT_PUT",
    "ACTIONS",
    "LIMIT_DENY",
    "LIMIT_MAX_COUNT",
    "LIMIT_MAX_BYTES",
    "LIMIT_MAX_OPEN_HANDOFFS",
    "LIMIT_REQUIRE_APPROVAL",
    "LIMIT_KINDS",
    "COUNT_LIMIT_KINDS",
    "APPROVAL_ACTIONS",
    "WINDOWS",
    "WINDOW_SECONDS",
    "EVENT_DENIED",
    "EVENT_APPROVAL_REQUESTED",
    "EVENT_APPROVAL_GRANTED",
    "EVENT_APPROVAL_DENIED",
    "Policy",
    "Subject",
    "Violation",
    "ApprovalRequired",
    "validate_policy_form",
    "subject_matches",
    "action_matches",
    "applicable_policies",
    "decide",
]


# --------------------------------------------------------------------------- #
# Closed vocabularies (BR1 - fail-closed on any value outside them)
# --------------------------------------------------------------------------- #
SUBJECT_AGENT = "agent"
SUBJECT_ROLE = "role"
SUBJECT_CAPABILITY = "capability"
SUBJECT_STAR = "star"
SUBJECT_KINDS: frozenset[str] = frozenset(
    {SUBJECT_AGENT, SUBJECT_ROLE, SUBJECT_CAPABILITY, SUBJECT_STAR}
)

ACTION_MESSAGE_CREATE = "message_create"
ACTION_BROADCAST = "broadcast"
ACTION_HANDOFF_CREATE = "handoff_create"
ACTION_ARTIFACT_PUT = "artifact_put"
ACTIONS: frozenset[str] = frozenset(
    {
        ACTION_MESSAGE_CREATE,
        ACTION_BROADCAST,
        ACTION_HANDOFF_CREATE,
        ACTION_ARTIFACT_PUT,
    }
)

LIMIT_DENY = "deny"
LIMIT_MAX_COUNT = "max_count"
LIMIT_MAX_BYTES = "max_bytes"
LIMIT_MAX_OPEN_HANDOFFS = "max_open_handoffs"
LIMIT_REQUIRE_APPROVAL = "require_approval"
LIMIT_KINDS: frozenset[str] = frozenset(
    {
        LIMIT_DENY,
        LIMIT_MAX_COUNT,
        LIMIT_MAX_BYTES,
        LIMIT_MAX_OPEN_HANDOFFS,
        LIMIT_REQUIRE_APPROVAL,
    }
)
#: Quota kinds whose ``current`` consumption is a COUNT the application must
#: pre-fetch (same UoW as the write path) and hand to :func:`decide`.
COUNT_LIMIT_KINDS: frozenset[str] = frozenset(
    {LIMIT_MAX_COUNT, LIMIT_MAX_OPEN_HANDOFFS}
)
#: Actions a require_approval policy may target (spec 2948b2a2 FR1 - V1 keeps
#: artifact_put out, and the broadcast hierarchy is reached via
#: message_create like everywhere else). Anything outside is fail-closed.
APPROVAL_ACTIONS: frozenset[str] = frozenset(
    {ACTION_MESSAGE_CREATE, ACTION_HANDOFF_CREATE}
)

WINDOWS: frozenset[str] = frozenset({"1h", "24h"})
#: Sliding-window sizes; the application derives ``since = now - seconds``.
WINDOW_SECONDS: dict[str, int] = {"1h": 3600, "24h": 86400}

#: Audit event emitted (workspace stream) when an action is denied (BR6).
EVENT_DENIED = "governance.denied"
#: HITL lifecycle events (spec 2948b2a2 TR5); payloads never carry the
#: intercepted action's subject/body (BR5).
EVENT_APPROVAL_REQUESTED = "approval.requested"
EVENT_APPROVAL_GRANTED = "approval.granted"
EVENT_APPROVAL_DENIED = "approval.denied"


# --------------------------------------------------------------------------- #
# Value objects
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Policy:
    """One stored governance policy row, as the evaluator sees it."""

    policy_id: str
    subject_kind: str
    subject_value: str | None
    action: str
    limit_kind: str
    limit_value: int | None
    window: str | None
    enabled: bool
    created_at: str

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "Policy":
        """Build a :class:`Policy` from a repo row / plain dict."""
        return cls(
            policy_id=str(row["policy_id"]),
            subject_kind=str(row["subject_kind"]),
            subject_value=row.get("subject_value"),
            action=str(row["action"]),
            limit_kind=str(row["limit_kind"]),
            limit_value=row.get("limit_value"),
            window=row.get("window"),
            enabled=bool(row.get("enabled", True)),
            created_at=str(row.get("created_at") or ""),
        )


@dataclass(frozen=True)
class Subject:
    """The caller as the matcher sees it (identity already resolved)."""

    agent_id: str
    role: str | None = None
    capabilities: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Violation:
    """The verdict of :func:`decide` when a policy denies the action.

    ``current`` carries the caller's own pre-fetched consumption for quota
    violations (count or payload bytes) and is ``None`` for categorical deny.
    The application maps this to ``POLICY_DENIED`` (deny) or ``QUOTA_EXCEEDED``
    (quotas) - details never reveal other agents' state (BR5).
    """

    policy: Policy
    current: int | None = None


@dataclass(frozen=True)
class ApprovalRequired:
    """The verdict of :func:`decide` when the action must be intercepted.

    Returned ONLY when the action would otherwise pass (no deny, no violated
    quota - spec 2948b2a2 BR8) and a ``require_approval`` policy matches;
    ``policy`` is the FIRST matching one in ``(created_at, policy_id)`` order.
    The application serialises the action into the approvals queue and returns
    the ``pending_approval`` envelope instead of executing.
    """

    policy: Policy


# --------------------------------------------------------------------------- #
# Policy form validation (BR1)
# --------------------------------------------------------------------------- #
def _norm_token(raw: Any) -> str:
    return str(raw).strip().lower() if raw is not None else ""


def validate_policy_form(
    *,
    subject_kind: Any,
    subject_value: Any = None,
    action: Any,
    limit_kind: Any,
    limit_value: Any = None,
    window: Any = None,
) -> dict[str, Any]:
    """Validate + normalise a policy's FORM; return the storable field dict.

    Fail-closed: any value outside the closed vocabularies, a missing/extra
    ``window``, a non-positive ``limit_value`` or a malformed ``subject_value``
    raises ``VALIDATION_ERROR``. Existence checks that need IO (registered
    agent, capability in the catalogue) belong to the application layer.
    """
    kind = _norm_token(subject_kind)
    if kind not in SUBJECT_KINDS:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"Unknown subject_kind: {subject_kind!r}.",
            {"subject_kind": subject_kind, "supported": sorted(SUBJECT_KINDS)},
        )

    if kind == SUBJECT_STAR:
        value: str | None = "*"
    else:
        value = str(subject_value).strip() if subject_value is not None else ""
        if not value:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"subject_value is required for subject_kind={kind!r}.",
                {"subject_kind": kind, "subject_value": subject_value},
            )

    act = _norm_token(action)
    if act not in ACTIONS:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"Unknown action: {action!r}.",
            {"action": action, "supported": sorted(ACTIONS)},
        )

    limit = _norm_token(limit_kind)
    if limit not in LIMIT_KINDS:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"Unknown limit_kind: {limit_kind!r}.",
            {"limit_kind": limit_kind, "supported": sorted(LIMIT_KINDS)},
        )

    if limit == LIMIT_MAX_COUNT:
        win = _norm_token(window)
        if win not in WINDOWS:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "window is required for limit_kind=max_count and must be one of "
                f"{sorted(WINDOWS)}.",
                {"window": window, "supported": sorted(WINDOWS)},
            )
        norm_window: str | None = win
    else:
        if window is not None and str(window).strip():
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"window is only allowed for limit_kind=max_count (got {limit!r}).",
                {"limit_kind": limit, "window": window},
            )
        norm_window = None

    if limit == LIMIT_REQUIRE_APPROVAL and act not in APPROVAL_ACTIONS:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "limit_kind=require_approval only applies to "
            f"{sorted(APPROVAL_ACTIONS)} (got action={act!r}).",
            {"limit_kind": limit, "action": act, "supported": sorted(APPROVAL_ACTIONS)},
        )

    if limit in (LIMIT_DENY, LIMIT_REQUIRE_APPROVAL):
        if limit_value is not None:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"limit_value is not allowed for limit_kind={limit!r}.",
                {"limit_kind": limit, "limit_value": limit_value},
            )
        norm_limit_value: int | None = None
    else:
        if isinstance(limit_value, bool) or not isinstance(limit_value, int):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"limit_value must be a positive integer for limit_kind={limit!r}.",
                {"limit_kind": limit, "limit_value": limit_value},
            )
        if limit_value <= 0:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"limit_value must be a positive integer for limit_kind={limit!r}.",
                {"limit_kind": limit, "limit_value": limit_value},
            )
        norm_limit_value = limit_value

    return {
        "subject_kind": kind,
        "subject_value": value,
        "action": act,
        "limit_kind": limit,
        "limit_value": norm_limit_value,
        "window": norm_window,
    }


# --------------------------------------------------------------------------- #
# Matching (BR2)
# --------------------------------------------------------------------------- #
def subject_matches(policy: Policy, subject: Subject) -> bool:
    """Return whether ``policy``'s subject clause covers ``subject``."""
    if policy.subject_kind == SUBJECT_STAR:
        return True
    if policy.subject_kind == SUBJECT_AGENT:
        return policy.subject_value == subject.agent_id
    if policy.subject_kind == SUBJECT_ROLE:
        return bool(subject.role) and policy.subject_value == subject.role
    if policy.subject_kind == SUBJECT_CAPABILITY:
        return policy.subject_value in subject.capabilities
    return False


def action_matches(policy_action: str, action: str) -> bool:
    """Return whether a policy's action clause covers the attempted ``action``.

    ``message_create`` covers every message creation INCLUDING broadcasts;
    ``broadcast`` covers only broadcast-strategy sends (BR2).
    """
    if policy_action == action:
        return True
    return policy_action == ACTION_MESSAGE_CREATE and action == ACTION_BROADCAST


def applicable_policies(
    policies: Iterable[Policy], subject: Subject, action: str
) -> list[Policy]:
    """Filter to enabled policies matching ``subject`` x ``action``, ordered.

    The deterministic ``(created_at, policy_id)`` order fixes which policy is
    reported when several are violated (BR2). Malformed rows are not expected
    here (writes are fail-closed); anything not matching simply drops out.
    """
    matched = [
        p
        for p in policies
        if p.enabled
        and p.limit_kind in LIMIT_KINDS
        and subject_matches(p, subject)
        and action_matches(p.action, action)
    ]
    matched.sort(key=lambda p: (p.created_at, p.policy_id))
    return matched


# --------------------------------------------------------------------------- #
# Verdict (deny-overrides, deterministic)
# --------------------------------------------------------------------------- #
def decide(
    applicable: list[Policy],
    *,
    size_bytes: int,
    usage: Mapping[str, int],
) -> Violation | ApprovalRequired | None:
    """Return the winning verdict: deny/quota, interception, or allow.

    ``applicable`` is the ordered output of :func:`applicable_policies`.
    ``size_bytes`` is the UTF-8 payload size of the CURRENT action (0 when the
    action carries no payload). ``usage`` maps ``policy_id`` to the caller's
    pre-fetched consumption for every count-based quota in ``applicable``
    (``max_count`` / ``max_open_handoffs``) - fetched by the application inside
    the SAME UoW as the write path; a missing entry is a programming error and
    raises ``KeyError`` (never fails open).

    Violation semantics (BR3): counts violate when ``current >= limit`` (the
    current action would exceed the budget); ``max_bytes`` violates when
    ``size_bytes > limit`` (the exact limit passes). Deny beats quotas.

    Third stage (spec 2948b2a2 BR8): only when the action would have passed
    every deny and quota, the FIRST matching ``require_approval`` policy (the
    list is already deterministically ordered) yields :class:`ApprovalRequired`
    so the application can intercept instead of executing.
    """
    for policy in applicable:
        if policy.limit_kind == LIMIT_DENY:
            return Violation(policy)
    for policy in applicable:
        limit = policy.limit_value
        if limit is None:
            continue
        if policy.limit_kind in COUNT_LIMIT_KINDS:
            current = usage[policy.policy_id]
            if current >= limit:
                return Violation(policy, current=current)
        elif policy.limit_kind == LIMIT_MAX_BYTES:
            if size_bytes > limit:
                return Violation(policy, current=size_bytes)
    for policy in applicable:
        if policy.limit_kind == LIMIT_REQUIRE_APPROVAL:
            return ApprovalRequired(policy)
    return None
