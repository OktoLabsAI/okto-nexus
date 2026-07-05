"""Agent communication permissions (pure domain).

The Pulse permission grammar adapted to the Nexus communication domain:

* a nested ``{group: {flag: bool}}`` registry of boolean capabilities plus a
  small set of *quantitative* limits for fine-tuning communication;
* built-in presets (Full access / Coordinator / Worker / Observer) defined in
  CODE - custom presets live in the ``permission_presets`` table and are
  managed by the operator through the dashboard;
* a :class:`PermissionSet` resolver with **default-allow** semantics: an
  absent flag (or a ``NULL`` permissions column) reads as allowed, so every
  pre-existing agent keeps working unchanged after migration 011.

Strictly side-effect-free: stdlib + the error catalogue only (the import
boundary test enforces this). Enforcement happens in the APPLICATION layer
(:mod:`okto_nexus.application.permissions`), never in transport adapters, so
stdio MCP, HTTP MCP and REST inherit identical rules by construction.
"""

from __future__ import annotations

import copy
from typing import Any

from ..errors import ErrorCode, OktoNexusError

#: Canonical registry: every known boolean flag with its default (True =
#: allowed). ``limits`` carries the quantitative knobs (0 = unlimited).
#:
#: REMOVED in F1 (tag scoping): ``messages.allowed_peers``. Directed-send
#: allowlists are now the tag-based ``comm_scope.outbound`` audience selector
#: on the agent (operator-set; see the Tag Registry). New payloads carrying
#: ``allowed_peers`` are rejected as an unknown flag (fail-closed); rows
#: persisted by older versions are INERT - no code reads the key, and no data
#: migration rewrites them.
PERMISSION_REGISTRY: dict[str, dict[str, Any]] = {
    "messages": {
        "send_direct": True,
        "send_broadcast": True,
        "send_channel": True,
    },
    "handoffs": {
        "create": True,
        "work": True,
        "cancel": True,
    },
    "channels": {
        "create": True,
    },
    "artifacts": {
        "put": True,
    },
    "events": {
        "read": True,
    },
    "limits": {
        "messages_per_minute": 0,
        "max_recipients": 0,
    },
}

#: Human descriptions surfaced by the API for the dashboard editor.
PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "messages.send_direct": "Send direct messages to a specific agent.",
    "messages.send_broadcast": "Fan out to groups: broadcast, by role or by capability.",
    "messages.send_channel": "Post messages into channels.",
    "handoffs.create": "Offer work to the pool (handoff_create).",
    "handoffs.work": "Claim, complete or reject handoffs.",
    "handoffs.cancel": "Cancel handoffs it created.",
    "channels.create": "Create new channels.",
    "artifacts.put": "Publish artifacts.",
    "events.read": "Read or wait on the workspace event stream (event_get / event_wait).",
    "limits.messages_per_minute": "Max messages this agent may send per minute (0 = unlimited).",
    "limits.max_recipients": "Max recipients a single group send may fan out to (0 = unlimited).",
}


def _registry_copy() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(PERMISSION_REGISTRY)


def _preset(
    flags_off: list[str], limits: dict[str, int] | None = None
) -> dict[str, Any]:
    """Build a preset's flags: the full registry with ``flags_off`` disabled."""
    flags = _registry_copy()
    for path in flags_off:
        group, flag = path.split(".", 1)
        flags[group][flag] = False
    for key, value in (limits or {}).items():
        flags["limits"][key] = value
    return flags


#: Built-in presets (Pulse pattern: defined in code, read-only, clonable).
#: ``preset_id`` values are stable strings so an agent row can reference them.
BUILTIN_PRESETS: list[dict[str, Any]] = [
    {
        "preset_id": "builtin:full",
        "name": "Full access",
        "description": "Unrestricted: every communication capability enabled (the default for new agents).",
        "is_builtin": True,
        "flags": _registry_copy(),
    },
    {
        "preset_id": "builtin:coordinator",
        "name": "Coordinator",
        "description": "Orchestrates the swarm: everything enabled, including broadcasts, handoff creation and cancellation.",
        "is_builtin": True,
        "flags": _registry_copy(),
    },
    {
        "preset_id": "builtin:worker",
        "name": "Worker",
        "description": "Executes work: direct messages and handoff claim/complete only - no broadcasts, no handoff creation or cancellation, no channel creation.",
        "is_builtin": True,
        "flags": _preset(
            [
                "messages.send_broadcast",
                "handoffs.create",
                "handoffs.cancel",
                "channels.create",
            ]
        ),
    },
    {
        "preset_id": "builtin:observer",
        "name": "Observer",
        "description": "Read-only: watches the event stream but sends nothing and never touches handoffs or artifacts.",
        "is_builtin": True,
        "flags": _preset(
            [
                "messages.send_direct",
                "messages.send_broadcast",
                "messages.send_channel",
                "handoffs.create",
                "handoffs.work",
                "handoffs.cancel",
                "channels.create",
                "artifacts.put",
            ]
        ),
    },
]


