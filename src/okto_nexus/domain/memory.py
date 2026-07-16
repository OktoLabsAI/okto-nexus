"""Pure domain rules for the workspace memory slice (spec 8928b320, I6).

A *memory* is a short, durable, addressable fact an agent records for the
whole workspace: a title, a content body bounded to what a default projection
response can carry verbatim, optional lowercase topics, and an optional
provenance pointer. This module owns the IO-free grammar - field validation,
the closed provenance vocabulary and the id shape. It never imports
``sqlite3`` nor ``mcp`` (enforced by the import-boundary test).

Design anchors:

* ``MEMORY_CONTENT_MAX_BYTES`` equals the projection's ``MAX_ITEM_BYTES``
  (16384): a whole memory always fits one default envelope untruncated (BR8).
  Larger documents belong to artifacts.
* Provenance is an atomic pair with a closed ``source_kind`` vocabulary; the
  pointed-at entity's EXISTENCE is never verified (trace_id/I1 philosophy:
  an informative audit pointer that survives pruning of its source) (BR3).
* The supersede chain is linear; the cross-row invariants (target exists in
  the same workspace, target not yet superseded) are enforced by the
  application service inside the unit of work - here we only validate shape.
"""

from __future__ import annotations

from typing import Any

from ..errors import ErrorCode, OktoNexusError
from .base import new_id, utf8_byte_len

__all__ = [
    "MEMORY_TITLE_MAX_LEN",
    "MEMORY_CONTENT_MAX_BYTES",
    "MEMORY_TOPICS_MAX",
    "MEMORY_TOPIC_MAX_LEN",
    "MEMORY_SOURCE_KINDS",
    "MEMORY_SOURCE_ID_MAX_LEN",
    "MEMORY_STREAM",
    "MEMORY_CREATED_EVENT",
    "MEMORY_SUPERSEDED_EVENT",
    "new_memory_id",
    "validate_memory_title",
    "validate_memory_content",
    "normalize_memory_topics",
    "validate_memory_provenance",
]

#: Upper bound for ``title`` (characters, post-strip).
MEMORY_TITLE_MAX_LEN = 200

#: Inclusive upper bound for ``content`` in UTF-8 BYTES (not characters).
#: Deliberately equal to the projection's ``MAX_ITEM_BYTES`` so one memory
#: always fits a default tool response without truncation (BR8).
MEMORY_CONTENT_MAX_BYTES = 16384

#: At most this many topics per memory (measured AFTER silent dedup).
MEMORY_TOPICS_MAX = 10

#: Upper bound for a single topic (characters, post-strip/lowercase).
MEMORY_TOPIC_MAX_LEN = 50

#: Closed provenance vocabulary (BR3). Existence of the pointed-at entity is
#: never verified - the pair is an informative audit pointer.
MEMORY_SOURCE_KINDS: frozenset[str] = frozenset({"event", "message", "handoff"})

#: Upper bound for ``source_id`` (characters, post-strip).
MEMORY_SOURCE_ID_MAX_LEN = 128

#: Event stream + types for the audit events (FR6). Published on the base
#: ``workspace`` stream so ``event_get``/``event_wait`` consumers observe them.
MEMORY_STREAM = "workspace"
MEMORY_CREATED_EVENT = "memory.created"
MEMORY_SUPERSEDED_EVENT = "memory.superseded"


def new_memory_id() -> str:
    """Return a fresh memory id (``mem_`` + 32 hex chars)."""
    return new_id("mem")


def validate_memory_title(value: Any) -> str:
    """Return the stripped ``title`` if it is 1..200 characters.

    Raises ``VALIDATION_ERROR`` for a missing/blank/non-string title or one
    longer than :data:`MEMORY_TITLE_MAX_LEN` characters post-strip.
    """
    if not isinstance(value, str) or not value.strip():
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "title is required and must be a non-empty string.",
            {"title": value},
        )
    title = value.strip()
    if len(title) > MEMORY_TITLE_MAX_LEN:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"title exceeds {MEMORY_TITLE_MAX_LEN} characters.",
            {"title_chars": len(title), "max": MEMORY_TITLE_MAX_LEN},
        )
    return title


