"""Pure domain primitives shared across slices.

Strictly side-effect-free: no DB, no network, no MCP. Only the stdlib (plus the
dependency-free error catalogue) is imported here, and never ``sqlite3`` nor
``mcp`` (enforced by the import boundary test).

This module is the SINGLE home of the cross-slice helpers that used to be
copy-pasted per slice (and had already diverged):

* time: :func:`utc_now_iso` / :func:`iso_to_epoch` / :func:`iso_plus`;
* the inclusive inline-content limit: :func:`check_inline_size`;
* pagination input parsing: :func:`normalize_cursor` / :func:`clamp_limit`.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ..errors import ErrorCode, OktoNexusError

#: The canonical timestamp grammar: fixed-width UTC ISO-8601 with a 6-digit
#: fractional part and a ``Z`` designator - the EXACT shape :func:`utc_now_iso`
#: emits. Fixed width is what makes lexicographic string ordering equal
#: chronological ordering (e.g. the SQL ``<`` used for inbox lease expiry).
_CANONICAL_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with a ``Z`` suffix.

    Example: ``"2026-06-07T12:34:56.789012Z"``. The ``Z`` designator marks UTC
    explicitly (no offset), as required by the canonical timestamp rule.
    ``timespec="microseconds"`` forces a FIXED-WIDTH fractional part (always 6
    digits, even at a whole second) so that lexicographic string ordering of
    timestamps matches chronological ordering everywhere (e.g. the SQL ``<``
    used for inbox lease expiry).
    """
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def iso_to_epoch(iso: str) -> float:
    """Parse a UTC ISO-8601 timestamp to POSIX epoch seconds.

    The single, shared parser (previously triplicated per slice, with copies
    already diverging on lowercase ``z``): both ``Z`` and ``z`` designators are
    honoured, an explicit offset is normalised, and a naive timestamp is
    assumed UTC. Raises ``ValueError`` for an unparseable string and
    ``TypeError`` for a non-string (the stdlib contract callers already wrap).
    """
    if not isinstance(iso, str):
        raise TypeError(f"timestamp must be a string, not {type(iso).__name__}")
    text = iso.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def iso_plus(now_iso: str, seconds: float) -> str:
    """Return ``now_iso`` shifted forward by ``seconds``, in canonical form.

    This is the LEASE-WRITE boundary: lease timestamps are compared
    lexicographically (SQL ``<``) against other canonical timestamps, so the
    base instant MUST itself be canonical fixed-width (a mixed-width value -
    e.g. ``...T00:00:00Z`` next to ``...T00:00:00.500000Z`` - orders WRONG
    lexicographically). A non-canonical input is a producer/wiring bug (an
    injected clock not emitting :func:`utc_now_iso`'s shape), so it raises
    ``INTERNAL_ERROR`` with a prescriptive message rather than writing a lease
    that silently corrupts expiry ordering.
    """
    if not isinstance(now_iso, str) or not _CANONICAL_UTC_RE.match(now_iso):
        raise OktoNexusError(
            ErrorCode.INTERNAL_ERROR,
            f"Refusing to compute a lease timestamp from {now_iso!r}: it is not "
            "the canonical fixed-width UTC form 'YYYY-MM-DDTHH:MM:SS.ffffffZ'. "
            "Lease expiry compares timestamps lexicographically, so a "
            "mixed-width value would corrupt expiry ordering. Fix the injected "
            "Clock to emit utc_now_iso()'s format.",
            {"now_iso": now_iso},
        )
    dt = datetime.fromisoformat(now_iso[:-1] + "+00:00")
    shifted = dt + timedelta(seconds=seconds)
    return shifted.isoformat(timespec="microseconds").replace("+00:00", "Z")


def new_id(prefix: str = "") -> str:
    """Generate a new opaque identifier (UUID4 hex), optionally prefixed.

    Slices use this for entity ids (e.g. ``new_id("msg")`` -> ``"msg_<hex>"``).
    The prefix is purely cosmetic; ids are treated as opaque strings.
    """
    raw = uuid.uuid4().hex
    return f"{prefix}_{raw}" if prefix else raw


def utf8_byte_len(text: str) -> int:
    """Return the UTF-8 encoded byte length of ``text``.

    Used to enforce the inline content limit (boundary is inclusive:
    ``<= max_inline_bytes`` is allowed).
    """
    return len(text.encode("utf-8"))


def check_inline_size(field: str, value: Any, max_inline_bytes: int) -> None:
    """Enforce the inclusive inline content limit on ``value``.

    The single, shared check (previously duplicated per slice with diverging
    measurement rules): the limit is measured on the canonical serialised TEXT
    - a string is measured verbatim (it round-trips byte-for-byte), any other
    value is measured as its JSON encoding. ``None`` always passes. Raises
    ``VALIDATION_ERROR`` for a non-JSON-serialisable value and
    ``CONTENT_TOO_LARGE`` when the limit is exceeded.
    """
    if value is None:
        return
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{field} is not JSON-serialisable.",
                {"field": field},
            ) from exc
    if utf8_byte_len(text) > max_inline_bytes:
        raise OktoNexusError(
            ErrorCode.CONTENT_TOO_LARGE,
            f"{field} inline content exceeds {max_inline_bytes} UTF-8 bytes.",
            {"field": field, "max_inline_bytes": max_inline_bytes},
        )


def _coerce_page_int(value: Any, *, message: str, details_key: str) -> int:
    """Coerce a pagination input (int or digit-string) to ``int``, fail-closed.

    ``bool`` is rejected explicitly (an ``int`` subclass); a string is accepted
    when it parses as an integer (cursors round-trip as opaque STRINGS on some
    tools, and MCP agents routinely send numbers as strings). Anything else
    raises ``VALIDATION_ERROR`` with the caller's message.
    """
    invalid = OktoNexusError(
        ErrorCode.VALIDATION_ERROR, message, {details_key: value}
    )
    if isinstance(value, bool):
        raise invalid
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except (TypeError, ValueError):
            raise invalid from None
    raise invalid


def normalize_cursor(cursor: Any) -> int:
    """Coerce ``cursor`` to a non-negative INTEGER (``None``/blank -> ``0``).

    The single pagination-cursor parser shared by every offset/event-id cursor
    (events, handoffs). Accepts an int or an integer string (tools echo
    ``next_cursor`` as an opaque string); ``bool``, negatives, and anything
    else raise ``VALIDATION_ERROR``.
    """
    if cursor is None or (isinstance(cursor, str) and not cursor.strip()):
        return 0
    value = _coerce_page_int(
        cursor,
        message="cursor must be a non-negative integer.",
        details_key="cursor",
    )
    if value < 0:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "cursor must be a non-negative integer.",
            {"cursor": cursor},
        )
    return value


def clamp_limit(limit: Any, *, default: int, maximum: int) -> int:
    """Resolve a page size: ``None``/blank -> ``default``, then clamp to ``maximum``.

    The single page-limit parser shared by every paginated read. Accepts an
    int or an integer string; ``bool``, non-integers, and values ``< 1`` raise
    ``VALIDATION_ERROR``. Values above ``maximum`` are clamped to ``maximum``.
    """
    if limit is None or (isinstance(limit, str) and not limit.strip()):
        return min(default, maximum)
    value = _coerce_page_int(
        limit,
        message="limit must be a positive integer.",
        details_key="limit",
    )
    if value < 1:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "limit must be a positive integer.",
            {"limit": limit},
        )
    return min(value, maximum)
