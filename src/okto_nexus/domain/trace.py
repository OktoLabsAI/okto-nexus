"""Pure domain rules for trajectory correlation (``trace_id``).

A *trace* is an opaque correlation id that links a chain of coordination acts
(message -> handoff -> message ...) into one trajectory. This module owns the
IO-free rules: id shape, validation and the deterministic resolution matrix
that every write path applies. It never imports ``sqlite3`` nor ``mcp``
(enforced by the import-boundary test).

The whole feature is gated by the ``feature_trace`` flag (default OFF). Flag
OFF means *accept-and-ignore*: :func:`resolve_trace` returns ``None`` without
validating, persisting or echoing anything, so the write paths behave exactly
as they did before the feature existed (spec a9a2c856, decision D4 - the
canonical gating pattern for feature-flagged behaviour).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..errors import ErrorCode, OktoNexusError

__all__ = [
    "TRACE_ID_MAX_LEN",
    "new_trace_id",
    "validate_trace_id",
    "resolve_trace",
]

#: Upper bound for a caller-supplied trace id. Generous enough for any
#: external correlation scheme (W3C traceparent is 55 chars) while keeping the
#: indexed column bounded.
TRACE_ID_MAX_LEN = 128


def new_trace_id() -> str:
    """Return a fresh server-generated trace id (``trc_`` + 32 hex chars)."""
    return "trc_" + uuid4().hex


def validate_trace_id(trace_id: Any) -> str:
    """Return ``trace_id`` if it is a non-empty string of at most 128 chars.

    Anything else raises ``VALIDATION_ERROR`` (canonical catalogue code). Only
    reached when the feature is ON - flag OFF never validates (D4).
    """
    if isinstance(trace_id, str) and 1 <= len(trace_id) <= TRACE_ID_MAX_LEN:
        return trace_id
    raise OktoNexusError(
        ErrorCode.VALIDATION_ERROR,
        "trace_id must be a non-empty string of at most "
        f"{TRACE_ID_MAX_LEN} characters.",
        {"trace_id": trace_id, "max_len": TRACE_ID_MAX_LEN},
    )


def resolve_trace(
    *,
    explicit: Any = None,
    inherited: str | None = None,
    feature_on: bool,
) -> str | None:
    """Resolve the trace id a write path must persist (the D3 matrix).

    Deterministic precedence: caller-supplied ``explicit`` (validated) beats
    ``inherited`` (e.g. the parent message's trace) beats a fresh
    server-generated id. With ``feature_on=False`` the answer is always
    ``None`` - accept-and-ignore, no validation, no generation (D4).
    """
    if not feature_on:
        return None
    if explicit is not None:
        return validate_trace_id(explicit)
    if inherited:
        return inherited
    return new_trace_id()
