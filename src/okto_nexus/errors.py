"""Canonical error taxonomy for Okto Nexus.

This module is dependency-free (stdlib only) so it can be imported from any
layer, including ``domain`` and ``application``. It defines:

* :class:`ErrorCode` - the CLOSED catalogue of 18 error codes.
* :class:`OktoNexusError` - the single exception type carried across the
  application; every adapter boundary converts it into an error envelope.
  Carries ``retryable`` so transient failures (e.g. SQLite lock contention)
  are distinguishable from real faults by MCP callers.
* :func:`to_envelope_error` - normalises ANY exception into a well-formed
  error payload, mapping unknown exceptions to ``INTERNAL_ERROR``.
* :func:`is_retryable_db_exception` / :func:`db_error_from_exception` - the
  single classification point for transient SQLite lock/busy errors.

The catalogue is normative and FROZEN: do not add, rename, or remove codes
without a corresponding contract change.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


class ErrorCode(str, Enum):
    """Closed catalogue of the 18 canonical error codes (SCREAMING_SNAKE_CASE).

    Inherits from ``str`` so members serialise directly as their value in
    JSON envelopes (``ErrorCode.NOT_FOUND == "NOT_FOUND"``).
    """

    # Workspace resolution / scoping
    WORKSPACE_REQUIRED = "WORKSPACE_REQUIRED"
    WORKSPACE_UNRESOLVED = "WORKSPACE_UNRESOLVED"
    WORKSPACE_MISMATCH = "WORKSPACE_MISMATCH"

    # Validation / lookup / ownership
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    NOT_OWNER = "NOT_OWNER"

    # State machines / streams
    INVALID_TRANSITION = "INVALID_TRANSITION"
    INVALID_STREAM = "INVALID_STREAM"

    # Handoff claim lifecycle
    HANDOFF_ALREADY_CLAIMED = "HANDOFF_ALREADY_CLAIMED"
    NOT_ELIGIBLE_TO_CLAIM = "NOT_ELIGIBLE_TO_CLAIM"

    # Content / filesystem limits
    CONTENT_TOO_LARGE = "CONTENT_TOO_LARGE"
    PATH_OUTSIDE_WORKSPACE = "PATH_OUTSIDE_WORKSPACE"

    # Infrastructure
    CONFIG_ERROR = "CONFIG_ERROR"
    MIGRATION_ERROR = "MIGRATION_ERROR"
    DB_ERROR = "DB_ERROR"
    RENDER_ERROR = "RENDER_ERROR"

    # Tool catalogue migration: returned by shims of removed/renamed tools,
    # pointing the caller at the replacement tool.
    MIGRATED = "MIGRATED"

    # Catch-all for unexpected failures
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Frozen set of the canonical code strings, for membership checks/validation.
ERROR_CODES: frozenset[str] = frozenset(code.value for code in ErrorCode)


class OktoNexusError(Exception):
    """Domain/application exception carrying a canonical error code.

    Attributes
    ----------
    code:
        One of the :class:`ErrorCode` values (stored as its string value).
    message:
        Human-readable, safe-to-surface message.
    details:
        Optional structured context (must be JSON-serialisable). Never
        ``None`` in the serialised envelope when present.
    retryable:
        ``True`` when the failure is transient (e.g. the SQLite database was
        briefly locked by another process) and the SAME call can simply be
        retried. Defaults to ``False`` and is surfaced in the envelope's
        ``details`` so MCP callers can branch on it.
    """

    def __init__(
        self,
        code: "ErrorCode | str",
        message: str,
        details: Mapping[str, Any] | None = None,
        *,
        retryable: bool = False,
    ) -> None:
        self.code: str = code.value if isinstance(code, ErrorCode) else str(code)
        self.message: str = message
        self.details: dict[str, Any] | None = dict(details) if details else None
        self.retryable: bool = retryable
        super().__init__(f"{self.code}: {self.message}")

    def to_error_dict(self) -> dict[str, Any]:
        """Return the ``error`` object for a failure envelope."""
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        details = dict(self.details) if self.details else {}
        if self.retryable:
            details["retryable"] = True
        if details:
            error["details"] = details
        return error

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"OktoNexusError(code={self.code!r}, message={self.message!r}, "
            f"details={self.details!r})"
        )


# Lowercased message fragments of sqlite3.OperationalError that identify the
# SQLITE_BUSY / SQLITE_BUSY_SNAPSHOT / SQLITE_LOCKED family: another connection
# holds the write lock, and the call succeeds once that writer commits.
_TRANSIENT_DB_MARKERS: tuple[str, ...] = ("database is locked", "database is busy")


def is_retryable_db_exception(exc: BaseException) -> bool:
    """Return whether ``exc`` is transient SQLite lock/busy contention.

    Matches ``sqlite3.OperationalError`` (recognised by class name so this
    module stays free of a ``sqlite3`` import) whose message reports the
    database as locked/busy. Anything else - including programming errors that
    merely mention locking - is NOT retryable.
    """
    if not any(c.__name__ == "OperationalError" for c in type(exc).__mro__):
        return False
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_DB_MARKERS)


def db_error_from_exception(
    action: str,
    exc: BaseException,
    details: Mapping[str, Any] | None = None,
) -> OktoNexusError:
    """Normalise a low-level database exception into a ``DB_ERROR``.

    The single construction point used by the SQLite adapters: transient
    lock/busy contention (see :func:`is_retryable_db_exception`) is flagged
    ``retryable=True`` with a message that tells the caller to retry;
    everything else stays ``retryable=False``. ``details["reason"]`` always
    carries the driver's message.
    """
    retryable = is_retryable_db_exception(exc)
    merged: dict[str, Any] = {"reason": str(exc)}
    if details:
        merged.update(details)
    if retryable:
        message = (
            f"SQLite failure while {action}: the database is briefly locked by "
            "another process. Retry the call; the lock clears as soon as the "
            "competing writer commits."
        )
    else:
        message = f"SQLite failure while {action}."
    return OktoNexusError(ErrorCode.DB_ERROR, message, merged, retryable=retryable)


def to_envelope_error(exc: BaseException) -> dict[str, Any]:
    """Normalise any exception into a failure-envelope ``error`` object.

    Known :class:`OktoNexusError` instances are surfaced verbatim. Any other
    exception is mapped to ``INTERNAL_ERROR`` so that no unexpected exception
    type leaks across the adapter boundary.
    """
    if isinstance(exc, OktoNexusError):
        return exc.to_error_dict()
    return {
        "code": ErrorCode.INTERNAL_ERROR.value,
        "message": "An unexpected internal error occurred.",
        "details": {"exception": type(exc).__name__},
    }
