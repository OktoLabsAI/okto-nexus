"""Pure domain core for communication guardrails and agent groups.

Guardrails are table-owned controls for Nexus communication writes. They are
separate from the legacy ``governance_policies`` and the attachable
``policies`` catalog: a guardrail has immutable evaluator config versions, and
assignments attach those versions either globally or to explicit agent groups.

Groups are rosters, not tags. A group contains concrete agent ids and does not
participate in tag discovery or routing.

This module is IO-free and never imports ``sqlite3`` nor ``mcp``. Persistence,
admin APIs, MCP tools and dashboard surfaces live in outer layers.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..errors import ErrorCode, OktoNexusError

__all__ = [
    "VERSION_STATUS_DRAFT",
    "VERSION_STATUS_ACTIVE",
    "VERSION_STATUS_DEPRECATED",
    "VERSION_STATUS_ARCHIVED",
    "VERSION_STATUSES",
    "EVALUATOR_KIND_DETERMINISTIC",
    "EVALUATOR_KIND_LLM",
    "EVALUATOR_KINDS",
    "SURFACES",
    "SCOPE_KIND_GLOBAL",
    "SCOPE_KIND_AGENT_GROUP",
    "SCOPE_KIND_CAPABILITY",
    "SCOPE_KINDS",
    "VERSION_MODE_LATEST",
    "VERSION_MODE_PINNED",
    "VERSION_MODES",
    "ENFORCEMENT_MODE_AUDIT",
    "ENFORCEMENT_MODE_WARN",
    "ENFORCEMENT_MODE_ENFORCE",
    "ENFORCEMENT_MODES",
    "RESOLUTION_RESOLVED",
    "RESOLUTION_CONFIG_UNAVAILABLE",
    "AgentGroupRecord",
    "AgentGroupMember",
    "GuardrailRecord",
    "GuardrailVersion",
    "GuardrailAssignment",
    "EffectiveGuardrail",
    "validate_group_header_form",
    "validate_guardrail_header_form",
    "validate_guardrail_version_form",
    "validate_guardrail_assignment_form",
    "latest_active_version",
    "resolve_assignment_version",
    "resolve_effective_guardrails",
]


# --------------------------------------------------------------------------- #
# Closed vocabularies
# --------------------------------------------------------------------------- #
VERSION_STATUS_DRAFT = "draft"
VERSION_STATUS_ACTIVE = "active"
VERSION_STATUS_DEPRECATED = "deprecated"
VERSION_STATUS_ARCHIVED = "archived"
VERSION_STATUSES: frozenset[str] = frozenset(
    {
        VERSION_STATUS_DRAFT,
        VERSION_STATUS_ACTIVE,
        VERSION_STATUS_DEPRECATED,
        VERSION_STATUS_ARCHIVED,
    }
)

EVALUATOR_KIND_DETERMINISTIC = "deterministic"
EVALUATOR_KIND_LLM = "llm"
EVALUATOR_KINDS: frozenset[str] = frozenset(
    {EVALUATOR_KIND_DETERMINISTIC, EVALUATOR_KIND_LLM}
)

SURFACES: frozenset[str] = frozenset({"message", "artifact", "handoff"})

SCOPE_KIND_GLOBAL = "global"
SCOPE_KIND_AGENT_GROUP = "agent_group"
SCOPE_KIND_CAPABILITY = "capability"
SCOPE_KINDS: frozenset[str] = frozenset(
    {SCOPE_KIND_GLOBAL, SCOPE_KIND_AGENT_GROUP, SCOPE_KIND_CAPABILITY}
)

VERSION_MODE_LATEST = "latest"
VERSION_MODE_PINNED = "pinned"
VERSION_MODES: frozenset[str] = frozenset({VERSION_MODE_LATEST, VERSION_MODE_PINNED})

ENFORCEMENT_MODE_AUDIT = "audit"
ENFORCEMENT_MODE_WARN = "warn"
ENFORCEMENT_MODE_ENFORCE = "enforce"
ENFORCEMENT_MODES: frozenset[str] = frozenset(
    {ENFORCEMENT_MODE_AUDIT, ENFORCEMENT_MODE_WARN, ENFORCEMENT_MODE_ENFORCE}
)

_DETERMINISTIC_KINDS: frozenset[str] = frozenset(
    {
        "regex",
        "keyword_blocklist",
        "pii_detection",
        "schema_validation",
        "token_limit",
    }
)
_RUNTIME_DETERMINISTIC_KINDS: frozenset[str] = frozenset(
    {"regex", "keyword_blocklist", "pii_detection", "token_limit"}
)
_MAX_PATTERN_LENGTH = 1000
_SURFACE_FIELD_ROOTS: dict[str, frozenset[str]] = {
    "message": frozenset({"subject", "body"}),
    "artifact": frozenset({"artifact_type", "name", "content", "metadata", "path"}),
    "handoff": frozenset({"payload", "acceptance_criteria"}),
}

RESOLUTION_RESOLVED = "resolved"
RESOLUTION_CONFIG_UNAVAILABLE = "config_unavailable"

_NAME_MAX = 200
_DESCRIPTION_MAX = 2000
_FIELD_TARGET_MAX = 120


# --------------------------------------------------------------------------- #
# Value objects
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AgentGroupRecord:
    """Catalog entry for an explicit roster of agents."""

    group_id: str
    name: str
    description: str | None
    created_at: str
    updated_at: str | None


@dataclass(frozen=True)
class AgentGroupMember:
    """One agent membership row inside a group."""

    group_id: str
    agent_id: str
    created_at: str


@dataclass(frozen=True)
class GuardrailRecord:
    """Catalog entry for a named guardrail."""

    guardrail_id: str
    name: str
    description: str | None
    created_at: str
    updated_at: str | None
    latest_version: int = 0
    latest_active_version: int | None = None


@dataclass(frozen=True)
class GuardrailVersion:
    """One guardrail version.

    ``evaluator_config`` is the validated JSON payload consumed by the
    evaluator layer. ``surfaces`` selects communication write paths and
    ``field_targets`` selects payload fields within those surfaces.
    """

    guardrail_id: str
    version: int
    status: str
    evaluator_kind: str
    evaluator_config: dict[str, Any]
    surfaces: tuple[str, ...]
    field_targets: tuple[str, ...]
    created_at: str
    updated_at: str | None = None
    activated_at: str | None = None


@dataclass(frozen=True)
class GuardrailAssignment:
    """One assignment of a guardrail to global, group or capability scope."""

    assignment_id: str
    scope_kind: str
    group_id: str | None
    capability: str | None
    guardrail_id: str
    version_mode: str
    pinned_version: int | None
    mode: str
    priority: int
    enabled: bool
    created_at: str
    updated_at: str | None = None


@dataclass(frozen=True)
class EffectiveGuardrail:
    """Resolved assignment plus the version selected for runtime.

    ``version`` is ``None`` when the assignment is enabled but its configuration
    is unavailable. The evaluator/service layer decides whether that becomes an
    audit record, warning or fail-closed denial according to ``assignment.mode``.
    """

    assignment: GuardrailAssignment
    version: GuardrailVersion | None
    resolution_status: str
    reason: str | None = None


# --------------------------------------------------------------------------- #
# Form validation
# --------------------------------------------------------------------------- #
def _text(value: Any, *, field: str, required: bool, max_len: int) -> str | None:
    if value is None:
        if required:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field} is required.",
                {field: value},
            )
        return None
    if not isinstance(value, str):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{field} must be a string.",
            {field: value, "type": type(value).__name__},
        )
    trimmed = value.strip()
    if required and not trimmed:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{field} is required.",
            {field: value},
        )
    if len(trimmed) > max_len:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{field} must be at most {max_len} characters.",
            {"field": field, "max": max_len},
        )
    return trimmed or None


def _enum(value: Any, *, field: str, supported: frozenset[str]) -> str:
    text = str(value or "").strip().lower()
    if text not in supported:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{field} must be one of {sorted(supported)}.",
            {"field": field, "value": value, "supported": sorted(supported)},
        )
    return text


def _string_tuple(
    value: Any,
    *,
    field: str,
    supported: frozenset[str] | None = None,
    max_item_len: int = _FIELD_TARGET_MAX,
    lowercase: bool = True,
) -> tuple[str, ...]:
    if not (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
    ):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{field} must be a non-empty list of strings.",
            {"field": field, "value": value, "type": type(value).__name__},
        )
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item = _text(raw, field=field, required=True, max_len=max_item_len)
        assert item is not None  # for type-checkers; required=True above
        if lowercase:
            item = item.lower()
        if supported is not None and item not in supported:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field} contains unsupported value {item!r}.",
                {"field": field, "value": item, "supported": sorted(supported)},
            )
        if item not in seen:
            seen.add(item)
            out.append(item)
    if not out:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{field} must contain at least one value.",
            {"field": field},
        )
    return tuple(out)


def validate_group_header_form(*, name: Any, description: Any = None) -> dict[str, Any]:
    """Validate group metadata."""

    return {
        "name": _text(name, field="name", required=True, max_len=_NAME_MAX),
        "description": _text(
            description,
            field="description",
            required=False,
            max_len=_DESCRIPTION_MAX,
        ),
    }


def validate_guardrail_header_form(
    *, name: Any, description: Any = None
) -> dict[str, Any]:
    """Validate guardrail metadata."""

    return validate_group_header_form(name=name, description=description)


def validate_guardrail_version_form(
    *,
    status: Any = VERSION_STATUS_DRAFT,
    evaluator_kind: Any,
    evaluator_config: Any,
    surfaces: Any,
    field_targets: Any,
) -> dict[str, Any]:
    """Validate one guardrail version body.

    Deterministic guardrails follow the Omni Flow vocabulary through
    ``evaluator_config.kind``. LLM evaluators keep their provider/model prompt
    payload opaque to this slice; the evaluator card owns execution semantics.
    """

    normalised_status = _enum(status, field="status", supported=VERSION_STATUSES)
    normalised_kind = _enum(
        evaluator_kind,
        field="evaluator_kind",
        supported=EVALUATOR_KINDS,
    )
    if not isinstance(evaluator_config, Mapping):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "evaluator_config must be a JSON object.",
            {
                "evaluator_config": evaluator_config,
                "type": type(evaluator_config).__name__,
            },
        )
    config = dict(evaluator_config)
    if normalised_kind == EVALUATOR_KIND_DETERMINISTIC:
        kind = str(config.get("kind") or "").strip().lower()
        if kind not in _DETERMINISTIC_KINDS:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "deterministic evaluator_config.kind must be one of "
                f"{sorted(_DETERMINISTIC_KINDS)}.",
                {"kind": config.get("kind"), "supported": sorted(_DETERMINISTIC_KINDS)},
            )
        config["kind"] = kind
        if normalised_status == VERSION_STATUS_ACTIVE and kind not in _RUNTIME_DETERMINISTIC_KINDS:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{kind} guardrails cannot be activated because the runtime evaluator is unavailable.",
                {"kind": kind, "supported_active": sorted(_RUNTIME_DETERMINISTIC_KINDS)},
            )
        config = _validate_deterministic_config(kind, config)
    elif normalised_status == VERSION_STATUS_ACTIVE:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "LLM guardrails cannot be activated because the runtime evaluator is unavailable.",
            {"evaluator_kind": normalised_kind},
        )
    normalised_surfaces = _string_tuple(
        surfaces, field="surfaces", supported=SURFACES
    )
    normalised_targets = _string_tuple(field_targets, field="field_targets")
    _validate_field_targets(normalised_surfaces, normalised_targets)
    return {
        "status": normalised_status,
        "evaluator_kind": normalised_kind,
        "evaluator_config": config,
        "surfaces": normalised_surfaces,
        "field_targets": normalised_targets,
    }


def _validate_deterministic_config(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    """Validate evaluator-specific payloads before a version can be stored."""

    if kind in {"regex", "keyword_blocklist"}:
        field = "patterns" if kind == "regex" else "keywords"
        values = _string_tuple(
            config.get(field),
            field=f"evaluator_config.{field}",
            max_item_len=_MAX_PATTERN_LENGTH,
            lowercase=False,
        )
        if kind == "regex":
            for index, pattern in enumerate(values, start=1):
                try:
                    re.compile(pattern)
                except re.error as exc:
                    raise OktoNexusError(
                        ErrorCode.VALIDATION_ERROR,
                        f"Invalid regular expression at position {index}: {exc}.",
                        {"field": field, "index": index - 1, "pattern": pattern},
                    ) from exc
        config[field] = list(values)
        if kind == "regex" and "ignore_case" in config and not isinstance(
            config["ignore_case"], bool
        ):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "evaluator_config.ignore_case must be true or false.",
                {"ignore_case": config["ignore_case"]},
            )
    elif kind == "token_limit":
        limit = config.get("max_tokens")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "evaluator_config.max_tokens must be an integer greater than or equal to zero.",
                {"max_tokens": limit},
            )
    return config


def _validate_field_targets(
    surfaces: Sequence[str], field_targets: Sequence[str]
) -> None:
    """Require meaningful fields for every selected communication surface."""

    roots = {target.split(".", 1)[0] for target in field_targets}
    allowed = set().union(*(_SURFACE_FIELD_ROOTS[surface] for surface in surfaces))
    unsupported = sorted(roots - allowed)
    if unsupported:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"field_targets contains unsupported field(s): {', '.join(unsupported)}.",
            {"unsupported": unsupported, "supported": sorted(allowed)},
        )
    missing = [
        surface
        for surface in surfaces
        if roots.isdisjoint(_SURFACE_FIELD_ROOTS[surface])
    ]
    if missing:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "Every selected surface must have at least one compatible field target.",
            {"surfaces_without_fields": missing},
        )


def validate_guardrail_assignment_form(
    *,
    scope_kind: Any,
    group_id: Any = None,
    capability: Any = None,
    guardrail_id: Any,
    version_mode: Any = VERSION_MODE_LATEST,
    pinned_version: Any = None,
    mode: Any = ENFORCEMENT_MODE_AUDIT,
    priority: Any = 100,
    enabled: Any = True,
) -> dict[str, Any]:
    """Validate an assignment shape before persistence."""

    normalised_scope = _enum(scope_kind, field="scope_kind", supported=SCOPE_KINDS)
    normalised_group = _text(
        group_id,
        field="group_id",
        required=normalised_scope == SCOPE_KIND_AGENT_GROUP,
        max_len=_NAME_MAX,
    )
    normalised_capability = _text(
        capability,
        field="capability",
        required=normalised_scope == SCOPE_KIND_CAPABILITY,
        max_len=_NAME_MAX,
    )
    if normalised_scope != SCOPE_KIND_AGENT_GROUP and normalised_group is not None:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{normalised_scope} guardrail assignments must not set group_id.",
            {"scope_kind": normalised_scope, "group_id": group_id},
        )
    if normalised_scope != SCOPE_KIND_CAPABILITY and normalised_capability is not None:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"{normalised_scope} guardrail assignments must not set capability.",
            {"scope_kind": normalised_scope, "capability": capability},
        )
    normalised_guardrail = _text(
        guardrail_id,
        field="guardrail_id",
        required=True,
        max_len=_NAME_MAX,
    )
    normalised_version_mode = _enum(
        version_mode,
        field="version_mode",
        supported=VERSION_MODES,
    )
    pin: int | None = None
    if normalised_version_mode == VERSION_MODE_PINNED:
        if isinstance(pinned_version, bool) or not isinstance(pinned_version, int):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "mode=pinned requires a positive integer pinned_version.",
                {"pinned_version": pinned_version},
            )
        if pinned_version <= 0:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "mode=pinned requires a positive integer pinned_version.",
                {"pinned_version": pinned_version},
            )
        pin = pinned_version
    elif pinned_version is not None:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "pinned_version is only allowed for version_mode=pinned.",
            {"version_mode": normalised_version_mode, "pinned_version": pinned_version},
        )
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "priority must be an integer.",
            {"priority": priority, "type": type(priority).__name__},
        )
    if priority < 0:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "priority must be zero or greater.",
            {"priority": priority},
        )
    if not isinstance(enabled, bool):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "enabled must be a boolean.",
            {"enabled": enabled, "type": type(enabled).__name__},
        )
    return {
        "scope_kind": normalised_scope,
        "group_id": normalised_group,
        "capability": normalised_capability,
        "guardrail_id": normalised_guardrail,
        "version_mode": normalised_version_mode,
        "pinned_version": pin,
        "mode": _enum(mode, field="mode", supported=ENFORCEMENT_MODES),
        "priority": priority,
        "enabled": enabled,
    }


# --------------------------------------------------------------------------- #
# Effective resolution
# --------------------------------------------------------------------------- #
def latest_active_version(
    versions: Sequence[GuardrailVersion],
) -> GuardrailVersion | None:
    """Return the highest active version, or ``None`` if none is active."""

    active = [version for version in versions if version.status == VERSION_STATUS_ACTIVE]
    return max(active, key=lambda version: version.version) if active else None


def _pinned_version(
    versions: Sequence[GuardrailVersion], pinned_version: int | None
) -> GuardrailVersion | None:
    for version in versions:
        if version.version == pinned_version:
            return version
    return None


def resolve_assignment_version(
    assignment: GuardrailAssignment,
    versions: Sequence[GuardrailVersion],
) -> EffectiveGuardrail:
    """Resolve one assignment to its runtime version.

    Latest assignments pick the maximum ACTIVE version. Pinned assignments must
    still point at an ACTIVE version to resolve. Missing or non-active pins are
    surfaced as ``config_unavailable`` so the evaluator can fail closed under
    enforce mode.
    """

    if not assignment.enabled:
        return EffectiveGuardrail(
            assignment=assignment,
            version=None,
            resolution_status=RESOLUTION_CONFIG_UNAVAILABLE,
            reason="assignment_disabled",
        )
    if assignment.version_mode == VERSION_MODE_PINNED:
        chosen = _pinned_version(versions, assignment.pinned_version)
        if chosen is None:
            return EffectiveGuardrail(
                assignment=assignment,
                version=None,
                resolution_status=RESOLUTION_CONFIG_UNAVAILABLE,
                reason="pinned_version_missing",
            )
        if chosen.status != VERSION_STATUS_ACTIVE:
            return EffectiveGuardrail(
                assignment=assignment,
                version=None,
                resolution_status=RESOLUTION_CONFIG_UNAVAILABLE,
                reason="pinned_version_inactive",
            )
        return EffectiveGuardrail(
            assignment=assignment,
            version=chosen,
            resolution_status=RESOLUTION_RESOLVED,
        )
    chosen = latest_active_version(versions)
    if chosen is None:
        return EffectiveGuardrail(
            assignment=assignment,
            version=None,
            resolution_status=RESOLUTION_CONFIG_UNAVAILABLE,
            reason="no_active_version",
        )
    return EffectiveGuardrail(
        assignment=assignment,
        version=chosen,
        resolution_status=RESOLUTION_RESOLVED,
    )


def resolve_effective_guardrails(
    assignments: Iterable[GuardrailAssignment],
    versions_by_guardrail: Mapping[str, Sequence[GuardrailVersion]],
) -> list[EffectiveGuardrail]:
    """Resolve enabled assignments deterministically.

    Ordering is ``priority`` first, then guardrail id and assignment id. Disabled
    assignments are ignored on the effective read path.
    """

    out: list[EffectiveGuardrail] = []
    for assignment in assignments:
        if not assignment.enabled:
            continue
        versions = versions_by_guardrail.get(assignment.guardrail_id) or ()
        out.append(resolve_assignment_version(assignment, versions))
    out.sort(
        key=lambda item: (
            item.assignment.priority,
            item.assignment.guardrail_id,
            item.assignment.assignment_id,
        )
    )
    return out
