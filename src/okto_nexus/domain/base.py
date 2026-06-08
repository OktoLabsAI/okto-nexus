"""Pure domain primitives shared across slices.

Strictly side-effect-free: no DB, no network, no MCP. Only the stdlib is
imported here, and never ``sqlite3`` nor ``mcp`` (enforced by the import
boundary test).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with a ``Z`` suffix.

    Example: ``"2026-06-07T12:34:56.789012Z"``. The ``Z`` designator marks
    UTC explicitly (no offset), as required by the canonical timestamp rule.
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