def validate_memory_content(value: Any) -> str:
    """Return ``content`` if it is a non-empty string of at most 16384 bytes.

    The boundary is measured in UTF-8 BYTES post-encode (inclusive), matching
    the projection's per-item ceiling: a valid memory is always returnable
    verbatim in a default response. Oversized content raises
    ``VALIDATION_ERROR`` whose details point the caller at ``artifact_put``
    for larger documents (BR8).
    """
    if not isinstance(value, str) or not value:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "content is required and must be a non-empty string.",
            {"content": value},
        )
    size = utf8_byte_len(value)
    if size > MEMORY_CONTENT_MAX_BYTES:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            (
                f"content is {size} bytes UTF-8, exceeding the inclusive "
                f"{MEMORY_CONTENT_MAX_BYTES}-byte limit. Memory holds short "
                "addressable facts; store larger documents with artifact_put "
                "and reference them."
            ),
            {"content_bytes": size, "max": MEMORY_CONTENT_MAX_BYTES},
        )
    return value


def normalize_memory_topics(value: Any) -> list[str]:
    """Normalise ``topics`` to at most 10 lowercase, deduplicated tokens.

    ``None`` means no topics. Each entry must be a non-blank string of at
    most 50 characters post-strip; entries are lowercased and silently
    deduplicated preserving first-seen order. More than 10 DISTINCT topics
    raises ``VALIDATION_ERROR`` (fail-closed - nothing is silently dropped
    except exact duplicates).
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "topics must be a list of strings.",
            {"topics": value},
        )
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "topics entries must be non-empty strings.",
                {"topic": item},
            )
        topic = item.strip().lower()
        if len(topic) > MEMORY_TOPIC_MAX_LEN:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"a topic exceeds {MEMORY_TOPIC_MAX_LEN} characters.",
                {"topic": topic, "max": MEMORY_TOPIC_MAX_LEN},
            )
        if topic not in normalized:
            normalized.append(topic)
    if len(normalized) > MEMORY_TOPICS_MAX:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"at most {MEMORY_TOPICS_MAX} distinct topics are allowed.",
            {"topics_count": len(normalized), "max": MEMORY_TOPICS_MAX},
        )
    return normalized


def validate_memory_provenance(
    source_kind: Any = None, source_id: Any = None
) -> tuple[str | None, str | None]:
    """Validate the provenance pair ``(source_kind, source_id)``.

    Both absent -> ``(None, None)``. One without the other raises
    ``VALIDATION_ERROR`` (atomic pair, BR3). ``source_kind`` must belong to
    the closed vocabulary ``{event, message, handoff}``; ``source_id`` must be
    a non-blank string of at most 128 characters post-strip. Shape only - the
    pointed-at entity's existence is deliberately NOT verified.
    """
    if source_kind is None and source_id is None:
        return None, None
    if source_kind is None or source_id is None:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "source_kind and source_id must be provided together.",
            {"source_kind": source_kind, "source_id": source_id},
        )
    if not isinstance(source_kind, str) or (
        source_kind.strip().lower() not in MEMORY_SOURCE_KINDS
    ):
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"Unsupported source_kind: {source_kind!r}.",
            {
                "source_kind": source_kind,
                "supported": sorted(MEMORY_SOURCE_KINDS),
            },
        )
    if not isinstance(source_id, str) or not source_id.strip():
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "source_id must be a non-empty string.",
            {"source_id": source_id},
        )
    sid = source_id.strip()
    if len(sid) > MEMORY_SOURCE_ID_MAX_LEN:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            f"source_id exceeds {MEMORY_SOURCE_ID_MAX_LEN} characters.",
            {"source_id_chars": len(sid), "max": MEMORY_SOURCE_ID_MAX_LEN},
        )
    return source_kind.strip().lower(), sid
