"""Pure routing rules: eligibility and visibility.

This module owns the *coordination routing* domain logic for Okto Nexus V1.
It answers two questions, with **no IO** whatsoever (stdlib only, never
``sqlite3``/``mcp`` - enforced by the import-boundary test):

* :func:`is_agent_eligible` - does ``agent`` match an item's ``target`` rule
  (the routing strategy) at instant ``now`` (given the item's ``created_at``)?
* :func:`can_agent_see_event` - may ``agent`` *see* an event/handoff, given the
  item's ``visibility`` *and* its ``target`` (visibility is layered on top of
  eligibility, and is **isolated by workspace**).

Both functions are total, deterministic, and side-effect free.

Target strategies (the ``strategy`` discriminator, case-insensitive, with
``-``/spaces normalised to ``_``)::

    direct                 agent_id == target.agent_id  (exact, opaque ids)
    capability             target.capability is possessed by the agent
                           (exact, CASE-SENSITIVE; ``preferred`` is advisory)
    role                   agent.role == target.role     (exact, CASE-SENSITIVE)
    broadcast              every agent in the workspace is eligible
    mixed                  union/OR of target.rules (each a sub-target)
    direct_with_fallback   the direct agent is always eligible; after
                           ``now >= created_at + fallback_after_seconds``
                           (INCLUSIVE, monotonic) the ``fallback`` sub-target
                           (default: broadcast) also becomes eligible

Visibilities (``visibility`` discriminator, case-insensitive)::

    public      any agent in the same workspace can see it
    eligible    only eligible agents (see :func:`is_agent_eligible`) can see it
    private     eligible-only; for non-direct targets ``private`` == ``eligible``
                (it never broadens beyond the eligible set)

Note that **visibility is not claimability**: an item may be visible to the
whole workspace (e.g. ``public``) while only its target is allowed to claim it.

Malformed inputs raise :class:`OktoNexusError` with ``VALIDATION_ERROR`` (the
canonical catalogue code); a well-formed rule that simply does not match an
agent returns ``False`` (not an error).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..errors import ErrorCode, OktoNexusError

__all__ = [
    "RoutingAgent",
    "is_agent_eligible",
    "can_agent_see_event",
    "normalize_capabilities",
    "target_strategy",
]


# --------------------------------------------------------------------------- #
# Canonical vocabularies
# --------------------------------------------------------------------------- #
_STRATEGIES: frozenset[str] = frozenset(
    {
        "direct",
        "capability",
        "role",
        "broadcast",
        "mixed",
        "direct_with_fallback",
    }
)

_VISIBILITIES: frozenset[str] = frozenset({"public", "eligible", "private"})

#: Visibility assumed when an item leaves ``visibility`` unset (NULL column).
#: An event with no explicit visibility is treated as workspace-``public``;
#: combined with the strict workspace-isolation check this keeps it scoped to
#: the originating workspace while still honouring ``visibility != claimability``
#: (a directed-but-public item is visible to all, claimable only by its target).
_DEFAULT_VISIBILITY = "public"


# --------------------------------------------------------------------------- #
# Lightweight routing view of an agent (duck-typed; dicts are also accepted)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class RoutingAgent:
    """The minimal agent context routing needs.

    ``workspace_id`` is the workspace the agent is *currently operating in*
    (agents are global identities, but routing decisions are always made within
    a workspace). ``capabilities`` accepts either a flag-mapping (``{"py": True}``
    -> the agent has ``"py"``) or a plain sequence of capability names; it is
    normalised lazily by the accessor.
    """

    agent_id: str
    workspace_id: str
    role: str | None = None
    capabilities: Mapping[str, Any] | Sequence[str] | None = field(default=None)


# --------------------------------------------------------------------------- #
# Generic attribute/key accessors (work on dataclasses AND plain mappings)
# --------------------------------------------------------------------------- #
def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _agent_id(agent: Any) -> str | None:
    value = _get(agent, "agent_id")
    return value if value is None else str(value)


def _agent_workspace(agent: Any) -> str | None:
    value = _get(agent, "workspace_id")
    return value if value is None else str(value)


def _agent_role(agent: Any) -> str | None:
    return _get(agent, "role")


def normalize_capabilities(capabilities: Any) -> frozenset[str]:
    """Normalise a raw capabilities value into an exact-match string set.

    The single rule shared by capability ROUTING and capability DISCOVERY
    (``capability_list``), so what is advertised is exactly what a
    ``capability`` target would match:

    * ``Mapping`` -> keys whose value is truthy (a capability mapped to a
      falsey value counts as *not* possessed).
    * ``str`` -> a single capability.
    * other ``Sequence``/iterable of strings -> that set.
    * ``None`` -> empty.

    Blank/whitespace names are dropped (they could never be matched by a
    ``capability`` target, which rejects an empty capability), so the advertised
    set equals the addressable set. A non-iterable value raises ``VALIDATION_ERROR``.
    """
    if capabilities is None:
        return frozenset()
    if isinstance(capabilities, Mapping):
        return frozenset(
            str(k) for k, v in capabilities.items() if v and str(k).strip()
        )
    if isinstance(capabilities, str):
        return frozenset({capabilities}) if capabilities.strip() else frozenset()
    if isinstance(capabilities, (set, frozenset, list, tuple)):
        return frozenset(str(c) for c in capabilities if str(c).strip())
    # Any other iterable of names.
    try:
        return frozenset(str(c) for c in capabilities if str(c).strip())
    except TypeError:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "Agent capabilities are not an iterable of names or a flag mapping.",
            {"capabilities_type": type(capabilities).__name__},
        ) from None


def _agent_capabilities(agent: Any) -> frozenset[str]:
    """Normalise an agent object's capabilities (see :func:`normalize_capabilities`)."""
    return normalize_capabilities(_get(agent, "capabilities"))


