"""Pure domain rules for per-recipient message delivery — the inbox model.

ADR 0001. Strictly side-effect-free (stdlib only; never ``sqlite3``/``mcp`` -
enforced by the import-boundary test). This module owns:

* the delivery **status vocabulary** (``unread`` / ``delivered`` / ``read`` /
  ``parked`` - the dead-letter lane for deliveries that exhausted their claim
  attempts);
* :func:`new_delivery_id`;
* :func:`resolve_recipients` - which agents a message ``target`` reaches, reusing
  the IMPORTED routing predicate :func:`okto_nexus.domain.routing.is_agent_eligible`
  (recipient resolution is EAGER / send-time, per ADR decision D3);
* :func:`requires_known_recipient` - whether an empty recipient set is an ERROR
  (a *directed* target naming an unknown agent) or a benign warning (a *group*
  target matching nobody).

Recipient resolution is workspace-agnostic here (``is_agent_eligible`` never
consults ``workspace_id``); the candidate SET is chosen one layer up - global
agents for directed/capability/role targets, the workspace's present agents for
``broadcast`` (the bounded blast radius from ADR decision S1).

Note on the time-based ``direct_with_fallback`` strategy: resolution passes
``created_at == now`` (the send instant), so a positive ``fallback_after_seconds``
delay has not elapsed and the message resolves to the **direct agent only** - the
lazy time-based fallback does not fire under eager inbox delivery (a delay of
``0`` includes the fallback set immediately).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..errors import ErrorCode, OktoNexusError
from .base import new_id
from .messages import validate_target
from .routing import is_agent_eligible, target_strategy

__all__ = [
    "DELIVERY_UNREAD",
    "DELIVERY_DELIVERED",
    "DELIVERY_READ",
    "DELIVERY_PARKED",
    "DELIVERY_STATUSES",
    "new_delivery_id",
    "resolve_recipients",
    "requires_known_recipient",
    "requires_workspace_audience",
    "assert_deliverable_message_target",
]

#: Delivery lanes. ``unread`` (queued) -> ``delivered`` (pulled, in-flight under a
#: lease) -> ``read`` (acknowledged into history). A delivery whose claim
#: attempts are exhausted is ``parked`` (dead-letter): it is never redelivered,
#: so a poison message cannot reoccupy the head of every pull batch.
DELIVERY_UNREAD = "unread"
DELIVERY_DELIVERED = "delivered"
DELIVERY_READ = "read"
DELIVERY_PARKED = "parked"
DELIVERY_STATUSES: frozenset[str] = frozenset(
    {DELIVERY_UNREAD, DELIVERY_DELIVERED, DELIVERY_READ, DELIVERY_PARKED}
)

#: Strategies that name a SPECIFIC recipient, so resolving to nobody is an ERROR
#: (an unknown agent) rather than a benign zero-match warning.
_DIRECTED_STRATEGIES: frozenset[str] = frozenset({"direct", "direct_with_fallback"})


def new_delivery_id() -> str:
    """Return a fresh, server-assigned, opaque delivery id (``del_…``)."""
    return new_id("del")


def _candidate_agent_id(candidate: Any) -> str | None:
    """Extract ``agent_id`` from a candidate (any ``Mapping`` or attr object).

    Matches the breadth of routing's own accessor (``is_agent_eligible`` accepts
    any :class:`collections.abc.Mapping`), so an eligible candidate is never
    silently dropped from the resolved set.
    """
    if isinstance(candidate, Mapping):
        value = candidate.get("agent_id")
    else:
        value = getattr(candidate, "agent_id", None)
    return None if value is None else str(value)


def resolve_recipients(
    target: Any, candidates: Any, now: Any = None
) -> frozenset[str]:
    """Return the ``agent_id`` set among ``candidates`` that ``target`` reaches.

    Pure: applies the IMPORTED routing rule :func:`is_agent_eligible` to each
    candidate (a :class:`~okto_nexus.domain.routing.RoutingAgent` or any
    ``Mapping`` exposing ``agent_id``/``role``/``capabilities``) at instant
    ``now``. The candidate set is supplied by the caller (global agents for
    directed / capability / role targets; the workspace's agents for
    ``broadcast``).

    The ``target`` schema is validated **up front** (via
    :func:`okto_nexus.domain.messages.validate_target`), so a malformed target
    raises ``VALIDATION_ERROR`` regardless of how many candidates there are -
    including an empty list. A well-formed target that simply matches no
    candidate yields an empty set (the caller decides error vs. warning via
    :func:`requires_known_recipient`).
    """
    # Validate once, independent of candidate count: an empty candidate list must
    # NOT silently accept a malformed target.
    validate_target(target, now)
    resolved: set[str] = set()
    for candidate in candidates:
        if is_agent_eligible(candidate, target, created_at=now, now=now):
            agent_id = _candidate_agent_id(candidate)
            if agent_id is not None:
                resolved.add(agent_id)
    return frozenset(resolved)


def requires_known_recipient(target: Any) -> bool:
    """Whether an empty recipient set must be treated as an ERROR.

    ``True`` for ``direct`` / ``direct_with_fallback`` - they name a specific
    agent, so zero recipients means an *unknown* recipient (a hard error).
    ``False`` for group targets (``capability`` / ``role`` / ``broadcast`` /
    ``mixed`` / no target), where zero matches is a benign warning. Propagates
    ``VALIDATION_ERROR`` for a malformed/unknown strategy.
    """
    return target_strategy(target) in _DIRECTED_STRATEGIES


def requires_workspace_audience(target: Any) -> bool:
    """Whether ``target`` is delivered to the workspace's PARTICIPANTS (ADR S1).

    ``True`` for a top-level ``broadcast`` or an absent target - a broadcast is
    bounded to the sender's workspace (its present agents), never the whole bus.
    ``False`` for ``direct`` / ``capability`` / ``role`` / ``mixed`` /
    ``direct_with_fallback``, which resolve against the GLOBAL agent registry.
    Propagates ``VALIDATION_ERROR`` for a malformed/unknown strategy.

    A bare top-level ``broadcast`` stays workspace-bounded. Unsafe constructions
    that would broadcast against the GLOBAL registry - a ``broadcast`` nested in a
    ``mixed``, or a ``direct_with_fallback`` whose fallback fires eagerly - are
    rejected up front by :func:`assert_deliverable_message_target`, so they never
    reach this function.
    """
    return target_strategy(target) in (None, "broadcast")


def _mixed_rules(target: Any) -> list[Any]:
    """Best-effort extraction of a ``mixed`` target's sub-rules (or ``[]``)."""
    obj: Any = target
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except (TypeError, ValueError):
            return []
    if not isinstance(obj, Mapping):
        return []
    rules = obj.get("rules", obj.get("targets"))
    return list(rules) if isinstance(rules, (list, tuple)) else []


