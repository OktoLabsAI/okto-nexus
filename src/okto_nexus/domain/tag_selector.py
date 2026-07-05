"""Single source of truth for the tag / tag-selector GRAMMAR (migrations 013+).

FORM lives here; EXISTENCE lives in the application layer. This module
validates the SHAPE of an agent's ``tags`` map, of a tag ``selector``, and of
the operator-set ``comm_scope`` envelope - it never consults the central tag
catalog (``TagCatalogService`` performs the fail-closed existence check on
every write path before these values persist).

Grammar (F1 flat form + F3 rich match-expression form)::

    tags        {key: [value, ...]}     multi-value map; keys and values are
                                        non-empty, case-sensitive strings.
                                        Tags are ALWAYS flat - expressions
                                        exist only on the selector side.
    selector    {key: [value, ...]}     FLAT form: sugar for one In expression
                                        per key (AND across keys, OR within a
                                        key's values)
                [{"key": K,             RICH form (Kubernetes matchExpressions
                  "operator": Op,       parity): Op is one of In | NotIn |
                  "values": [...]},     Exists | DoesNotExist; AND across the
                 ...]                   expressions of the list. In/NotIn
                                        REQUIRE a non-empty ``values`` list;
                                        Exists/DoesNotExist FORBID it.
    comm_scope  {"outbound": <selector or null>,
                 "inbound": <selector or null>}
                                        outbound = "whom may I reach";
                                        inbound = "who may reach me" (F2).
                                        Each direction accepts either form.

Matching semantics (:func:`selector_matches`): a ``None``/empty selector
matches EVERY agent (allow-all - the default that keeps pre-existing agents
working); string comparison is case-sensitive. Per expression, against the
agent's values under ``key`` (multi-value intersection):

    In            key present AND tags[key] intersects ``values``
    NotIn         key ABSENT, or tags[key] does not intersect ``values``
    Exists        key present (``values`` forbidden)
    DoesNotExist  key absent (``values`` forbidden)

K8s-parity absence trap: NotIn and DoesNotExist MATCH agents that lack the
key entirely - a lone negative selector matches every untagged agent.
Compose with Exists ("has the key AND is not X") to require the key.

Hierarchical values (F3): a value containing ``/`` is a path; matching is
SEGMENT-wise - selector value ``ENG`` covers tags ``ENG`` and ``ENG/BACKEND``
but never ``ENGX`` (each ``/``-segment must be equal; this is not a string
prefix). Applies to the intersection of In and NotIn (``NotIn ENG`` excludes
the whole ``ENG/*`` subtree) and equally to the flat form (In sugar). There
is no inheritance across different KEYS.

Reachability (:func:`reachable`, F2): sender reaches recipient iff the
sender's ``outbound`` matches the recipient's tags AND the recipient's
``inbound`` matches the sender's tags - the double intersection every
communication surface (messages, handoffs, discovery, event stream) shares.
An agent always reaches itself (self carve-out).

Strictly side-effect free (stdlib + the error catalogue only); never imports
``sqlite3`` nor ``mcp`` (enforced by the import-boundary test).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from ..errors import ErrorCode, OktoNexusError

__all__ = [
    "COMM_SCOPE_DIRECTIONS",
    "EXPRESSION_OPERATORS",
    "iter_pairs",
    "iter_selector_keys",
    "iter_selector_pairs",
    "reachable",
    "scope_selector",
    "selector_matches",
    "validate_comm_scope",
    "validate_selector",
    "validate_tags",
]

#: The closed set of comm_scope directions: ``outbound`` ("whom may I reach")
#: and ``inbound`` ("who may reach me"). Unknown directions are rejected
#: fail-closed - a misspelling must never silently mean "unrestricted".
COMM_SCOPE_DIRECTIONS: frozenset[str] = frozenset({"outbound", "inbound"})

#: The closed set of match-expression operators (Kubernetes matchExpressions
#: parity). Case-sensitive; anything else is rejected fail-closed.
EXPRESSION_OPERATORS: frozenset[str] = frozenset(
    {"In", "NotIn", "Exists", "DoesNotExist"}
)

#: Operators that REQUIRE a non-empty ``values`` list.
_VALUE_OPERATORS: frozenset[str] = frozenset({"In", "NotIn"})
#: Operators that FORBID ``values`` (presence checks carry no values).
_PRESENCE_OPERATORS: frozenset[str] = frozenset({"Exists", "DoesNotExist"})
#: The only fields a match expression may carry (unknown fields are rejected
#: fail-closed - a typo like "vaules" must never silently widen a selector).
_EXPRESSION_FIELDS: frozenset[str] = frozenset({"key", "operator", "values"})


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_listish(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )


def _validate_tag_map(value: Any, *, field: str) -> dict[str, list[str]]:
    """Shared shape validator for ``tags`` and flat ``selector`` maps.

    Both are ``{key: [value, ...]}``: non-empty string keys, each mapping to a
    NON-EMPTY list of non-empty strings (a bare string is accepted and
    normalised to a one-element list; an empty list is rejected - it can never
    match anything and would silently deaden the entry). Values are
    de-duplicated preserving first-seen order. Keys and values are
    case-sensitive and stored exactly as given (stripped).
    """
    if not isinstance(value, Mapping):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{field} must be a JSON object mapping tag keys to value lists, "
            'e.g. {"team": ["backend"]}.',
            {field: value, "type": type(value).__name__},
        )
    out: dict[str, list[str]] = {}
    for raw_key, raw_values in value.items():
        if _is_blank(raw_key) or not isinstance(raw_key, str):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field} keys must be non-empty strings.",
                {"key": raw_key},
            )
        key = raw_key.strip()
        values = _validate_value_list(raw_values, label=f"{field}[{key!r}]", key=key)
        if key in out:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field} contains duplicate key {key!r} after normalisation.",
                {"key": key},
            )
        out[key] = values
    return out


def _validate_value_list(raw_values: Any, *, label: str, key: str) -> list[str]:
    """Normalise one tag-value list: bare string accepted, non-empty strings
    only, de-duplicated preserving first-seen order."""
    if isinstance(raw_values, str):
        candidates: Sequence[Any] = [raw_values]
    elif _is_listish(raw_values):
        candidates = list(raw_values)
    else:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{label} must be a list of tag values (or a single string).",
            {"key": key, "type": type(raw_values).__name__},
        )
    if not candidates:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{label} must not be an empty list: an empty value "
            "list can never match anything. Drop the key or name at least "
            "one value.",
            {"key": key},
        )
    values: list[str] = []
    for raw in candidates:
        if _is_blank(raw) or not isinstance(raw, str):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{label} values must be non-empty strings.",
                {"key": key, "value": raw},
            )
        candidate = raw.strip()
        if candidate not in values:
            values.append(candidate)
    return values


def _validate_expression(expr: Any, *, field: str, index: int) -> dict[str, Any]:
    """Validate ONE match expression; return its normalised form.

    Canonical shape: ``{"key": K, "operator": Op}`` for Exists/DoesNotExist,
    plus ``"values": [...]`` for In/NotIn. Unknown fields, unknown operators,
    a blank key, values on a presence operator, or missing/empty values on
    In/NotIn are all rejected fail-closed with ``VALIDATION_ERROR``.
    """
    label = f"{field}[{index}]"
    if not isinstance(expr, Mapping):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{label} must be a match-expression object, e.g. "
            '{"key": "team", "operator": "In", "values": ["backend"]}.',
            {"index": index, "type": type(expr).__name__},
        )
    unknown = sorted(str(k) for k in expr.keys() if k not in _EXPRESSION_FIELDS)
    if unknown:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{label} contains unknown field(s): {unknown}. Supported: "
            f"{sorted(_EXPRESSION_FIELDS)}.",
            {"index": index, "unknown": unknown},
        )
    raw_key = expr.get("key")
    if _is_blank(raw_key) or not isinstance(raw_key, str):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{label} requires a non-empty string 'key'.",
            {"index": index, "key": raw_key},
        )
    key = raw_key.strip()
    raw_operator = expr.get("operator")
    operator = raw_operator.strip() if isinstance(raw_operator, str) else raw_operator
    if operator not in EXPRESSION_OPERATORS:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{label} has unknown operator {raw_operator!r}. Supported "
            f"(case-sensitive): {sorted(EXPRESSION_OPERATORS)}.",
            {
                "index": index,
                "operator": raw_operator,
                "supported": sorted(EXPRESSION_OPERATORS),
            },
        )
    raw_values = expr.get("values")
    if operator in _PRESENCE_OPERATORS:
        if raw_values is not None and not (_is_listish(raw_values) and not raw_values):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{label}: operator {operator!r} is a presence check and "
                "FORBIDS 'values'. Drop the values list (use In/NotIn to "
                "match specific values).",
                {"index": index, "operator": operator, "values": raw_values},
            )
        return {"key": key, "operator": operator}
    if raw_values is None:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{label}: operator {operator!r} REQUIRES a non-empty 'values' "
            "list (use Exists/DoesNotExist for bare presence checks).",
            {"index": index, "operator": operator},
        )
    values = _validate_value_list(raw_values, label=f"{label}.values", key=key)
    return {"key": key, "operator": operator, "values": values}


def validate_tags(tags: Any) -> dict[str, list[str]] | None:
    """Validate an agent ``tags`` map; return its normalised form.

    ``None`` -> ``None`` (no tags - the reset value). An empty mapping is
    normalised to ``None`` as well: "no tags" has exactly one representation.
    Tags are ALWAYS flat (match expressions exist only on the selector side).
    Raises ``VALIDATION_ERROR`` for any structural problem.
    """
    if tags is None:
        return None
    normalised = _validate_tag_map(tags, field="tags")
    return normalised or None


def validate_selector(
    selector: Any,
) -> dict[str, list[str]] | list[dict[str, Any]] | None:
    """Validate a tag ``selector`` in EITHER form; return its normalised form.

    ``None``/empty mapping/empty expression list -> ``None`` (allow-all:
    matches every agent). A mapping validates as the FLAT form (each entry is
    sugar for one In expression); a list validates as the RICH form (each
    element a match expression - see :func:`_validate_expression`). Each form
    normalises to itself: flat stays a mapping (F1/F2 byte-compatibility),
    rich stays a list of canonical expressions. Raises ``VALIDATION_ERROR``
    for any structural problem.
    """
    if selector is None:
        return None
    if isinstance(selector, Mapping):
        return _validate_tag_map(selector, field="selector") or None
    if _is_listish(selector):
        normalised = [
            _validate_expression(expr, field="selector", index=index)
            for index, expr in enumerate(selector)
        ]
        return normalised or None
    raise OktoNexusError(
        ErrorCode.VALIDATION_ERROR,
        'selector must be a flat tag map ({"team": ["backend"]}) or a list '
        'of match expressions ([{"key": "team", "operator": "In", '
        '"values": ["backend"]}]).',
        {"selector": selector, "type": type(selector).__name__},
    )


def validate_comm_scope(comm_scope: Any) -> dict[str, Any] | None:
    """Validate the operator-set ``comm_scope`` envelope; return it normalised.

    ``None``/empty mapping -> ``None`` (unrestricted). Only the directions in
    :data:`COMM_SCOPE_DIRECTIONS` are accepted (unknown keys are rejected
    fail-closed - a misspelled direction must never silently mean
    "unrestricted"). Each direction is a selector (flat or rich form) or
    ``null``: ``outbound`` bounds whom the agent may reach, ``inbound`` bounds
    who may reach the agent (F2). An envelope whose directions are all
    ``null`` normalises to ``None``; a direction that validates to ``None``
    is dropped so "no restriction" has exactly one representation.
    """
    if comm_scope is None:
        return None
    if not isinstance(comm_scope, Mapping):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            'comm_scope must be a JSON object, e.g. {"outbound": {"team": '
            '["backend"]}} - or null for unrestricted.',
            {"comm_scope": comm_scope, "type": type(comm_scope).__name__},
        )
    unknown = sorted(
        str(k) for k in comm_scope.keys() if k not in COMM_SCOPE_DIRECTIONS
    )
    if unknown:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"comm_scope contains unknown direction(s): {unknown}. Supported: "
            f"{sorted(COMM_SCOPE_DIRECTIONS)}.",
            {"unknown": unknown, "supported": sorted(COMM_SCOPE_DIRECTIONS)},
        )
    normalised: dict[str, Any] = {}
    for direction in ("outbound", "inbound"):
        selector = validate_selector(comm_scope.get(direction))
        if selector is not None:
            normalised[direction] = selector
    return normalised or None


def scope_selector(comm_scope: Any, direction: str) -> Any:
    """Extract one direction's selector from a (validated) ``comm_scope``.

    ``None`` means "no restriction on this direction": an unset scope, a
    non-mapping value, or a direction that is absent/null. Read-path only -
    the envelope was validated fail-closed at write time.
    """
    if not isinstance(comm_scope, Mapping):
        return None
    return comm_scope.get(direction)


def _participant_field(participant: Any, key: str) -> Any:
    if isinstance(participant, Mapping):
        return participant.get(key)
    return getattr(participant, key, None)


def reachable(sender: Any, recipient: Any) -> bool:
    """Decide whether ``sender`` may communicate with ``recipient`` (F2).

    The single double-intersection predicate every surface shares::

        selector_matches(sender.comm_scope.outbound, recipient.tags)
        AND selector_matches(recipient.comm_scope.inbound, sender.tags)

    Both participants are duck-typed (mapping or object) carrying
    ``agent_id``, ``tags`` and ``comm_scope``. Self carve-out: when both ids
    are present and equal the answer is always ``True`` - an agent reaches
    itself regardless of its own selectors. Missing selectors permit their
    side (default-allow); like :func:`selector_matches` this never raises.
    """
    sender_id = _participant_field(sender, "agent_id")
    recipient_id = _participant_field(recipient, "agent_id")
    if (
        sender_id is not None
        and recipient_id is not None
        and str(sender_id) == str(recipient_id)
    ):
        return True
    outbound = scope_selector(_participant_field(sender, "comm_scope"), "outbound")
    inbound = scope_selector(_participant_field(recipient, "comm_scope"), "inbound")
    return selector_matches(
        outbound, _participant_field(recipient, "tags")
    ) and selector_matches(inbound, _participant_field(sender, "tags"))


def _value_covers(wanted: str, have: str) -> bool:
    """Whether tag value ``have`` sits inside selector value ``wanted``'s
    subtree - SEGMENT-wise path comparison, never a string prefix.

    ``ENG`` covers ``ENG`` and ``ENG/BACKEND`` but not ``ENGX``; every
    ``/``-segment of ``wanted`` must equal the corresponding segment of
    ``have``. Case-sensitive.
    """
    wanted_segments = wanted.split("/")
    have_segments = have.split("/")
    return (
        len(wanted_segments) <= len(have_segments)
        and have_segments[: len(wanted_segments)] == wanted_segments
    )


def _hierarchical_intersects(wanted_values: Any, have_values: Any) -> bool:
    """Non-empty hierarchical intersection: some selector value covers some
    agent value (non-strings never match)."""
    return any(
        _value_covers(wanted, have)
        for wanted in wanted_values
        if isinstance(wanted, str)
        for have in have_values
        if isinstance(have, str)
    )


def _tag_values(tags: Any, key: str) -> list[Any] | None:
    """The agent's values under ``key`` - ``None`` when the key is ABSENT.

    Presence is what the absence-sensitive operators (NotIn, Exists,
    DoesNotExist) branch on; a key whose value is not list-shaped is treated
    as absent (impossible after write-path validation - defensive only).
    """
    if not isinstance(tags, Mapping) or key not in tags:
        return None
    raw = tags.get(key)
    if isinstance(raw, str):
        return [raw]
    if _is_listish(raw):
        return list(raw)
    return None


def _match_expression(expression: Mapping[str, Any], tags: Any) -> bool:
    """Evaluate ONE match expression against an agent's tags (truth table).

    K8s absence parity: NotIn and DoesNotExist MATCH when the key is absent.
    Malformed expressions never match (fail-closed at read); never raises.
    """
    key = expression.get("key")
    operator = expression.get("operator")
    if not isinstance(key, str) or operator not in EXPRESSION_OPERATORS:
        return False
    have = _tag_values(tags, key)
    if operator == "Exists":
        return have is not None
    if operator == "DoesNotExist":
        return have is None
    wanted = expression.get("values")
    if isinstance(wanted, str):
        wanted_values: Sequence[Any] = [wanted]
    elif _is_listish(wanted):
        wanted_values = wanted
    else:
        return False
    if operator == "In":
        return have is not None and _hierarchical_intersects(wanted_values, have)
    # NotIn: an absent key MATCHES (K8s parity); otherwise the hierarchical
    # intersection must be empty (NotIn ENG excludes the whole ENG/* subtree).
    return have is None or not _hierarchical_intersects(wanted_values, have)


def selector_matches(selector: Any, tags: Any) -> bool:
    """Decide whether an agent's ``tags`` satisfy ``selector`` (read time).

    Accepts BOTH selector forms. The flat form is In sugar: AND across keys,
    per key a non-empty hierarchical intersection with the wanted values
    (OR). The rich form ANDs its match expressions (truth table in the module
    docstring - NotIn/DoesNotExist match agents missing the key). A ``None``/
    empty selector matches everyone. Values containing ``/`` match by path
    segment (``ENG`` covers ``ENG/BACKEND``). Both sides are expected in
    their validated forms; comparison is exact (case-sensitive). Never raises
    - a malformed side simply does not match (except the allow-all cases
    above).
    """
    if not selector:
        return True
    if isinstance(selector, Mapping):
        return all(
            _match_expression({"key": key, "operator": "In", "values": wanted}, tags)
            for key, wanted in selector.items()
        )
    if _is_listish(selector):
        return all(
            isinstance(expression, Mapping) and _match_expression(expression, tags)
            for expression in selector
        )
    return False


def iter_pairs(mapping: Any) -> Iterator[tuple[str, str]]:
    """Yield every ``(key, value)`` pair of a validated FLAT tags/selector map.

    The existence-check helper for flat maps (agent ``tags`` are always
    flat): the application layer feeds these pairs to the central tag
    catalog. Tolerant of ``None`` (yields nothing) so callers can pass
    optional fields straight through. For selectors that may carry the rich
    form use :func:`iter_selector_keys` / :func:`iter_selector_pairs`.
    """
    if not isinstance(mapping, Mapping):
        return
    for key, values in mapping.items():
        if isinstance(values, str):
            yield (str(key), values)
            continue
        if isinstance(values, Sequence) and not isinstance(values, (bytes, bytearray)):
            for value in values:
                yield (str(key), str(value))


def iter_selector_keys(selector: Any) -> Iterator[str]:
    """Yield every tag KEY a validated selector references (either form).

    Feeds the catalog existence gate: EVERY expression's key must be
    registered - including Exists/DoesNotExist, which carry no values.
    Tolerant of ``None``/malformed input (yields nothing; never raises).
    """
    if isinstance(selector, Mapping):
        for key in selector.keys():
            yield str(key)
        return
    if not _is_listish(selector):
        return
    for expression in selector:
        if isinstance(expression, Mapping) and not _is_blank(expression.get("key")):
            yield str(expression["key"])


def iter_selector_pairs(selector: Any) -> Iterator[tuple[str, str]]:
    """Yield every ``(key, value)`` PAIR a validated selector references.

    Flat form: every pair (same as :func:`iter_pairs`). Rich form: only
    In/NotIn contribute pairs - Exists/DoesNotExist are presence checks and
    carry no values (their keys surface via :func:`iter_selector_keys`).
    Tolerant of ``None``/malformed input (yields nothing; never raises).
    """
    if isinstance(selector, Mapping):
        yield from iter_pairs(selector)
        return
    if not _is_listish(selector):
        return
    for expression in selector:
        if not isinstance(expression, Mapping) or _is_blank(expression.get("key")):
            continue
        if expression.get("operator") not in _VALUE_OPERATORS:
            continue
        key = str(expression["key"])
        values = expression.get("values")
        if isinstance(values, str):
            yield (key, values)
        elif isinstance(values, Sequence) and not isinstance(
            values, (bytes, bytearray)
        ):
            for value in values:
                yield (key, str(value))