# --------------------------------------------------------------------------- #
# Time coercion (ISO-8601 string OR POSIX epoch seconds) -> epoch float
# --------------------------------------------------------------------------- #
def _to_epoch(value: Any, *, field_name: str) -> float | None:
    """Coerce an ISO-8601 string or numeric epoch into POSIX-epoch seconds.

    Returns ``None`` for ``None``/blank input. Raises ``VALIDATION_ERROR`` for
    a value that is neither a number nor a parseable timestamp. Naive ISO
    timestamps are assumed to be UTC; a trailing ``Z`` is honoured.
    """
    if value is None:
        return None
    # NB: bool is an int subclass - reject it explicitly as a timestamp.
    if isinstance(value, bool):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{field_name} must be a timestamp or epoch, not a boolean.",
            {"field": field_name, "value": value},
        )
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s[-1] in ("Z", "z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field_name} is not a valid ISO-8601 timestamp.",
                {"field": field_name, "value": value},
            ) from None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    raise OktoNexusError(
        ErrorCode.VALIDATION_ERROR,
        f"{field_name} must be an ISO-8601 string or epoch number.",
        {"field": field_name, "type": type(value).__name__},
    )


# --------------------------------------------------------------------------- #
# Target coercion / strategy resolution
# --------------------------------------------------------------------------- #
def _coerce_target(target: Any) -> Mapping[str, Any] | None:
    """Return the target as a mapping (parsing a JSON-object string if needed).

    ``None``/blank -> ``None`` (no routing restriction). A JSON string is
    parsed; anything that does not resolve to an object raises
    ``VALIDATION_ERROR``.
    """
    if target is None:
        return None
    if isinstance(target, Mapping):
        return target
    if isinstance(target, str):
        s = target.strip()
        if not s:
            return None
        try:
            parsed = json.loads(s)
        except (ValueError, TypeError):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "Target string is not valid JSON.",
                {"target": target},
            ) from None
        if isinstance(parsed, Mapping):
            return parsed
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "Target JSON must be an object.",
            {"target": target},
        )
    raise OktoNexusError(
        ErrorCode.VALIDATION_ERROR,
        "Target must be a mapping, a JSON object string, or null.",
        {"target_type": type(target).__name__},
    )