def assert_deliverable_message_target(target: Any) -> None:
    """Reject message targets that cannot be delivered SAFELY under eager fan-out.

    Inbox delivery resolves recipients once, at send time (ADR D3). Two targets
    break that model and are rejected with ``VALIDATION_ERROR``:

    * ``direct_with_fallback`` - a lazy, *time-based* strategy whose fallback can
      never fire after an eager send (and whose ``0``-delay form would broadcast
      against the GLOBAL registry); model timed escalation as a **handoff**.
    * a ``broadcast`` (or ``direct_with_fallback``) **nested inside a ``mixed``** -
      it would resolve against the global registry = an unscoped bus-wide
      broadcast, defeating S1's workspace blast-radius cap. A bare top-level
      ``broadcast`` stays workspace-bounded and is allowed.

    A ``None``/blank or otherwise well-formed safe target is accepted. A malformed
    target propagates ``VALIDATION_ERROR`` from :func:`target_strategy`.
    """
    _reject_unsafe(target, nested=False)


def _reject_unsafe(target: Any, *, nested: bool) -> None:
    strategy = target_strategy(target)
    if strategy == "direct_with_fallback":
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "direct_with_fallback is a time-based strategy not supported for "
            "messages (the fallback cannot fire after an eager send); use a "
            "handoff for timed escalation.",
            {"strategy": strategy, "nested": nested},
        )
    if nested and strategy == "broadcast":
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "broadcast may not be nested inside a mixed target (it would broadcast "
            "to every agent on the bus); use a bare top-level broadcast, which "
            "stays bounded to the workspace.",
            {"strategy": strategy, "nested": nested},
        )
    if strategy == "mixed":
        for rule in _mixed_rules(target):
            _reject_unsafe(rule, nested=True)
