"""Pure domain rules for the artifacts slice.

This module owns the *content-shape* invariants of Okto Nexus V1 artifacts and
is strictly side-effect free: stdlib only, never ``sqlite3`` nor ``mcp``
(enforced by the import-boundary test). All filesystem containment and
persistence live in the outbound adapters; here we only answer pure questions:

* :func:`normalize_artifact_type` - is ``artifact_type`` in the closed
  whitelist ``{file, text, json, markdown}`` (else ``VALIDATION_ERROR``)?
* :func:`ensure_within_inline_limit` - is inline ``content`` within the 64 KB
  (``65536`` bytes UTF-8, *inclusive*) ceiling (else ``CONTENT_TOO_LARGE``)?
* :func:`ensure_well_formed_json` - does a ``json`` artifact's ``content``
  parse as well-formed JSON (else ``VALIDATION_ERROR``)?

These are total, deterministic functions that raise the canonical catalogue
codes; a value that is simply absent is handled by the caller.
"""

from __future__ import annotations

import json
from typing import Any

from ..errors import ErrorCode, OktoNexusError
from .base import utf8_byte_len

__all__ = [
    "ARTIFACT_TYPES",
    "STORED_INLINE",
    "STORED_PATH",
    "ARTIFACT_STREAM",
    "ARTIFACT_CREATED_EVENT",
    "normalize_artifact_type",
    "ensure_within_inline_limit",
    "ensure_well_formed_json",
]

#: Closed whitelist of accepted artifact types (BR3).
ARTIFACT_TYPES: frozenset[str] = frozenset({"file", "text", "json", "markdown"})

#: ``stored`` discriminators surfaced in the envelopes (derived, not a column).
STORED_INLINE = "inline"
STORED_PATH = "path"

#: Event stream + type for the audit event emitted on a successful put (FR7).
#: The event is PUBLISHED on the ``workspace`` stream - the base observable
#: stream of the whole workspace and one of the consumable ``VALID_STREAMS``
#: (workspace/agent/task/handoff) - so consumers of ``event_get`` /
#: ``event_wait`` can observe it (rather than an unconsultable ``artifact``
#: stream).
ARTIFACT_STREAM = "workspace"
ARTIFACT_CREATED_EVENT = "artifact.created"


def normalize_artifact_type(value: Any) -> str:
    """Validate and normalise ``artifact_type`` against the closed whitelist.

    Matching is case-insensitive; the canonical lowercase token is returned.
    Raises ``VALIDATION_ERROR`` for a missing/blank type or one outside
    ``{file, text, json, markdown}`` (FR2 / BR3).
    """
    if not isinstance(value, str) or not value.strip():
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "artifact_type is required.",
            {"artifact_type": value},
        )
    token = value.strip().lower()
    if token not in ARTIFACT_TYPES:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"Unsupported artifact_type: {value!r}.",
            {"artifact_type": value, "supported": sorted(ARTIFACT_TYPES)},
        )
    return token


def ensure_within_inline_limit(content: str, max_inline_bytes: int) -> int:
    """Return the UTF-8 byte length of ``content`` if it fits inline.

    The boundary is *inclusive*: exactly ``max_inline_bytes`` is allowed, one
    byte over raises ``CONTENT_TOO_LARGE`` whose ``details`` instruct the caller
    to store large content as a file (``artifact_type=file`` + ``path``)
    (FR3 / FR4 / BR4 / BR11).
    """
    size = utf8_byte_len(content)
    if size > max_inline_bytes:
        raise OktoNexusError(
            ErrorCode.CONTENT_TOO_LARGE,
            (
                f"Inline content is {size} bytes UTF-8, exceeding the inclusive "
                f"{max_inline_bytes}-byte limit."
            ),
            {
                "size_bytes": size,
                "max_inline_bytes": max_inline_bytes,
                "hint": (
                    "Store content larger than the inline limit as a file: pass "
                    "artifact_type='file' with a workspace-relative 'path' "
                    "instead of inline 'content'."
                ),
            },
        )
    return size


def ensure_well_formed_json(content: str) -> None:
    """Validate that a ``json`` artifact's inline ``content`` is well-formed JSON.

    Raises ``VALIDATION_ERROR`` when the content does not parse (FR5 / BR5).
    """
    try:
        json.loads(content)
    except (ValueError, TypeError) as exc:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "artifact_type 'json' requires well-formed JSON content.",
            {"reason": str(exc)},
        ) from None