def _normalize_strategy(raw: Any) -> str:
    token = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    if token not in _STRATEGIES:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"Unknown routing strategy: {raw!r}.",
            {"strategy": raw, "supported": sorted(_STRATEGIES)},
        )
    return token


def _require(target: Mapping[str, Any], key: str, strategy: str) -> Any:
    value = target.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"Target strategy {strategy!r} requires field {key!r}.",
            {"strategy": strategy, "missing_field": key},
        )
    return value


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def is_agent_eligible(
    agent: Any,
    target: Any,
    created_at: Any = None,
    now: Any = None,
) -> bool:
    """Return whether ``agent`` matches the routing ``target`` at ``now``.

    Parameters
    ----------
    agent:
        A :class:`RoutingAgent` (or any object/mapping exposing ``agent_id``,
        ``role`` and ``capabilities``).
    target:
        The routing rule (mapping or JSON-object string). ``None``/blank means
        *no restriction* and resolves to broadcast (every agent eligible).
    created_at:
        The item's creation time (ISO-8601 string or epoch seconds). Only
        consulted by the time-based ``direct_with_fallback`` strategy.
    now:
        The instant the decision is evaluated at (ISO-8601 string or epoch
        seconds). Only consulted by ``direct_with_fallback``.

    This function is intentionally workspace-agnostic: it answers *"does this
    agent match the rule"*. Workspace isolation is enforced one layer up, in
    :func:`can_agent_see_event`.

    Raises
    ------
    OktoNexusError
        ``VALIDATION_ERROR`` for an unknown strategy, a missing required field,
        a malformed ``mixed`` rule list, or (for ``direct_with_fallback``)
        missing/invalid timing fields.
    """
    resolved = _coerce_target(target)
    if resolved is None:
        # No routing restriction -> broadcast semantics.
        return True

    strategy = resolved.get("strategy", resolved.get("kind"))
    if strategy is None:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "Target is missing the 'strategy' discriminator.",
            {"target_keys": sorted(str(k) for k in resolved.keys())},
        )
    strategy = _normalize_strategy(strategy)

    if strategy == "broadcast":
        return True

    if strategy == "direct":
        wanted = _require(resolved, "agent_id", strategy)
        return _agent_id(agent) == str(wanted)

    if strategy == "role":
        wanted = _require(resolved, "role", strategy)
        # Exact, case-sensitive role match.
        return _agent_role(agent) == wanted

    if strategy == "capability":
        wanted = _require(resolved, "capability", strategy)
        owned = _agent_capabilities(agent)
        if isinstance(wanted, str):
            # Exact, case-sensitive capability membership.
            return wanted in owned
        if isinstance(wanted, (list, tuple, set, frozenset)):
            # Any-of for a list of required capabilities.
            return any(str(c) in owned for c in wanted)
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "Capability target must be a string or a list of strings.",
            {"capability": wanted},
        )

    if strategy == "mixed":
        rules = resolved.get("rules", resolved.get("targets"))
        if rules is None or not isinstance(rules, (list, tuple)):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "Mixed target requires a 'rules' list of sub-targets.",
                {"rules_type": type(rules).__name__ if rules is not None else None},
            )
        # Union / OR over the sub-rules. Short-circuits on the first match.
        return any(
            is_agent_eligible(agent, rule, created_at, now) for rule in rules
        )

    # strategy == "direct_with_fallback"
    wanted = _require(resolved, "agent_id", strategy)
    if _agent_id(agent) == str(wanted):
        # The direct recipient is eligible at all times (monotonic floor).
        return True

    fallback_after = _require(resolved, "fallback_after_seconds", strategy)
    if isinstance(fallback_after, bool) or not isinstance(fallback_after, (int, float)):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "fallback_after_seconds must be a non-negative number.",
            {"fallback_after_seconds": fallback_after},
        )
    if fallback_after < 0:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "fallback_after_seconds must be non-negative.",
            {"fallback_after_seconds": fallback_after},
        )

    created_epoch = _to_epoch(created_at, field_name="created_at")
    now_epoch = _to_epoch(now, field_name="now")
    if created_epoch is None or now_epoch is None:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "direct_with_fallback requires both created_at and now.",
            {"has_created_at": created_epoch is not None, "has_now": now_epoch is not None},
        )

    # Inclusive boundary, monotonic in ``now``.
    if now_epoch >= created_epoch + float(fallback_after):
        fallback = resolved.get("fallback")
        if fallback is None:
            # Default fallback is a workspace-wide broadcast.
            return True
        return is_agent_eligible(agent, fallback, created_at, now)
    return False


