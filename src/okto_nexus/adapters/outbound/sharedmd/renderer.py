"""Filesystem renderer for the shared.md slice (outbound adapter).

Implements the :class:`~okto_nexus.application.shared_md.SharedMdRenderer` port:
it formats a :class:`SharedMdView` into deterministic markdown and writes it to
``{home}/workspaces/{workspace_id}/shared.md`` with an ATOMIC temp-file +
``os.replace`` swap, so a concurrent reader or a second concurrent render of the
same workspace never observes a partial, truncated, or interleaved file.

This is an outbound adapter, so it may touch the filesystem (``os``/``tempfile``)
and depend inward on the application layer (the view / result dataclasses). It
never imports ``sqlite3`` nor ``mcp``. The rendered file embeds NO wall-clock
timestamp, keeping renders byte-identical for identical committed state.

Any filesystem or serialization failure is normalised to
``OktoNexusError(RENDER_ERROR)`` and leaves no partial file behind (the previous
``shared.md``, if any, is untouched because the swap only happens after the temp
file is fully written and fsync'd).
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from pathlib import Path

from ....application.shared_md import (
    RenderResult,
    SECTION_COUNT,
    SharedMdView,
)
from ....domain.base import utf8_byte_len
from ....errors import ErrorCode, OktoNexusError

#: Subdirectory under the home dir that contains per-workspace render trees.
WORKSPACES_DIRNAME = "workspaces"
#: The rendered file name within each workspace directory.
SHARED_MD_FILENAME = "shared.md"

_NONE_PLACEHOLDER = "_(none)_"
_NO_VALUE = "—"
#: shared.md is the workspace-PUBLIC view: any handoff whose visibility is not
#: exactly ``public`` (eligible / private / unset) has its routing target
#: redacted behind this placeholder instead of being rendered raw.
_PRIVATE_PLACEHOLDER = "[private]"

#: Unicode ``Cc`` control characters (C0, DEL, C1) - including CR/LF. Any run of
#: them inside an agent-controlled value is collapsed to a single space by
#: :func:`_md_inline` so one entry always renders as ONE logical line.
_CONTROL_RUN_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]+")


def _md_inline(value: object) -> str:
    """Flatten an agent-controlled value into a markdown-inline-safe string.

    shared.md interpolates agent-supplied identifiers/labels into a fixed
    markdown skeleton. This is a PRESENTATION concern (the values themselves
    are stored verbatim): a stray newline must not start a heading at column 0
    or split an entry across lines, and a backtick must not close the
    surrounding code-span - so control characters (Unicode ``Cc``: C0, DEL,
    C1, including CR/LF) collapse to a single space and backticks are
    neutralised to apostrophes. Pure and deterministic: values that are
    already clean pass through byte-identical.
    """
    return _CONTROL_RUN_RE.sub(" ", str(value)).replace("`", "'")


#: ``os.replace`` is atomic on POSIX, but on Windows it can transiently fail with
#: a sharing violation when two renders swap the SAME destination concurrently.
#: Retry briefly so concurrent renders of one workspace still succeed (the swap
#: itself stays atomic - readers always see a complete old-or-new file).
_REPLACE_ATTEMPTS = 50
_REPLACE_DELAY_SECONDS = 0.002


class FileSystemSharedMdRenderer:
    """Render + atomically persist ``shared.md`` under a fixed home directory."""

    def __init__(self, *, home_dir: str | os.PathLike[str]) -> None:
        self._home_dir = Path(home_dir)

    @property
    def home_dir(self) -> Path:
        return self._home_dir

    # ------------------------------------------------------------------ #
    # Port implementation
    # ------------------------------------------------------------------ #
    def render(self, *, view: SharedMdView) -> RenderResult:
        """Format ``view`` and atomically overwrite its ``shared.md``."""
        try:
            content = self.format(view)
        except (TypeError, ValueError, UnicodeError) as exc:
            raise OktoNexusError(
                ErrorCode.RENDER_ERROR,
                "Failed to serialize shared.md content.",
                {"workspace_id": view.workspace_id, "reason": str(exc)},
            ) from exc

        target_dir = self._workspace_dir(view.workspace_id)
        target_path = target_dir / SHARED_MD_FILENAME
        self._atomic_write(target_dir, target_path, content, view.workspace_id)

        return RenderResult(
            path=str(target_path),
            bytes_written=utf8_byte_len(content),
            sections_rendered=SECTION_COUNT,
        )

    # ------------------------------------------------------------------ #
    # Path resolution / containment
    # ------------------------------------------------------------------ #
    def _workspace_dir(self, workspace_id: str) -> Path:
        """Resolve the per-workspace directory, asserting containment.

        ``workspace_id`` is already validated as 64-char lowercase hex upstream,
        so traversal is impossible; this is belt-and-suspenders. A containment
        breach maps to ``RENDER_ERROR`` (the canonical catalog for this tool does
        not surface ``PATH_OUTSIDE_WORKSPACE``).
        """
        root = self._home_dir / WORKSPACES_DIRNAME
        candidate = root / workspace_id
        resolved_root = os.path.realpath(str(root))
        resolved_candidate = os.path.realpath(str(candidate))
        try:
            common = os.path.commonpath([resolved_root, resolved_candidate])
        except ValueError as exc:  # e.g. mixed drives on Windows
            raise OktoNexusError(
                ErrorCode.RENDER_ERROR,
                "shared.md target escapes the workspaces root.",
                {"workspace_id": workspace_id},
            ) from exc
        if common != resolved_root:
            raise OktoNexusError(
                ErrorCode.RENDER_ERROR,
                "shared.md target escapes the workspaces root.",
                {"workspace_id": workspace_id},
            )
        return candidate

    # ------------------------------------------------------------------ #
    # Atomic write
    # ------------------------------------------------------------------ #
    def _atomic_write(
        self,
        target_dir: Path,
        target_path: Path,
        content: str,
        workspace_id: str,
    ) -> None:
        tmp_path: str | None = None
        try:
            os.makedirs(target_dir, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                prefix=".shared.md.", suffix=".tmp", dir=str(target_dir)
            )
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            # Atomic swap on a single filesystem: readers see old-or-new, never
            # a partial file. Only here does the previous shared.md change.
            self._replace(tmp_path, str(target_path))
            tmp_path = None
        except OSError as exc:
            raise OktoNexusError(
                ErrorCode.RENDER_ERROR,
                "Failed to write shared.md atomically.",
                {"workspace_id": workspace_id, "reason": str(exc)},
            ) from exc
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _replace(src: str, dst: str) -> None:
        """``os.replace`` with a short retry for Windows sharing violations."""
        last: OSError | None = None
        for attempt in range(_REPLACE_ATTEMPTS):
            try:
                os.replace(src, dst)
                return
            except OSError as exc:
                last = exc
                if attempt + 1 < _REPLACE_ATTEMPTS:
                    time.sleep(_REPLACE_DELAY_SECONDS)
        assert last is not None  # loop ran at least once
        raise last

    # ------------------------------------------------------------------ #
    # Deterministic markdown formatting (pure)
    # ------------------------------------------------------------------ #
    def format(self, view: SharedMdView) -> str:
        """Render the four fixed sections in order as deterministic markdown.

        Every agent-controlled value is passed through :func:`_md_inline`
        before interpolation, so no value can corrupt the document structure
        (inject a heading, split an entry across lines, or escape its
        code-span).
        """
        lines: list[str] = []
        lines.append("# Okto Nexus — shared.md")
        lines.append("")
        lines.append(f"Workspace: `{view.workspace_id}`")
        lines.append(f"Recent events shown: up to {view.limit_events} (newest first)")
        lines.append("")

        # Section 1: relevant agents / active sessions.
        lines.append("## Agents & Sessions")
        lines.append("")
        lines.append("### Agents")
        if view.agents:
            for agent in view.agents:
                role = _md_inline(agent.role) if agent.role else _NO_VALUE
                lines.append(f"- `{_md_inline(agent.agent_id)}` — role: {role}")
        else:
            lines.append(_NONE_PLACEHOLDER)
        lines.append("")
        lines.append("### Active Sessions")
        if view.sessions:
            for session in view.sessions:
                lines.append(
                    f"- `{_md_inline(session.session_id)}`"
                    f" — agent `{_md_inline(session.agent_id)}`"
                    f" — status: {_md_inline(session.status)}"
                )
        else:
            lines.append(_NONE_PLACEHOLDER)
        lines.append("")

        # Section 2: open tasks.
        lines.append("## Open Tasks")
        if view.tasks:
            for task in view.tasks:
                lines.append(
                    f"- `{_md_inline(task.task_id)}`"
                    f" — [{_md_inline(task.status)}] {_md_inline(task.title)}"
                )
        else:
            lines.append(_NONE_PLACEHOLDER)
        lines.append("")

        # Section 3: open handoffs. shared.md is workspace-public, so the
        # target (and any payload, which is never rendered here) of a
        # non-public handoff is redacted - visibility 'eligible'/'private'
        # (or unset, fail-safe) must not leak through the public view.
        lines.append("## Open Handoffs")
        if view.handoffs:
            for handoff in view.handoffs:
                if (handoff.visibility or "").strip().lower() == "public":
                    target = (
                        _md_inline(handoff.target) if handoff.target else _NO_VALUE
                    )
                else:
                    target = _PRIVATE_PLACEHOLDER
                task_id = (
                    _md_inline(handoff.task_id) if handoff.task_id else _NO_VALUE
                )
                claimed_by = (
                    _md_inline(handoff.claimed_by)
                    if handoff.claimed_by
                    else _NO_VALUE
                )
                lines.append(
                    f"- `{_md_inline(handoff.handoff_id)}`"
                    f" — [{_md_inline(handoff.status)}]"
                    f" target: {target} — task: {task_id}"
                    f" — claimed_by: {claimed_by}"
                )
        else:
            lines.append(_NONE_PLACEHOLDER)
        lines.append("")

        # Section 4: recent events (newest-first; already ordered by the service).
        lines.append("## Recent Events")
        if view.events:
            for event in view.events:
                actor = (
                    _md_inline(event.actor_agent_id)
                    if event.actor_agent_id
                    else _NO_VALUE
                )
                lines.append(
                    f"- #{event.event_id} `{_md_inline(event.type)}`"
                    f" (stream: {_md_inline(event.stream)}) actor: {actor}"
                )
        else:
            lines.append(_NONE_PLACEHOLDER)

        return "\n".join(lines) + "\n"
