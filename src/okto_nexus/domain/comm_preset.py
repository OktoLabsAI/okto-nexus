"""Pure domain core for COMMUNICATION PRESETS (spec 6f961722).

A *communication preset* is the 4th per-agent axis, ORTHOGONAL to the three the
Nexus already owns (``comm_scope`` = WHO an agent may reach, ``permissions`` =
WHAT it may do, ``policy`` = audience+governance). It carries a self-descriptive
COMMUNICATION STYLE that tells the agent HOW it should communicate, surfaced
SELF-ONLY on ``whoami`` (never on any discovery surface).

Its *content* is a CLOSED set of style dimensions with FREE string values:

* ``tone`` / ``format`` / ``language`` / ``verbosity`` / ``structure`` - short
  structured labels; and
* ``additional_instructions`` - a free-text note.

Any key outside that closed set is rejected fail-closed; an EMPTY content object
is valid (a preset that says nothing).

A preset is attached to an agent by a SINGLE-SOURCE binding - this is the
deliberate divergence from :mod:`.policy` (whose bindings compose N globals with
AND): a communication binding is either

* ``inline`` - the content is embedded on the agent; or
* ``global`` - a reference to a named, append-only VERSIONED preset, with a
  ``mode``: ``latest`` (follow the highest published version) or ``pinned``
  (freeze on ``pinned_version``).

never both, never many. An agent with NO binding keeps today's ``whoami`` byte
for byte (zero regression) - the preset only appears once attached.

This module is IO-free (stdlib + the error catalogue). It never imports
``sqlite3`` nor ``mcp`` (enforced by the import-boundary test). Persistence
(repos), the migration, the whoami wiring, REST/MCP surfaces and the dashboard
live in the outer layers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..errors import ErrorCode, OktoNexusError

__all__ = [
    "BINDING_SOURCE_INLINE",
    "BINDING_SOURCE_GLOBAL",
    "BINDING_SOURCES",
    "BINDING_MODE_LATEST",
    "BINDING_MODE_PINNED",
    "BINDING_MODES",
    "CONTENT_KEY_ORDER",
    "CONTENT_KEYS",
    "CommPresetVersion",
    "CommPresetRecord",
    "CommBinding",
    "validate_content_form",
    "validate_preset_header_form",
    "validate_preset_version_form",
    "validate_comm_binding_form",
    "compose_comm_binding",
    "resolve_communication",
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

#: The CLOSED set of content dimensions, in canonical output order. The five
#: structured dimensions carry short labels; ``additional_instructions`` is a
#: free-text note. Iterating this tuple (never the frozenset) keeps a resolved
#: content dict deterministically ordered for stable JSON / tests.
CONTENT_KEY_ORDER: tuple[str, ...] = (
    "tone",
    "format",
    "language",
    "verbosity",
    "structure",
    "additional_instructions",
)
CONTENT_KEYS: frozenset[str] = frozenset(CONTENT_KEY_ORDER)

#: The free-text note dimension (a larger bound than the structured labels).
_NOTES_KEY = "additional_instructions"
#: Per-value length bounds (fail-closed; keeps a rogue payload from bloating the
#: resident whoami surface). Structured labels are short; the note is generous.
_STRUCTURED_VALUE_MAX = 500
_NOTES_VALUE_MAX = 4000

#: The only fields a binding object may carry.
_BINDING_FIELDS: frozenset[str] = frozenset(
    {"source", "preset_id", "mode", "pinned_version", "content"}
)
#: The only fields a preset's catalog header (metadata) may carry.
_HEADER_FIELDS: frozenset[str] = frozenset({"name", "description"})
#: Bounds on the header text (mirrors :mod:`.policy`).
_NAME_MAX = 200
_DESCRIPTION_MAX = 2000


# --------------------------------------------------------------------------- #
# Value objects
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CommPresetVersion:
    """One immutable, published version of a global communication preset.

    ``content`` is a validated, normalised subset of :data:`CONTENT_KEYS` with
    free string values (possibly empty ``{}``). ``version`` is a strictly
    increasing integer per preset; ``published_at`` fixes the ordering.
    """

    preset_id: str
    version: int
    content: dict[str, str]
    published_at: str


@dataclass(frozen=True)
class CommPresetRecord:
    """Catalog entry for a NAMED global preset (its versions live separately).

    ``latest_version`` is the highest published :class:`CommPresetVersion`
    number (0 when none published yet) - a read-surface convenience mirroring
    :class:`okto_nexus.domain.policy.PolicyRecord`.
    """

    preset_id: str
    name: str
    description: str | None
    created_at: str
    updated_at: str | None
    latest_version: int = 0


@dataclass(frozen=True)
class CommBinding:
    """The SINGLE communication binding of an agent (inline XOR a global ref).

    ``source == inline``: ``content`` carries the embedded style;
    ``preset_id``/``mode``/``pinned_version`` are ``None``.
    ``source == global``: ``preset_id`` + ``mode`` (+ ``pinned_version`` when
    ``mode == pinned``); ``content`` is unused.
    """

    source: str
    preset_id: str | None = None
    mode: str | None = None
    pinned_version: int | None = None
    content: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Form validation (fail-closed)
# --------------------------------------------------------------------------- #
def validate_content_form(content: Any) -> dict[str, str]:
    """Validate + normalise a preset's content; return the storable dict.

    Fail-closed: ``content`` is a JSON object whose keys are all in the CLOSED
    :data:`CONTENT_KEYS` and whose values are strings within the per-dimension
    length bound. ``None``/omitted or ``{}`` -> ``{}`` (an empty, non-directing
    preset is legal). Values are trimmed; a dimension whose trimmed value is
    empty is DROPPED (so a whitespace-only field never reaches ``whoami``). Keys
    are returned in :data:`CONTENT_KEY_ORDER` for deterministic output. Raises
    ``VALIDATION_ERROR`` for a non-object, an unknown dimension or a non-string
    / over-long value.
    """
    if content is None:
        return {}
    if not isinstance(content, Mapping):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "communication content must be a JSON object of style dimensions "
            '(e.g. {"tone": "concise", "language": "en"}), or null/omitted.',
            {"content": content, "type": type(content).__name__},
        )
    unknown = sorted(str(k) for k in content.keys() if k not in CONTENT_KEYS)
    if unknown:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"communication content contains unknown dimension(s): {unknown}. "
            f"Supported: {sorted(CONTENT_KEYS)}.",
            {"unknown": unknown, "supported": sorted(CONTENT_KEYS)},
        )
    normalised: dict[str, str] = {}
    for key in CONTENT_KEY_ORDER:
        if key not in content:
            continue
        value = content[key]
        if not isinstance(value, str):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"communication dimension {key!r} must be a string.",
                {"dimension": key, "value": value, "type": type(value).__name__},
            )
        max_len = _NOTES_VALUE_MAX if key == _NOTES_KEY else _STRUCTURED_VALUE_MAX
        if len(value) > max_len:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"communication dimension {key!r} must be at most {max_len} "
                "characters.",
                {"dimension": key, "max": max_len},
            )
        trimmed = value.strip()
        if trimmed:
            normalised[key] = trimmed
    return normalised


def validate_preset_header_form(
    *, name: Any, description: Any = None
) -> dict[str, Any]:
    """Validate + normalise a preset's metadata (``name`` + ``description``).

    ``name`` is REQUIRED (non-empty, trimmed, <= :data:`_NAME_MAX`);
    ``description`` is optional (``None`` or a string <= :data:`_DESCRIPTION_MAX`,
    whitespace normalising to ``None``). Uniqueness of ``name`` needs IO and is
    the application layer's job. Mirrors
    :func:`okto_nexus.domain.policy.validate_policy_header_form`.
    """
    if not isinstance(name, str) or not name.strip():
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "communication preset name is required (a non-empty string).",
            {"name": name},
        )
    trimmed = name.strip()
    if len(trimmed) > _NAME_MAX:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"communication preset name must be at most {_NAME_MAX} characters.",
            {"max": _NAME_MAX},
        )
    if description is None:
        normalised_description: str | None = None
    elif isinstance(description, str):
        if len(description) > _DESCRIPTION_MAX:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"communication preset description must be at most "
                f"{_DESCRIPTION_MAX} characters.",
                {"max": _DESCRIPTION_MAX},
            )
        normalised_description = description.strip() or None
    else:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "communication preset description must be a string or null.",
            {"description": description, "type": type(description).__name__},
        )
    return {"name": trimmed, "description": normalised_description}


def validate_preset_version_form(*, content: Any = None) -> dict[str, Any]:
    """Validate the FORM of a preset version body; return the storable dict.

    A version body is just ``content`` (validated by
    :func:`validate_content_form`); an empty version is legal. Raises
    ``VALIDATION_ERROR`` for any structural issue.
    """
    return {"content": validate_content_form(content)}


def validate_comm_binding_form(binding: Any) -> dict[str, Any]:
    """Validate + normalise ONE binding object; return the storable dict.

    Fail-closed: ``source`` must be in :data:`BINDING_SOURCES`; a global binding
    requires a non-empty ``preset_id`` and a ``mode`` in :data:`BINDING_MODES`
    (``pinned`` requires a positive-integer ``pinned_version``; ``latest``
    forbids it); an inline binding validates its embedded ``content`` via
    :func:`validate_content_form`. Unknown fields are rejected. Existence checks
    (preset_id/pinned_version registered) are the application layer's job.
    """
    if not isinstance(binding, Mapping):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            'a communication binding must be a JSON object, e.g. {"source": '
            '"global", "preset_id": "cpr_x", "mode": "latest"}.',
            {"binding": binding, "type": type(binding).__name__},
        )
    unknown = sorted(str(k) for k in binding.keys() if k not in _BINDING_FIELDS)
    if unknown:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"communication binding contains unknown field(s): {unknown}. "
            f"Supported: {sorted(_BINDING_FIELDS)}.",
            {"unknown": unknown, "supported": sorted(_BINDING_FIELDS)},
        )
    source = str(binding.get("source") or "").strip().lower()
    if source not in BINDING_SOURCES:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"communication binding source must be one of {sorted(BINDING_SOURCES)} "
            f"(got {binding.get('source')!r}).",
            {"source": binding.get("source"), "supported": sorted(BINDING_SOURCES)},
        )
    if source == BINDING_SOURCE_INLINE:
        return {
            "source": BINDING_SOURCE_INLINE,
            "content": validate_content_form(binding.get("content")),
        }
    # global
    preset_id = str(binding.get("preset_id") or "").strip()
    if not preset_id:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "a global communication binding requires a non-empty preset_id.",
            {"binding": dict(binding)},
        )
    mode = str(binding.get("mode") or "").strip().lower()
    if mode not in BINDING_MODES:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"communication binding mode must be one of {sorted(BINDING_MODES)} "
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
            "preset_id": preset_id,
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
        "preset_id": preset_id,
        "mode": BINDING_MODE_LATEST,
    }


def compose_comm_binding(
    *, inline: Any = None, global_ref: Any = None
) -> dict[str, Any] | None:
    """Compose + validate the agent's SINGLE-SOURCE binding from its two inputs.

    ``inline`` is a bare content object (``{tone, ...}``); ``global_ref`` is a
    ``{preset_id, mode, pinned_version?}`` reference. Exactly ZERO or ONE may be
    given: BOTH -> ``VALIDATION_ERROR`` (the single-source rule, D-CP-2);
    NEITHER -> ``None`` (clear the binding). The chosen side is validated by
    :func:`validate_comm_binding_form`. Existence of a referenced preset/version
    is the application layer's job.
    """
    if inline is not None and global_ref is not None:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "a communication binding is single-source: provide inline content OR "
            "a global preset reference, not both.",
            {},
        )
    if inline is not None:
        return validate_comm_binding_form(
            {"source": BINDING_SOURCE_INLINE, "content": inline}
        )
    if global_ref is not None:
        if not isinstance(global_ref, Mapping):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "a global communication reference must be a JSON object with "
                "preset_id + mode.",
                {"global": global_ref, "type": type(global_ref).__name__},
            )
        return validate_comm_binding_form(
            {**global_ref, "source": BINDING_SOURCE_GLOBAL}
        )
    return None


# --------------------------------------------------------------------------- #
# Binding resolution -> the whoami block (pure, deterministic)
# --------------------------------------------------------------------------- #
def _binding_from_any(binding: Any) -> CommBinding | None:
    """Coerce a stored mapping / :class:`CommBinding` / ``None`` into a binding.

    Bindings persisted through :func:`validate_comm_binding_form` are trusted; a
    malformed shape simply resolves to nothing rather than raising on the read
    path.
    """
    if binding is None:
        return None
    if isinstance(binding, CommBinding):
        return binding
    if not isinstance(binding, Mapping):
        return None
    source = str(binding.get("source") or "").strip().lower()
    if source not in BINDING_SOURCES:
        return None
    content_raw = binding.get("content")
    content = dict(content_raw) if isinstance(content_raw, Mapping) else {}
    return CommBinding(
        source=source,
        preset_id=binding.get("preset_id"),
        mode=binding.get("mode"),
        pinned_version=binding.get("pinned_version"),
        content=content,
    )


def _resolve_version(
    versions: Sequence[CommPresetVersion],
    *,
    mode: str | None,
    pinned_version: int | None,
) -> CommPresetVersion | None:
    """Pick the version a global binding resolves to (``None`` if none apply).

    ``latest`` -> the highest ``version``; ``pinned`` -> the exact
    ``pinned_version``. A global with no published versions (or a pin that no
    longer resolves) contributes nothing. Mirrors
    :func:`okto_nexus.domain.policy._resolve_version`.
    """
    if not versions:
        return None
    if mode == BINDING_MODE_PINNED:
        for pv in versions:
            if pv.version == pinned_version:
                return pv
        return None
    return max(versions, key=lambda pv: pv.version)


def resolve_communication(
    binding: Any,
    versions_by_preset: Mapping[str, Sequence[CommPresetVersion]] | None = None,
) -> dict[str, Any] | None:
    """Resolve an agent's binding to its ``whoami`` communication block, or ``None``.

    The block shape (BR11) is exactly ``{"source": <label>, "content": <dict>}``
    and NOTHING else:

    * inline -> ``source == "inline"``, ``content`` = the embedded style (always
      resolves, even when empty - an inline binding is a deliberate state);
    * global latest/pinned -> ``source == "<preset_id>@<version>"``, ``content``
      = that immutable version's content; a ``latest`` with no published version
      or a ``pinned`` whose version no longer exists resolves to ``None``.

    ``None`` (no binding, or an unresolvable global) means ``whoami`` OMITS the
    block entirely - an agent without a preset stays byte-identical to the
    pre-feature surface (zero regression). Pure and deterministic; never raises.
    """
    b = _binding_from_any(binding)
    if b is None:
        return None
    if b.source == BINDING_SOURCE_INLINE:
        return {"source": BINDING_SOURCE_INLINE, "content": dict(b.content)}
    if not b.preset_id:
        return None
    versions = (versions_by_preset or {}).get(b.preset_id) or ()
    chosen = _resolve_version(versions, mode=b.mode, pinned_version=b.pinned_version)
    if chosen is None:
        return None
    return {
        "source": f"{b.preset_id}@{chosen.version}",
        "content": dict(chosen.content),
    }