def target_strategy(target: Any) -> str | None:
    """Return the normalised routing strategy of ``target`` (or ``None``).

    ``None``/blank target -> ``None`` (no restriction / broadcast semantics). A
    present target's ``strategy``/``kind`` discriminator is normalised exactly as
    :func:`is_agent_eligible` (case-insensitive, ``-``/space -> ``_``); a missing
    or unknown strategy raises ``VALIDATION_ERROR`` (consistent with eligibility).

    Used by the inbox model (ADR 0001) to tell a *directed* target (``direct`` /
    ``direct_with_fallback``, where resolving to nobody is an unknown-recipient
    ERROR) from a *group* target (where zero matches is a benign warning).
    """
    resolved = _coerce_target(target)
    if resolved is None:
        return None
    strategy = resolved.get("strategy", resolved.get("kind"))
    if strategy is None:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "Target is missing the 'strategy' discriminator.",
            {"target_keys": sorted(str(k) for k in resolved.keys())},
        )
    return _normalize_strategy(strategy)


def _normalize_visibility(raw: Any) -> str:
    if raw is None:
        return _DEFAULT_VISIBILITY
    token = str(raw).strip().lower()
    if not token:
        return _DEFAULT_VISIBILITY
    if token not in _VISIBILITIES:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"Unknown visibility: {raw!r}.",
            {"visibility": raw, "supported": sorted(_VISIBILITIES)},
        )
    return token


def can_agent_see_event(agent: Any, event_or_handoff: Any, now: Any = None) -> bool:
    """Return whether ``agent`` may *see* an event or handoff.

    Visibility is layered on top of :func:`is_agent_eligible` and is strictly
    isolated by workspace:

    * the agent and the item must share the same ``workspace_id`` (otherwise
      ``False`` - no cross-workspace visibility);
    * ``public`` -> visible to any agent in that workspace;
    * ``eligible`` -> visible iff :func:`is_agent_eligible` is ``True``;
    * ``private`` -> eligible-only; for non-direct targets this equals
      ``eligible`` (private never broadens past the eligible set).

    Parameters
    ----------
    agent:
        A :class:`RoutingAgent` (or mapping/object) carrying ``workspace_id``.
    event_or_handoff:
        An :class:`~okto_nexus.domain.models.Event` /
        :class:`~okto_nexus.domain.models.Handoff` (or mapping) exposing
        ``workspace_id``, ``visibility``, ``target`` and ``created_at``.
    now:
        The decision instant (only used by time-based eligibility).

    Raises
    ------
    OktoNexusError
        ``VALIDATION_ERROR`` for an unknown ``visibility`` or a malformed
        ``target`` (propagated from :func:`is_agent_eligible`).
    """
    agent_ws = _agent_workspace(agent)
    item_ws = _get(event_or_handoff, "workspace_id")
    item_ws = item_ws if item_ws is None else str(item_ws)

    # Strict workspace isolation: both must be present and identical.
    if agent_ws is None or item_ws is None or agent_ws != item_ws:
        return False

    visibility = _normalize_visibility(_get(event_or_handoff, "visibility"))
    if visibility == "public":
        return True

    # Both ``eligible`` and ``private`` resolve to the eligible set. ``private``
    # for non-direct targets is explicitly equal to ``eligible`` (it never
    # broadens), and for a ``direct`` target the eligible set is the single
    # direct recipient - so the two collapse to the same eligibility check.
    target = _get(event_or_handoff, "target")
    created_at = _get(event_or_handoff, "created_at")
    return is_agent_eligible(agent, target, created_at, now)
