"""Workspace identity resolution.

``workspace_id`` is the lowercase hex of ``sha256(realpath(project_root))``.
The CLIENT supplies ``project_root``; the SERVER computes the hash. This module
is pure stdlib (``hashlib``, ``os``) and must never import ``sqlite3`` or
``mcp`` (enforced by the import boundary test).
"""

from __future__ import annotations

import hashlib
import os

from ..errors import ErrorCode, OktoNexusError


def resolve_realpath(project_root: str) -> str:
    """Resolve ``project_root`` to a canonical absolute path.

    Raises
    ------
    OktoNexusError
        With code ``WORKSPACE_UNRESOLVED`` when ``project_root`` is empty,
        cannot be resolved (e.g. a broken symlink), or does not exist.
    """
    if not project_root or not str(project_root).strip():
        raise OktoNexusError(
            ErrorCode.WORKSPACE_UNRESOLVED,
            "project_root is empty or blank.",
            {"project_root": project_root},
        )
    try:
        real = os.path.realpath(project_root, strict=True)
    except (OSError, ValueError) as exc:
        raise OktoNexusError(
            ErrorCode.WORKSPACE_UNRESOLVED,
            "Could not resolve project_root to a real path.",
            {"project_root": project_root, "reason": str(exc)},
        ) from exc
    return real


def resolve_workspace_id(project_root: str) -> str:
    """Compute the deterministic ``workspace_id`` for a ``project_root``.

    The id is ``sha256(realpath(project_root)).hexdigest()`` in lowercase hex.

    Raises
    ------
    OktoNexusError
        With code ``WORKSPACE_UNRESOLVED`` when the path cannot be resolved.
    """
    real = resolve_realpath(project_root)
    digest = hashlib.sha256(real.encode("utf-8")).hexdigest()
    return digest.lower()
