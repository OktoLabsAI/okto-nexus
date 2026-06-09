"""Pure domain rules for the Channels & Messages slice.

Strictly side-effect-free (stdlib only, never ``sqlite3``/``mcp`` - enforced by
the import-boundary test). This module owns:

* the seeded-channel vocabulary (only ``general`` - agents create the rest);
* the canonical event ``stream`` / ``type`` strings emitted for a new message;
* input validation for ``message_create`` (required fields, the 64KB inclusive
  inline boundary on ``subject``/``body``, the artifact-reference list, and the
  routing ``target`` schema) raising the canonical catalogue codes;
* ``(de)serialisation`` of the routing ``target`` (object <-> JSON TEXT);
* the visibility predicate ``can_view_message``, layered on the IMPORTED routing
  rule :func:`okto_nexus.domain.routing.is_agent_eligible` (this slice references
  routing, it never redefines it).
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Mapping
from typing import Any

from ..errors import ErrorCode, OktoNexusError
from .base import new_id, utf8_byte_len
from .routing import RoutingAgent, is_agent_eligible

__all__ = [
    "SEED_CHANNEL_NAMES",
    "MAX_CHANNEL_NAME_LEN",
    "MESSAGE_STREAM",
    "MESSAGE_CREATED_TYPE",
    "new_message_id",
    "new_channel_id",
    "validate_channel_name",
    "require_message_fields",
    "enforce_inline_size",
    "normalize_artifacts",
    "validate_target",
    "serialize_target",
    "parse_target",
    "can_view_message",
]

#: Channels seeded once per workspace (idempotently) the first time
#: ``channel_list`` touches the workspace (no write path seeds channels). Only
#: ``general`` is provided as a neutral default; every other channel is created
#: on demand by agents via ``channel_create`` so the tool is not pinned to any
#: one purpose (e.g. coding).
SEED_CHANNEL_NAMES: tuple[str, ...] = ("general",)

#: Upper bound (characters, after trimming) on an agent-supplied channel name.
MAX_CHANNEL_NAME_LEN = 64

#: Event-log stream and type for the single ``message.created`` event emitted
#: atomically with each new message row. The event is PUBLISHED on the
#: ``workspace`` stream - the base observable stream of the whole workspace and
#: one of the consumable ``VALID_STREAMS`` (workspace/agent/task/handoff) - so
#: that consumers of ``event_get`` / ``event_wait`` can observe it. Per-event
#: visibility (broadcast vs directed) is still enforced by
#: ``can_agent_see_event``; the stream is only the coarse routing channel.
MESSAGE_STREAM = "workspace"
MESSAGE_CREATED_TYPE = "message.created"


def new_message_id() -> str:
    """Return a fresh, server-assigned, opaque message id."""
    return new_id("msg")


def new_channel_id() -> str:
    """Return a fresh, server-assigned, opaque channel id."""
    return new_id("chan")


def validate_channel_name(name: Any) -> str:
    """Validate an agent-supplied channel name, returning the trimmed value.

    A channel name must be a non-blank string of at most
    :data:`MAX_CHANNEL_NAME_LEN` characters with no control characters. The
    value is whitespace-trimmed so ``" general "`` and ``"general"`` resolve to
    the same channel (names are unique per workspace and matched exactly, case
    included). Raises ``VALIDATION_ERROR`` on any violation.
    """
    if not isinstance(name, str) or not name.strip():
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "channel name is required (a non-blank string).",
            {"name": name},
        )
    trimmed = name.strip()
    if len(trimmed) > MAX_CHANNEL_NAME_LEN:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"channel name must be at most {MAX_CHANNEL_NAME_LEN} characters.",
            {"length": len(trimmed), "max": MAX_CHANNEL_NAME_LEN},
        )
    # Reject ANY Unicode control character (category "Cc"): the C0 range, DEL
    # (0x7F) and the C1 range (0x80-0x9F) - not just C0 (< 32).
    if any(unicodedata.category(ch) == "Cc" for ch in trimmed):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "channel name must not contain control characters.",
            {"name": name},
        )
    return trimmed


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def require_message_fields(from_agent_id: Any, subject: Any, body: Any) -> None:
    """Validate the mandatory message fields.

    ``from_agent_id``, ``subject`` and ``body`` are all required and must be
    non-empty strings. Raises ``VALIDATION_ERROR`` otherwise; no row/event is
    written by the caller on a rejection.
    """
    for field, value in (
        ("from_agent_id", from_agent_id),
        ("subject", subject),
        ("body", body),
    ):
        if not _is_nonempty_str(value):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field} is required and must be a non-empty string.",
                {"field": field},
            )


def enforce_inline_size(subject: Any, body: Any, max_inline_bytes: int) -> None:
    """Enforce the inclusive 64KB UTF-8 inline boundary on ``subject``/``body``.

    ``<= max_inline_bytes`` is accepted; ``> max_inline_bytes`` raises
    ``CONTENT_TOO_LARGE`` (and the caller writes nothing).
    """
    for field, value in (("subject", subject), ("body", body)):
        if value is None:
            continue
        size = utf8_byte_len(value if isinstance(value, str) else str(value))
        if size > max_inline_bytes:
            raise OktoNexusError(
                ErrorCode.CONTENT_TOO_LARGE,
                f"{field} exceeds the inline limit of {max_inline_bytes} UTF-8 bytes.",
                {"field": field, "size": size, "max_inline_bytes": max_inline_bytes},
            )


def normalize_artifacts(artifacts: Any) -> list[str]:
    """Normalise ``artifacts`` into a list of artifact-id reference strings.

    ``None`` -> ``[]``. The value must be a (non-string, non-mapping) sequence of
    non-empty strings; anything else raises ``VALIDATION_ERROR``. Only references
    are stored - never inline artifact blobs (identity is owned by the Artifacts
    spec; this slice merely echoes the references).
    """
    if artifacts is None:
        return []
    if isinstance(artifacts, (str, bytes)) or isinstance(artifacts, Mapping):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "artifacts must be a list of artifact_id reference strings.",
            {"artifacts_type": type(artifacts).__name__},
        )
    try:
        items = list(artifacts)
    except TypeError:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "artifacts must be a list of artifact_id reference strings.",
            {"artifacts_type": type(artifacts).__name__},
        ) from None
    out: list[str] = []
    for item in items:
        if not _is_nonempty_str(item):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "Each artifact reference must be a non-empty artifact_id string.",
                {"artifact": item},
            )
        out.append(item)
    return out


def validate_target(target: Any, now: Any) -> None:
    """Validate the routing ``target`` against the IMPORTED routing schema.

    A ``None``/blank target is a broadcast (no restriction) and is always valid.
    A malformed target (unknown strategy, missing required field, non-JSON
    string, ...) surfaces as ``VALIDATION_ERROR`` straight from
    :func:`okto_nexus.domain.routing.is_agent_eligible`, which this slice reuses
    rather than reimplementing. The boolean result is irrelevant here - we only
    exercise the schema.
    """
    if target is None or (isinstance(target, str) and not target.strip()):
        return
    probe = RoutingAgent(agent_id="__validate__", workspace_id="__validate__")
    # Pass ``now`` for both created_at and now so the time-based
    # ``direct_with_fallback`` strategy validates structurally.
    is_agent_eligible(probe, target, now, now)


def serialize_target(target: Any) -> str | None:
    """Serialise a routing ``target`` to the TEXT form stored on the row.

    Mappings are JSON-encoded; a (already-JSON) string is stored verbatim;
    ``None``/blank collapses to ``None`` (a broadcast message carries no target).
    """
    if target is None:
        return None
    if isinstance(target, str):
        stripped = target.strip()
        return stripped or None
    return json.dumps(target, ensure_ascii=False)


def parse_target(stored: Any) -> Any:
    """Parse a stored ``target`` back into its echo form (object or string).

    ``None``/blank -> ``None``; a JSON object/array string -> the decoded value;
    any other string -> itself.
    """
    if stored is None:
        return None
    if isinstance(stored, (Mapping, list)):
        return stored
    if isinstance(stored, str):
        text = stored.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return stored
    return stored


def can_view_message(
    viewer: Any, *, target: Any, created_at: Any = None, now: Any = None
) -> bool:
    """Return whether ``viewer`` may see a message with routing ``target``.

    ``viewer is None`` means *no visibility filtering* (an unscoped/admin read):
    the message is returned. Otherwise the IMPORTED routing eligibility decides:
    a broadcast (empty target) is visible to everyone; a directed message is
    visible only to agents the routing predicate deems eligible.
    """
    if viewer is None:
        return True
    return is_agent_eligible(viewer, target, created_at, now)
