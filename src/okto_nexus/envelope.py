"""Response envelope helpers.

Every tool/handler returns a canonical envelope:

* success -> ``{"ok": true, "data": {...}}``
* failure -> ``{"ok": false, "error": {"code", "message", "details"?}}``

``data`` and ``error`` are mutually exclusive. The :func:`tool_envelope`
decorator guarantees that NO exception ever crosses the adapter boundary:
:class:`OktoNexusError` becomes a structured failure, and any other exception
is normalised to ``INTERNAL_ERROR``.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Mapping

from .errors import OktoNexusError, to_envelope_error


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
