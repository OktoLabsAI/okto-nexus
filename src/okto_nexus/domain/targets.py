"""Single source of truth for the routing-target GRAMMAR.

Every slice that accepts, stores, or evaluates a routing ``target`` (routing
eligibility/visibility, handoff descriptors, message send-time validation)
parses and validates it through THIS module - the grammar is defined exactly
once, so a target accepted on one write path can never be rejected (or worse,
silently reinterpreted) on another.

Strictly side-effect free (stdlib + the error catalogue only); never imports
``sqlite3`` nor ``mcp`` (enforced by the import-boundary test).

Grammar (the ``strategy`` discriminator is case-insensitive, with ``-``/spaces
normalised to ``_``; ``kind`` is accepted as an alias of ``strategy``)::

    direct                 requires a non-empty ``agent_id``
    capability             requires ``capability`` - a non-empty string or a
                           non-empty list of non-empty names (any-of)
    role                   requires a non-empty ``role``
    tag                    requires a NON-EMPTY ``selector`` - either the flat
                           tag map (``{key: [value, ...]}``) or the rich
                           match-expression list (``[{key, operator, values}]``
                           with In | NotIn | Exists | DoesNotExist) - FORM
                           validated by :mod:`okto_nexus.domain.tag_selector`;
                           catalog EXISTENCE is the application layer's gate.
                           An empty selector is rejected (it would silently
                           be a broadcast)
    broadcast              no required fields
    mixed                  requires a NON-EMPTY ``rules`` list (``targets`` is
                           accepted as an alias) of sub-targets; each sub-rule
                           is validated recursively and may NOT be null/blank
                           (a null sub-rule would silently resolve to
                           "no restriction" = a covert broadcast) nor a nested
                           ``broadcast`` (mixed-with-broadcast degenerates to a
                           broadcast - use a bare top-level broadcast instead)
    direct_with_fallback   requires a non-empty ``agent_id`` and a non-negative
                           numeric ``fallback_after_seconds``; an explicit
                           ``fallback`` sub-target is validated recursively
                           (absent/null means the default broadcast fallback)

Malformed targets raise :class:`OktoNexusError` with ``VALIDATION_ERROR`` (the
canonical catalogue code) and a prescriptive message.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from ..errors import ErrorCode, OktoNexusError
from .tag_selector import validate_selector

__all__ = [
    "VALID_STRATEGIES",
    "coerce_target",
    "normalize_strategy",
    "target_strategy",
    "validate_target",
    "iter_target_selectors",
    "is_direct_target",
]

#: The closed set of routing strategies - the ONLY definition in the codebase.
VALID_STRATEGIES: frozenset[str] = frozenset(
    {
        "direct",
        "capability",
        "role",
        "tag",
        "broadcast",
        "mixed",
        "direct_with_fallback",
    }
)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def coerce_target(target: Any, *, required: bool = False) -> Mapping[str, Any] | None:
    """Return ``target`` as a mapping (parsing a JSON-object string if needed).

    ``None``/blank -> ``None`` (no routing restriction), unless ``required`` -
    then a missing target raises ``VALIDATION_ERROR`` (a handoff always carries
    an explicit routing rule). Anything that does not resolve to a JSON object
    raises ``VALIDATION_ERROR``.
    """
    if _is_blank(target):
        if required:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "target descriptor is required.",
                {"target": target},
            )
        return None
    if isinstance(target, Mapping):
        return target
    if isinstance(target, str):
        try:
            parsed = json.loads(target)
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


def normalize_strategy(raw: Any) -> str:
    """Normalise + validate a strategy token (case-insensitive, ``-``/space -> ``_``).

    Raises ``VALIDATION_ERROR`` for a missing/blank or unknown strategy.
    """
    if _is_blank(raw):
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


def _strategy_of(resolved: Mapping[str, Any]) -> str:
    raw = resolved.get("strategy", resolved.get("kind"))
    if raw is None:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "Target is missing the 'strategy' discriminator.",
            {"target_keys": sorted(str(k) for k in resolved.keys())},
        )
    return normalize_strategy(raw)


def target_strategy(target: Any) -> str | None:
    """Return the normalised routing strategy of ``target`` (or ``None``).

    ``None``/blank target -> ``None`` (no restriction / broadcast semantics).
    Only the discriminator is resolved - per-strategy required fields are NOT
    checked here (use :func:`validate_target` for the full grammar); a missing
    or unknown strategy raises ``VALIDATION_ERROR``.
    """
    resolved = coerce_target(target)
    if resolved is None:
        return None
    return _strategy_of(resolved)


def _require(resolved: Mapping[str, Any], key: str, strategy: str) -> Any:
    value = resolved.get(key)
    if _is_blank(value):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"Target strategy {strategy!r} requires field {key!r}.",
            {"strategy": strategy, "missing_field": key},
        )
    return value


def _validate_capability(resolved: Mapping[str, Any]) -> Any:
    wanted = _require(resolved, "capability", "capability")
    if isinstance(wanted, str):
        return wanted
    if isinstance(wanted, Sequence) and not isinstance(wanted, (str, bytes)):
        names = list(wanted)
        if not names or any(_is_blank(name) for name in names):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "Capability target list must be a non-empty list of non-empty "
                "capability names.",
                {"capability": wanted},
            )
        return names
    raise OktoNexusError(
        ErrorCode.VALIDATION_ERROR,
        "Capability target must be a string or a list of strings.",
        {"capability": wanted},
    )


def _validate_mixed_rules(resolved: Mapping[str, Any]) -> list[dict[str, Any]]:
    rules = resolved.get("rules", resolved.get("targets"))
    if (
        rules is None
        or isinstance(rules, (str, bytes))
        or not isinstance(rules, Sequence)
    ):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "Mixed target requires a 'rules' list of sub-targets.",
            {"rules_type": type(rules).__name__ if rules is not None else None},
        )
    if not rules:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "Mixed target requires a NON-EMPTY 'rules' list of sub-targets "
            "(an empty list matches nobody; drop the target or name a rule).",
            {"strategy": "mixed"},
        )
    validated: list[dict[str, Any]] = []
    for rule in rules:
        if _is_blank(rule):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "Mixed target sub-rules must be target objects; a null/blank "
                "sub-rule would silently resolve to 'no restriction' (a covert "
                'broadcast). Use a bare top-level {"strategy": "broadcast"} '
                "if you mean everyone.",
                {"strategy": "mixed"},
            )
        sub = validate_target(rule)
        assert sub is not None  # _is_blank guard above makes None impossible
        if sub["strategy"] == "broadcast":
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "broadcast may not be nested inside a mixed target (a mixed "
                "containing broadcast IS a broadcast). Use a bare top-level "
                '{"strategy": "broadcast"} instead.',
                {"strategy": "mixed", "nested": "broadcast"},
            )
        validated.append(sub)
    return validated


def _validate_tag_selector(
    resolved: Mapping[str, Any],
) -> dict[str, list[str]] | list[dict[str, Any]]:
    """Validate a ``tag`` target's ``selector`` in FORM (existence is the
    application layer's catalog gate). Both selector forms are accepted -
    flat map and rich match-expression list."""
    if resolved.get("selector") is None:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "Target strategy 'tag' requires field 'selector'.",
            {"strategy": "tag", "missing_field": "selector"},
        )
    selector = validate_selector(resolved["selector"])
    if selector is None:
        # {} normalises to allow-all - which would silently be a broadcast.
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "tag target requires a NON-EMPTY selector (an empty selector "
            "would match every agent - use a bare "
            '{"strategy": "broadcast"} if you mean everyone).',
            {"strategy": "tag"},
        )
    return selector


def _validate_fallback_seconds(resolved: Mapping[str, Any]) -> Any:
    after = _require(resolved, "fallback_after_seconds", "direct_with_fallback")
    if isinstance(after, bool) or not isinstance(after, (int, float)) or after < 0:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "fallback_after_seconds must be a non-negative number.",
            {"fallback_after_seconds": after},
        )
    return after


def validate_target(target: Any, *, required: bool = False) -> dict[str, Any] | None:
    """Validate ``target`` against the FULL grammar; return its normalised dict.

    ``None``/blank -> ``None`` (no routing restriction), unless ``required``.
    The returned dict carries the normalised ``strategy`` token; ``mixed``
    sub-rules (and an explicit ``direct_with_fallback`` ``fallback``) are
    replaced by their recursively validated, normalised forms (the ``targets``
    alias is normalised to ``rules``). Does NOT decide eligibility - that is
    :func:`okto_nexus.domain.routing.is_agent_eligible`'s job at read time.

    Raises ``VALIDATION_ERROR`` for any structural problem (see module
    docstring for the per-strategy rules).
    """
    resolved = coerce_target(target, required=required)
    if resolved is None:
        return None
    strategy = _strategy_of(resolved)

    out = dict(resolved)
    out["strategy"] = strategy

    if strategy == "direct":
        _require(resolved, "agent_id", strategy)
    elif strategy == "role":
        _require(resolved, "role", strategy)
    elif strategy == "capability":
        out["capability"] = _validate_capability(resolved)
    elif strategy == "tag":
        out["selector"] = _validate_tag_selector(resolved)
    elif strategy == "mixed":
        out.pop("targets", None)
        out["rules"] = _validate_mixed_rules(resolved)
    elif strategy == "direct_with_fallback":
        _require(resolved, "agent_id", strategy)
        _validate_fallback_seconds(resolved)
        fallback = resolved.get("fallback")
        if fallback is not None:
            # An explicit fallback must itself be a valid target (broadcast is
            # fine here - it is the documented default).
            out["fallback"] = validate_target(fallback)
    # strategy == "broadcast": no required fields.
    return out


def iter_target_selectors(resolved: Any) -> Iterator[Any]:
    """Yield every ``tag`` selector inside a VALIDATED target descriptor.

    Walks nested ``mixed`` rules and an explicit ``direct_with_fallback``
    ``fallback``, so a write path can run the catalog EXISTENCE gate over the
    whole tree before routing anything. Selectors are yielded in whichever
    form they carry (flat map or rich expression list). Expects the
    normalised output of :func:`validate_target`; anything else yields
    nothing (never raises).
    """
    if not isinstance(resolved, Mapping):
        return
    strategy = resolved.get("strategy")
    if strategy == "tag":
        selector = resolved.get("selector")
        if isinstance(selector, Mapping) or (
            isinstance(selector, Sequence) and not isinstance(selector, (str, bytes))
        ):
            yield selector
    elif strategy == "mixed":
        for rule in resolved.get("rules") or []:
            yield from iter_target_selectors(rule)
    elif strategy == "direct_with_fallback":
        yield from iter_target_selectors(resolved.get("fallback"))


def iter_target_capabilities(resolved: Any) -> Iterator[str]:
    """Yield every capability NAME inside a VALIDATED target descriptor.

    Walks the ``capability`` strategy (single string or any-of list), nested
    ``mixed`` sub-rules and an explicit ``direct_with_fallback`` ``fallback``,
    so a write path can run the catalog EXISTENCE gate over the whole tree
    before routing anything (migration 014). Expects the normalised output of
    :func:`validate_target`; anything else yields nothing (never raises).
    """
    if not isinstance(resolved, Mapping):
        return
    strategy = resolved.get("strategy")
    if strategy == "capability":
        wanted = resolved.get("capability")
        if isinstance(wanted, str):
            yield wanted
        elif isinstance(wanted, Sequence) and not isinstance(wanted, (str, bytes)):
            for name in wanted:
                if isinstance(name, str):
                    yield name
    elif strategy == "mixed":
        for rule in resolved.get("rules") or []:
            yield from iter_target_capabilities(rule)
    elif strategy == "direct_with_fallback":
        yield from iter_target_capabilities(resolved.get("fallback"))


def is_direct_target(target: Any, agent_id: str) -> bool:
    """Return whether ``agent_id`` is the *direct* named recipient of ``target``.

    Used by the pre-claim reject path (a ``direct`` target may reject an OPEN
    handoff before claiming it). Only the ``direct`` strategy qualifies; any
    malformed/other descriptor returns ``False`` (never raises).
    """
    if not agent_id:
        return False
    try:
        resolved = coerce_target(target, required=True)
    except OktoNexusError:
        return False
    raw = resolved.get("strategy", resolved.get("kind"))
    if raw is None:
        return False
    token = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    if token != "direct":
        return False
    return str(resolved.get("agent_id")) == str(agent_id)
