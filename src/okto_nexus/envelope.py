"""Response envelope helpers.

Every tool/handler returns a canonical envelope:

* success -> ``{"ok": true, "data": {...}}``
* failure -> ``{"ok": false, "error": {"code", "message", "details"?}}``

``data`` and ``error`` are mutually exclusive. The :func:`tool_envelope`
decorator guarantees that NO exception ever crosses the adapter boundary:
:class:`OktoNexusError` becomes a structured failure, and any other exception
is normalised to ``INTERNAL_ERROR``.

:func:`require_json_object_param` is the wrapper-level guard that keeps the
MCP SDK's pydantic error grammar OUT of the surface: tool wrappers annotate
object-shaped parameters as ``Any`` and call it, so a wrong type comes back as
the canonical ``VALIDATION_ERROR`` envelope instead of an SDK validation error.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Mapping

from .errors import ErrorCode, OktoNexusError, to_envelope_error


def ok(data: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a success envelope.

    Parameters
    ----------
    data:
        The success payload. ``None`` is treated as an empty object so the
        ``data`` key is always present and is always a mapping.
    """
    return {"ok": True, "data": dict(data) if data else {}}


def err(
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a failure envelope from explicit fields."""
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = dict(details)
    return {"ok": False, "error": error}


def err_from_exc(exc: BaseException) -> dict[str, Any]:
    """Build a failure envelope from any exception (see :func:`to_envelope_error`)."""
    return {"ok": False, "error": to_envelope_error(exc)}


def require_json_object_param(
    param: str,
    value: Any,
    *,
    required: bool = False,
    example: str = '{"strategy": "direct", "agent_id": "<id>"}',
) -> Any:
    """Validate a tool parameter documented as a JSON object; return it unchanged.

    Used by tool wrappers whose parameter is annotated ``Any`` so that a
    wrong-typed value reaches THIS guard (and becomes the canonical
    ``VALIDATION_ERROR`` envelope via :func:`tool_envelope`) instead of being
    rejected by FastMCP/pydantic in a second error grammar.

    Accepted: a mapping (the canonical shape), ``None`` when optional, and a
    ``str`` (passed through untouched - the application layer parses a
    JSON-object string and rejects anything else with its own canonical error).
    Numbers, booleans and arrays can never become an object, so they are
    rejected here with a prescriptive message.
    """
    if value is None:
        if required:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{param} is required and must be a JSON object, e.g. {example}.",
                {param: None},
            )
        return None
    if isinstance(value, (Mapping, str)):
        return value
    raise OktoNexusError(
        ErrorCode.VALIDATION_ERROR,
        f"{param} must be a JSON object (got {type(value).__name__}), e.g. "
        f"{example}. Pass it as a raw JSON object, NOT as a number, boolean "
        "or array.",
        {param: value, f"{param}_type": type(value).__name__},
    )


def tool_envelope(fn: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
    """Wrap a handler so it always returns a canonical envelope.

    Behaviour:

    * If the handler returns a dict that is already an envelope
      (has an ``ok`` key), it is passed through unchanged.
    * If the handler returns any other value, it is wrapped via :func:`ok`.
    * :class:`OktoNexusError` is converted to its failure envelope.
    * Any other exception is converted to an ``INTERNAL_ERROR`` envelope.

    This is the single choke point ensuring exceptions never escape the
    inbound adapter.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            result = fn(*args, **kwargs)
        except OktoNexusError as exc:
            return {"ok": False, "error": exc.to_error_dict()}
        except Exception as exc:  # noqa: BLE001 - boundary catch is intentional
            return err_from_exc(exc)
        if isinstance(result, dict) and "ok" in result:
            return result
        return ok(result if isinstance(result, Mapping) else {"result": result})

    return wrapper
