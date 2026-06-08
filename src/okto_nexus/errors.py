"""Canonical error taxonomy for Okto Nexus.

This module is dependency-free (stdlib only) so it can be imported from any
layer, including ``domain`` and ``application``. It defines:

* :class:`ErrorCode` - the CLOSED catalogue of 17 error codes.
* :class:`OktoNexusError` - the single exception type carried across the
  application; every adapter boundary converts it into an error envelope.
* :func:`to_envelope_error` - normalises ANY exception into a well-formed
  error payload, mapping unknown exceptions to ``INTERNAL_ERROR``.

The catalogue is normative and FROZEN: do not add, rename, or remove codes
without a corresponding contract change.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


class ErrorCode(str, Enum):
    """Closed catalogue of the 17 canonical error codes (SCREAMING_SNAKE_CASE).

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
    """

    def __init__(
        self,
        code: "ErrorCode | str",
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code: str = code.value if isinstance(code, ErrorCode) else str(code)
        self.message: str = message
        self.details: dict[str, Any] | None = dict(details) if details else None
        super().__init__(f"{self.code}: {self.message}")

    def to_error_dict(self) -> dict[str, Any]:
        """Return the ``error`` object for a failure envelope."""
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        return error

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"OktoNexusError(code={self.code!r}, message={self.message!r}, "
            f"details={self.details!r})"
        )


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
