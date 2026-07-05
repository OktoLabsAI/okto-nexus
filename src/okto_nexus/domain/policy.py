"""Pure domain core for ATTACHABLE, VERSIONED policies (spec 80624c1a).

A *policy* unifies the two per-agent control axes the Nexus already owns into
one versionable object:

* **audience** - the tag ``comm_scope`` grammar (:mod:`.tag_selector`): an
  ``{outbound?, inbound?}`` envelope of selectors bounding whom the agent may
  reach / who may reach it.
* **governance** - the deny / quota / require_approval rules
  (:mod:`.governance`), here SUBJECT-LESS: the attachment (binding) IS the
  subject, so a rule is only ``{action, limit_kind, limit_value?, window?}``.

A policy is attached to an agent by a *binding*, in one of two sources:

* ``inline`` - the audience+governance are embedded on the agent (this is
  where the migrated ``comm_scope`` lands: audience = old comm_scope,
  governance = []). At most one inline binding per agent.
* ``global`` - a reference to a named, append-only VERSIONED policy, with a
  ``mode``: ``latest`` (follow the highest published version) or ``pinned``
  (freeze on ``pinned_version``). An agent may hold N global bindings.

**Composition is intersection (AND), fail-safe.** The effective sources of an
agent (its resolved globals + its inline) compose so that attaching a policy
can only ever NARROW: for audience a target passes only if it satisfies EVERY
source that declares that leg; for governance the union of all rules is run
through the existing :func:`governance.decide` (deny beats quota beats
require_approval, first violated in deterministic order wins). An agent with NO
bindings keeps today's behaviour exactly (zero regression) - the policy only
bites once attached.

This module is IO-free (stdlib + the sibling pure modules + the error
catalogue). It never imports ``sqlite3`` nor ``mcp`` (enforced by the
import-boundary test). Persistence (repos), the migration, the enforcement
wiring, REST/MCP surfaces and the dashboard live in the outer layers.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from . import governance
from .tag_selector import (
    scope_selector,
    selector_matches,
    validate_comm_scope,
)
from ..errors import ErrorCode, OktoNexusError

__all__ = [
    "BINDING_SOURCE_INLINE",
    "BINDING_SOURCE_GLOBAL",
    "BINDING_SOURCES",
    "BINDING_MODE_LATEST",
    "BINDING_MODE_PINNED",
    "BINDING_MODES",
    "AUDIENCE_LEGS",
    "PolicyVersion",
    "PolicyRecord",
    "Binding",
    "EffectiveSource",
    "validate_policy_rule_form",
    "validate_policy_version_form",
    "validate_policy_header_form",
    "validate_binding_form",
    "validate_agent_bindings",
    "resolve_effective_sources",
    "audience_permits",
    "audience_reachable",
    "outbound_snapshot",
    "snapshot_permits",
    "snapshot_to_selector",
    "effective_governance_policies",
    "combined_governance_verdict",
    "effective_policy_labels",
]


# --------------------------------------------------------------------------- #
# Closed vocabularies (fail-closed on any value outside them)
# --------------------------------------------------------------------------- #
BINDING_SOURCE_INLINE = "inline"
BINDING_SOURCE_GLOBAL = "global"
BINDING_SOURCES: frozenset[str] = frozenset(
    {BINDING_SOURCE_INLINE, BINDING_SOURCE_GLOBAL}
)

BINDING_MODE_LATEST = "latest"
BINDING_MODE_PINNED = "pinned"
BINDING_MODES: frozenset[str] = frozenset({BINDING_MODE_LATEST, BINDING_MODE_PINNED})

#: The two audience directions a policy version may declare (same names as
#: ``comm_scope``): ``outbound`` = whom the holder may reach, ``inbound`` =
#: who may reach the holder.
AUDIENCE_LEGS: tuple[str, str] = ("outbound", "inbound")

#: The only fields a governance rule (subject-less) may carry.
_RULE_FIELDS: frozenset[str] = frozenset(
    {"action", "limit_kind", "limit_value", "window"}
)
#: The only fields a binding object may carry.
_BINDING_FIELDS: frozenset[str] = frozenset(
    {"source", "policy_id", "mode", "pinned_version", "audience", "governance"}
)
#: A synthetic subject value for the star subject the effective governance
#: policies carry (the binding is the real subject, so every rule matches the
#: acting agent unconditionally).
_SYNTH_SUBJECT = "*"
#: Sentinel ``published_at`` for the inline source so it orders FIRST and
#: deterministically among the effective sources.
_INLINE_PUBLISHED_AT = ""


# --------------------------------------------------------------------------- #
# Value objects
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PolicyVersion:
    """One immutable, published version of a global policy.

    ``audience`` is a validated ``comm_scope`` envelope (``{outbound?,
    inbound?}``) or ``None``; ``governance`` is a tuple of validated
    subject-less rule dicts. ``version`` is a strictly increasing integer per
    policy; ``published_at`` fixes the deterministic ordering.
    """

    policy_id: str
    version: int
    audience: dict[str, Any] | None
    governance: tuple[dict[str, Any], ...]
    published_at: str


@dataclass(frozen=True)
class PolicyRecord:
    """Catalog entry for a NAMED global policy (its versions live separately).

    The mutable metadata of a global policy: ``name`` (unique) + ``description``.
    ``latest_version`` is the highest published :class:`PolicyVersion` number (0
    when none has been published yet) - a read-surface convenience so the
    catalog can show "at v3" without a second round-trip. The versions
    themselves are append-only and fetched via the policy repo.
    """

    policy_id: str
    name: str
    description: str | None
    created_at: str
    updated_at: str | None
    latest_version: int = 0


@dataclass(frozen=True)
class Binding:
    """One attachment of a policy to an agent (inline OR a global reference).

    ``source == inline``: ``audience``/``governance`` carry the embedded
    policy; ``policy_id``/``mode``/``pinned_version`` are ``None``.
    ``source == global``: ``policy_id`` + ``mode`` (+ ``pinned_version`` when
    ``mode == pinned``); ``audience``/``governance`` are unused.
    """

    source: str
    policy_id: str | None = None
    mode: str | None = None
    pinned_version: int | None = None
    audience: dict[str, Any] | None = None
    governance: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class EffectiveSource:
    """A resolved source contributing audience + governance to composition.

    Produced by :func:`resolve_effective_sources`. ``label`` is the audit
    handle (``"<policy_id>@<version>"`` for a global, ``"inline"`` for the
    inline source) reported back to the operator; ``published_at`` and
    ``version`` fix the deterministic ordering.
    """

    audience: dict[str, Any] | None
    governance: tuple[dict[str, Any], ...]
    policy_id: str
    version: int | None
    published_at: str
    label: str

    #: Ordering key: (published_at, policy_id, version). The inline source
    #: (published_at "") sorts first; ``version`` None is treated as -1.
    @property
    def order_key(self) -> tuple[str, str, int]:
        return (self.published_at, self.policy_id, self.version or -1)


# --------------------------------------------------------------------------- #
# Form validation (fail-closed) - reuses the sibling pure validators
# --------------------------------------------------------------------------- #
def validate_policy_rule_form(rule: Any) -> dict[str, Any]:
    """Validate + normalise ONE subject-less governance rule.

    Reuses :func:`governance.validate_policy_form` (with the star subject) for
    the closed-vocabulary + window + limit_value checks, then strips the
    subject fields - the binding is the subject. Unknown fields on the rule are
    rejected fail-closed. Raises ``VALIDATION_ERROR`` for any structural issue.
    """
    if not isinstance(rule, Mapping):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            'a governance rule must be a JSON object, e.g. {"action": '
            '"message_create", "limit_kind": "deny"}.',
            {"rule": rule, "type": type(rule).__name__},
        )
    unknown = sorted(str(k) for k in rule.keys() if k not in _RULE_FIELDS)
    if unknown:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"governance rule contains unknown field(s): {unknown}. Supported: "
            f"{sorted(_RULE_FIELDS)}.",
            {"unknown": unknown, "supported": sorted(_RULE_FIELDS)},
        )
    fields = governance.validate_policy_form(
        subject_kind=governance.SUBJECT_STAR,
        action=rule.get("action"),
        limit_kind=rule.get("limit_kind"),
        limit_value=rule.get("limit_value"),
        window=rule.get("window"),
    )
    return {
        "action": fields["action"],
        "limit_kind": fields["limit_kind"],
        "limit_value": fields["limit_value"],
        "window": fields["window"],
    }


def validate_policy_version_form(
    *, audience: Any = None, governance: Any = None
) -> dict[str, Any]:
    """Validate the FORM of a policy version body; return the storable dict.

    ``audience`` is validated by :func:`tag_selector.validate_comm_scope`
    (``{outbound?, inbound?}`` or ``None``); ``governance`` is a list of
    subject-less rules each validated by :func:`validate_policy_rule_form`.
    A version with no audience and no rules is legal (an empty, non-restricting
    version). Raises ``VALIDATION_ERROR`` for any structural issue.
    """
    normalised_audience = validate_comm_scope(audience)
    rules_in: Sequence[Any]
    if governance is None:
        rules_in = []
    elif isinstance(governance, Sequence) and not isinstance(
        governance, (str, bytes, bytearray)
    ):
        rules_in = list(governance)
    else:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "governance must be a list of rule objects (or null/omitted).",
            {"governance": governance, "type": type(governance).__name__},
        )
    rules = [validate_policy_rule_form(rule) for rule in rules_in]
    return {"audience": normalised_audience, "governance": rules}


#: The only fields a NAMED policy's catalog header (metadata) may carry.
_POLICY_HEADER_FIELDS: frozenset[str] = frozenset({"name", "description"})
#: Bounds on the header text (fail-closed; keeps a rogue payload from bloating
#: the catalog). The name is the unique operator handle; the description is a
#: free note.
_POLICY_NAME_MAX = 200
_POLICY_DESCRIPTION_MAX = 2000


def validate_policy_header_form(
    *, name: Any, description: Any = None
) -> dict[str, Any]:
    """Validate + normalise a named policy's metadata (``name`` + ``description``).

    ``name`` is REQUIRED: a non-empty string (trimmed) of at most
    :data:`_POLICY_NAME_MAX` chars. ``description`` is optional: ``None`` or a
    string of at most :data:`_POLICY_DESCRIPTION_MAX` chars (an empty/whitespace
    value normalises to ``None``). Raises ``VALIDATION_ERROR`` fail-closed for
    any structural issue. Uniqueness of ``name`` needs IO and is the application
    layer's job (a duplicate is a ``VALIDATION_ERROR`` there).
    """
    if not isinstance(name, str) or not name.strip():
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "policy name is required (a non-empty string).",
            {"name": name},
        )
    trimmed = name.strip()
    if len(trimmed) > _POLICY_NAME_MAX:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"policy name must be at most {_POLICY_NAME_MAX} characters.",
            {"max": _POLICY_NAME_MAX},
        )
    if description is None:
        normalised_description: str | None = None
    elif isinstance(description, str):
        if len(description) > _POLICY_DESCRIPTION_MAX:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"policy description must be at most {_POLICY_DESCRIPTION_MAX} "
                "characters.",
                {"max": _POLICY_DESCRIPTION_MAX},
            )
        normalised_description = description.strip() or None
    else:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "policy description must be a string or null.",
            {"description": description, "type": type(description).__name__},
        )
    return {"name": trimmed, "description": normalised_description}


def validate_binding_form(binding: Any) -> dict[str, Any]:
    """Validate + normalise ONE binding object; return the storable dict.

    Fail-closed: ``source`` must be in :data:`BINDING_SOURCES`; a global
    binding requires a non-empty ``policy_id`` and a ``mode`` in
    :data:`BINDING_MODES` (``pinned`` requires a positive-integer
    ``pinned_version``; ``latest`` forbids it); an inline binding validates its
    embedded ``audience``/``governance`` via
    :func:`validate_policy_version_form`. Unknown fields are rejected.
    Existence checks (policy_id/pinned_version registered) are the application
    layer's job.
    """
    if not isinstance(binding, Mapping):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            'a binding must be a JSON object, e.g. {"source": "global", '
            '"policy_id": "pol_x", "mode": "latest"}.',
            {"binding": binding, "type": type(binding).__name__},
        )
    unknown = sorted(str(k) for k in binding.keys() if k not in _BINDING_FIELDS)
    if unknown:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"binding contains unknown field(s): {unknown}. Supported: "
            f"{sorted(_BINDING_FIELDS)}.",
            {"unknown": unknown, "supported": sorted(_BINDING_FIELDS)},
        )
    source = str(binding.get("source") or "").strip().lower()
    if source not in BINDING_SOURCES:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"binding source must be one of {sorted(BINDING_SOURCES)} "
            f"(got {binding.get('source')!r}).",
            {"source": binding.get("source"), "supported": sorted(BINDING_SOURCES)},
        )
    if source == BINDING_SOURCE_INLINE:
        body = validate_policy_version_form(
            audience=binding.get("audience"),
            governance=binding.get("governance"),
        )
        return {
            "source": BINDING_SOURCE_INLINE,
            "audience": body["audience"],
            "governance": body["governance"],
        }
    # global
    policy_id = str(binding.get("policy_id") or "").strip()
    if not policy_id:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "a global binding requires a non-empty policy_id.",
            {"binding": dict(binding)},
        )
    mode = str(binding.get("mode") or "").strip().lower()
    if mode not in BINDING_MODES:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"binding mode must be one of {sorted(BINDING_MODES)} "
            f"(got {binding.get('mode')!r}).",
            {"mode": binding.get("mode"), "supported": sorted(BINDING_MODES)},
        )
    if mode == BINDING_MODE_PINNED:
        raw = binding.get("pinned_version")
        if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "mode=pinned requires a positive-integer pinned_version.",
                {"pinned_version": raw},
            )
        return {
            "source": BINDING_SOURCE_GLOBAL,
            "policy_id": policy_id,
            "mode": BINDING_MODE_PINNED,
            "pinned_version": raw,
        }
    if binding.get("pinned_version") is not None:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "pinned_version is only allowed for mode=pinned.",
            {"mode": mode, "pinned_version": binding.get("pinned_version")},
        )
    return {
        "source": BINDING_SOURCE_GLOBAL,
        "policy_id": policy_id,
        "mode": BINDING_MODE_LATEST,
    }


def validate_agent_bindings(bindings: Any) -> list[dict[str, Any]]:
    """Validate the FULL set of an agent's bindings; return the storable list.

    ``None``/empty -> ``[]`` (no bindings = today's behaviour). Each element is
    validated by :func:`validate_binding_form`; AT MOST one inline binding is
    allowed (a second inline is rejected fail-closed). Order is preserved.
    """
    if bindings is None:
        return []
    if not (
        isinstance(bindings, Sequence)
        and not isinstance(bindings, (str, bytes, bytearray))
    ):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "bindings must be a list of binding objects (or null/omitted).",
            {"bindings": bindings, "type": type(bindings).__name__},
        )
    out: list[dict[str, Any]] = []
    inline_seen = False
    for binding in bindings:
        normalised = validate_binding_form(binding)
        if normalised["source"] == BINDING_SOURCE_INLINE:
            if inline_seen:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    "at most one inline binding is allowed per agent.",
                    {},
                )
            inline_seen = True
        out.append(normalised)
    return out


# --------------------------------------------------------------------------- #
# Binding resolution -> effective sources (pure, deterministic)
# --------------------------------------------------------------------------- #
def _binding_from_any(binding: Any) -> Binding:
    """Coerce a mapping / :class:`Binding` into a :class:`Binding` (read-path).

    Bindings persisted through :func:`validate_agent_bindings` are trusted; a
    malformed shape simply produces an inert source rather than raising on the
    read path.
    """
    if isinstance(binding, Binding):
        return binding
    if not isinstance(binding, Mapping):
        return Binding(source=BINDING_SOURCE_INLINE)
    governance_raw = binding.get("governance") or ()
    return Binding(
        source=str(binding.get("source") or BINDING_SOURCE_INLINE),
        policy_id=binding.get("policy_id"),
        mode=binding.get("mode"),
        pinned_version=binding.get("pinned_version"),
        audience=binding.get("audience"),
        governance=tuple(governance_raw),
    )


def _resolve_version(
    versions: Sequence[PolicyVersion], *, mode: str | None, pinned_version: int | None
) -> PolicyVersion | None:
    """Pick the version a global binding resolves to (``None`` if none apply).

    ``latest`` -> the highest ``version``; ``pinned`` -> the exact
    ``pinned_version``. A global with no published versions (or a pin that no
    longer resolves) contributes nothing.
    """
    if not versions:
        return None
    if mode == BINDING_MODE_PINNED:
        for pv in versions:
            if pv.version == pinned_version:
                return pv
        return None
    return max(versions, key=lambda pv: pv.version)


def resolve_effective_sources(
    bindings: Iterable[Any],
    versions_by_policy: Mapping[str, Sequence[PolicyVersion]],
) -> list[EffectiveSource]:
    """Resolve an agent's bindings to its ordered list of effective sources.

    ``versions_by_policy`` maps each referenced global ``policy_id`` to its
    published versions. Each global binding resolves via :func:`_resolve_version`
    (latest -> highest; pinned -> exact); each inline binding becomes a source
    directly. The result is ordered deterministically by
    ``(published_at, policy_id, version)`` - the inline source first - so the
    downstream governance union is stable and auditable.
    """
    sources: list[EffectiveSource] = []
    for raw in bindings:
        binding = _binding_from_any(raw)
        if binding.source == BINDING_SOURCE_INLINE:
            sources.append(
                EffectiveSource(
                    audience=binding.audience,
                    governance=tuple(binding.governance),
                    policy_id=BINDING_SOURCE_INLINE,
                    version=None,
                    published_at=_INLINE_PUBLISHED_AT,
                    label=BINDING_SOURCE_INLINE,
                )
            )
            continue
        if not binding.policy_id:
            continue
        versions = versions_by_policy.get(binding.policy_id) or ()
        chosen = _resolve_version(
            versions, mode=binding.mode, pinned_version=binding.pinned_version
        )
        if chosen is None:
            continue
        sources.append(
            EffectiveSource(
                audience=chosen.audience,
                governance=tuple(chosen.governance),
                policy_id=chosen.policy_id,
                version=chosen.version,
                published_at=chosen.published_at,
                label=f"{chosen.policy_id}@{chosen.version}",
            )
        )
    sources.sort(key=lambda s: s.order_key)
    return sources


def effective_policy_labels(sources: Iterable[EffectiveSource]) -> list[str]:
    """The audit labels (``policy_id@version`` / ``inline``) of the sources.

    The whoami / binding-summary surfaces report THIS (never the selector
    contents) so an agent sees which policies apply without leaking audience.
    """
    return [source.label for source in sources]


# --------------------------------------------------------------------------- #
# Audience composition (AND, fail-safe) - reuses selector_matches
# --------------------------------------------------------------------------- #
def _source_permits(source: EffectiveSource, leg: str, target_tags: Any) -> bool:
    """Whether ONE source permits ``target_tags`` on ``leg``.

    A source that does not declare the leg (no selector) does not restrict -
    :func:`selector_matches` treats ``None`` as allow-all.
    """
    selector = scope_selector(source.audience, leg)
    return selector_matches(selector, target_tags)


def audience_permits(
    sources: Iterable[EffectiveSource], leg: str, target_tags: Any
) -> bool:
    """Whether ALL sources permit ``target_tags`` on ``leg`` (AND, fail-safe).

    The target passes only if it satisfies EVERY source that declares the leg;
    a source without the leg does not restrict. With no sources the answer is
    ``True`` (no bindings = unrestricted = today's behaviour).
    """
    return all(_source_permits(source, leg, target_tags) for source in sources)


def audience_reachable(
    *,
    sender_sources: Iterable[EffectiveSource],
    sender_tags: Any,
    sender_id: Any = None,
    recipient_sources: Iterable[EffectiveSource],
    recipient_tags: Any,
    recipient_id: Any = None,
) -> bool:
    """Policy-aware analogue of :func:`tag_selector.reachable`.

    ``sender`` reaches ``recipient`` iff the sender's OUTBOUND sources permit
    the recipient's tags AND the recipient's INBOUND sources permit the
    sender's tags. Self carve-out: equal, present ids always reach. With no
    bindings on either side this reduces to unrestricted reachability.
    """
    if (
        sender_id is not None
        and recipient_id is not None
        and str(sender_id) == str(recipient_id)
    ):
        return True
    return audience_permits(
        sender_sources, "outbound", recipient_tags
    ) and audience_permits(recipient_sources, "inbound", sender_tags)


# --------------------------------------------------------------------------- #
# Artifact audience snapshot (D10/D11) - immutable outbound capture
# --------------------------------------------------------------------------- #
def outbound_snapshot(sources: Iterable[EffectiveSource]) -> list[Any]:
    """Freeze the publisher's EFFECTIVE OUTBOUND as an ordered selector list.

    One entry per source that declares an ``outbound`` selector, in source
    order. An empty list means "no outbound restriction" (public). Stored
    verbatim as ``artifacts.audience`` at ``artifact_put`` time; the AND is
    re-evaluated against a reader's tags by :func:`snapshot_permits`.
    """
    snapshot: list[Any] = []
    for source in sources:
        selector = scope_selector(source.audience, "outbound")
        if selector is not None:
            snapshot.append(selector)
    return snapshot


def snapshot_permits(snapshot: Any, reader_tags: Any) -> bool:
    """Whether ``reader_tags`` satisfy a frozen artifact-audience snapshot.

    ``None``/empty snapshot (legacy rows, or a publisher with no outbound
    restriction) -> ``True`` (public / default-allow). Otherwise every selector
    in the snapshot must match the reader (AND). Never raises.
    """
    if not snapshot:
        return True
    if not isinstance(snapshot, Sequence) or isinstance(
        snapshot, (str, bytes, bytearray)
    ):
        return True
    return all(selector_matches(selector, reader_tags) for selector in snapshot)


def _selector_expressions(selector: Any) -> list[dict[str, Any]]:
    """Rewrite ONE selector (either form) as an equivalent match-expression list.

    A flat map ``{key: [values]}`` is In-sugar, so each entry becomes one
    canonical ``{"key", "operator": "In", "values"}`` expression; a rich list is
    passed through verbatim (its expressions are already ANDed). ``None``/empty
    or a malformed shape contributes nothing. This is the read-time inverse used
    to fold a multi-selector AND into a single selector for event routing; it
    never validates (existence + form were checked at write time) and never
    raises.
    """
    if not selector:
        return []
    if isinstance(selector, Mapping):
        out: list[dict[str, Any]] = []
        for key, values in selector.items():
            vals = [values] if isinstance(values, str) else list(values)
            out.append({"key": str(key), "operator": "In", "values": vals})
        return out
    if isinstance(selector, Sequence) and not isinstance(
        selector, (str, bytes, bytearray)
    ):
        return [dict(expr) for expr in selector if isinstance(expr, Mapping)]
    return []


def snapshot_to_selector(snapshot: Any) -> list[dict[str, Any]] | None:
    """Fold an artifact-audience snapshot (AND of N selectors) into ONE selector.

    Returns a single RICH-form selector (list of match expressions) equivalent
    to the whole snapshot: :func:`selector_matches` of the result is bit-for-bit
    the AND :func:`snapshot_permits` computes, because the rich form ANDs its
    expressions and the flat form is In-sugar for exactly those expressions.
    ``None``/empty snapshot (public / legacy) -> ``None`` (no restriction). This
    lets an ``artifact.created`` event carry the SAME audience as the artifact
    via a plain ``tag`` target - no new routing strategy, no lossy collapse
    (BR7 - the stream never leaks what the read-path hides). Never raises.
    """
    if (
        not snapshot
        or not isinstance(snapshot, Sequence)
        or isinstance(snapshot, (str, bytes, bytearray))
    ):
        return None
    expressions: list[dict[str, Any]] = []
    for selector in snapshot:
        expressions.extend(_selector_expressions(selector))
    return expressions or None


# --------------------------------------------------------------------------- #
# Governance composition (union, deterministic) - reuses governance.decide
# --------------------------------------------------------------------------- #
def _synth_policy_id(source: EffectiveSource, rule_index: int) -> str:
    """Stable, unique id for one effective rule (also the ``usage`` key).

    Encodes provenance so the winning verdict is reportable as the policy that
    barred (``<label>#r<index>``).
    """
    return f"{source.label}#r{rule_index}"


def effective_governance_policies(
    sources: Iterable[EffectiveSource], action: str
) -> list[governance.Policy]:
    """The union of the sources' rules matching ``action``, deterministically.

    Every source rule becomes a synthetic star-subject :class:`governance.Policy`
    (the binding is the subject, so it always matches the acting agent), kept
    only when :func:`governance.action_matches` covers ``action``. The result is
    ordered ``(published_at, policy_id, version, rule_index)`` - the source
    order (already sorted) nested by rule index - so :func:`governance.decide`
    reports the FIRST violated rule stably. Each policy's ``policy_id`` is the
    synthetic key the caller fills ``usage`` under.
    """
    act = str(action).strip().lower()
    out: list[governance.Policy] = []
    for source in sources:
        for rule_index, rule in enumerate(source.governance):
            if not isinstance(rule, Mapping):
                continue
            rule_action = str(rule.get("action") or "").strip().lower()
            if not governance.action_matches(rule_action, act):
                continue
            out.append(
                governance.Policy(
                    policy_id=_synth_policy_id(source, rule_index),
                    subject_kind=governance.SUBJECT_STAR,
                    subject_value=_SYNTH_SUBJECT,
                    action=rule_action,
                    limit_kind=str(rule.get("limit_kind") or "").strip().lower(),
                    limit_value=rule.get("limit_value"),
                    window=rule.get("window"),
                    enabled=True,
                    created_at=source.published_at,
                )
            )
    return out


def combined_governance_verdict(
    sources: Iterable[EffectiveSource],
    *,
    action: str,
    size_bytes: int,
    usage: Mapping[str, int],
) -> governance.Violation | governance.ApprovalRequired | None:
    """Run the composed governance union through :func:`governance.decide`.

    ``sources`` are the agent's effective sources; ``usage`` maps each
    count-based synthetic policy id (see :func:`effective_governance_policies`)
    to the caller's pre-fetched consumption for that rule's ``(action,
    window)`` - the application fetches these inside the SAME UoW as the write
    path. A missing count for a count-rule raises ``KeyError`` (never fails
    open), exactly like :func:`governance.decide`. Returns the winning verdict
    or ``None`` (allow). With no sources / no matching rules the answer is
    ``None`` - an agent without bindings is never governed.
    """
    policies = effective_governance_policies(sources, action)
    return governance.decide(policies, size_bytes=size_bytes, usage=usage)
