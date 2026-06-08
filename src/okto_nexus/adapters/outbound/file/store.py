"""Workspace-contained filesystem store (outbound :class:`FileStore` port).

Implements :class:`okto_nexus.application.ports.FileStore`. Every relative path
is resolved against the workspace root with ``normalize`` + ``realpath`` and
then checked for *containment* via :func:`os.path.commonpath`: a resolved path
that escapes the root - through ``..`` traversal, an absolute external path, or
a symlink whose real target lies outside - raises ``PATH_OUTSIDE_WORKSPACE``
(FR6 / BR6).

Outbound adapter: free to touch the filesystem. It never decides *what* to do
with a file's contents - artifact reads return path + metadata only (BR10); the
``read_text``/``write_text`` helpers exist to satisfy the port for sibling
slices and likewise route through the same containment guard.
"""

from __future__ import annotations

import os

from ....errors import ErrorCode, OktoNexusError


def _is_contained(root_real: str, target_real: str) -> bool:
    """Return whether ``target_real`` lies within ``root_real`` (commonpath).

    Both inputs are absolute. Case is normalised for case-insensitive
    filesystems (Windows); a ``ValueError`` from :func:`os.path.commonpath`
    (e.g. paths on different drives) means *not contained*.
    """
    root_n = os.path.normcase(os.path.abspath(root_real))
    target_n = os.path.normcase(os.path.abspath(target_real))
    try:
        common = os.path.commonpath([root_n, target_n])
    except ValueError:
        return False
    return common == root_n


class WorkspaceFileStore:
    """Filesystem access constrained to a single workspace root."""

    def resolve(self, workspace_root: str, relative_path: str) -> str:
        """Resolve a workspace-relative path to an absolute real path.

        Raises ``PATH_OUTSIDE_WORKSPACE`` when the resolved real path escapes the
        workspace root. An absolute ``relative_path`` is honoured by
        :func:`os.path.join` (and therefore caught by containment if external).
        """
        root_real = os.path.realpath(workspace_root)
        candidate = os.path.join(root_real, relative_path) if relative_path else root_real
        resolved = os.path.realpath(candidate)
        if not _is_contained(root_real, resolved):
            raise OktoNexusError(
                ErrorCode.PATH_OUTSIDE_WORKSPACE,
                "Resolved path escapes the workspace root.",
                {
                    "workspace_root": root_real,
                    "path": relative_path,
                    "resolved": resolved,
                },
            )
        return resolved

    def exists(self, workspace_root: str, relative_path: str) -> bool:
        """Return whether the contained path exists (escapes are simply absent)."""
        try:
            resolved = self.resolve(workspace_root, relative_path)
        except OktoNexusError:
            return False
        return os.path.exists(resolved)

    def read_text(self, workspace_root: str, relative_path: str) -> str:
        """Read and return UTF-8 text from a contained path."""
        resolved = self.resolve(workspace_root, relative_path)
        try:
            with open(resolved, "r", encoding="utf-8") as handle:
                return handle.read()
        except OSError as exc:
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "Failed to read contained file.",
                {"path": relative_path, "reason": str(exc)},
            ) from exc

    def write_text(self, workspace_root: str, relative_path: str, content: str) -> int:
        """Write UTF-8 text to a contained path; return the bytes written."""
        resolved = self.resolve(workspace_root, relative_path)
        parent = os.path.dirname(resolved)
        data = content.encode("utf-8")
        try:
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(resolved, "wb") as handle:
                handle.write(data)
        except OSError as exc:
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "Failed to write contained file.",
                {"path": relative_path, "reason": str(exc)},
            ) from exc
        return len(data)