def builtin_preset(preset_id: Any) -> dict[str, Any] | None:
    """Return the built-in preset payload for ``preset_id`` (or ``None``)."""
    for preset in BUILTIN_PRESETS:
        if preset["preset_id"] == preset_id:
            return copy.deepcopy(preset)
    return None


def validate_permission_flags(flags: Any) -> dict[str, dict[str, Any]]:
    """Validate a user-supplied flags mapping against the registry.

    Unknown groups/flags and wrong value types raise ``VALIDATION_ERROR``
    (fail-closed: a typo silently granting everything via default-allow is
    exactly the failure mode this rejects). A PARTIAL mapping is fine - the
    resolver treats absent flags as their defaults. Returns a normalised
    deep copy safe to persist.
    """
    if not isinstance(flags, dict):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "permissions must be an object of {group: {flag: value}}.",
            {"permissions": flags},
        )
    normalised: dict[str, dict[str, Any]] = {}
    for group, entries in flags.items():
        if group not in PERMISSION_REGISTRY:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"Unknown permission group '{group}'.",
                {"group": group, "known_groups": sorted(PERMISSION_REGISTRY)},
            )
        if not isinstance(entries, dict):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"Permission group '{group}' must be an object of flags.",
                {"group": group},
            )
        normalised[group] = {}
        for flag, value in entries.items():
            if flag not in PERMISSION_REGISTRY[group]:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"Unknown permission flag '{group}.{flag}'.",
                    {
                        "flag": f"{group}.{flag}",
                        "known_flags": sorted(PERMISSION_REGISTRY[group]),
                    },
                )
            default = PERMISSION_REGISTRY[group][flag]
            if isinstance(default, bool):
                if not isinstance(value, bool):
                    raise OktoNexusError(
                        ErrorCode.VALIDATION_ERROR,
                        f"'{group}.{flag}' must be a boolean.",
                        {"flag": f"{group}.{flag}", "value": value},
                    )
                normalised[group][flag] = value
            else:  # int (the quantitative limits)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise OktoNexusError(
                        ErrorCode.VALIDATION_ERROR,
                        f"'{group}.{flag}' must be a non-negative integer (0 = unlimited).",
                        {"flag": f"{group}.{flag}", "value": value},
                    )
                normalised[group][flag] = value
    return normalised


class PermissionSet:
    """Resolved permissions for one agent, with default-allow semantics."""

    __slots__ = ("_flags",)

    def __init__(self, flags: dict[str, Any] | None) -> None:
        self._flags = flags or {}

    def allows(self, group: str, flag: str) -> bool:
        """``True`` unless the flag is explicitly stored as ``False``."""
        value = self._flags.get(group, {}).get(flag)
        if value is None:
            return True
        return bool(value)

    def limit(self, name: str) -> int:
        """Quantitative limit (``0`` = unlimited / absent)."""
        value = self._flags.get("limits", {}).get(name, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return 0
        return value

    def denial(self, group: str, flag: str) -> OktoNexusError:
        """Build the canonical PERMISSION_DENIED error for ``group.flag``."""
        path = f"{group}.{flag}"
        return OktoNexusError(
            ErrorCode.PERMISSION_DENIED,
            f"Agent does not have the '{path}' permission. "
            "An operator can grant it on the dashboard (Agents -> Permissions).",
            {"required_permission": path},
        )

    def require(self, group: str, flag: str) -> None:
        """Raise ``PERMISSION_DENIED`` unless ``group.flag`` is allowed."""
        if not self.allows(group, flag):
            raise self.denial(group, flag)
