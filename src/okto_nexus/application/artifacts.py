"""Artifacts slice application service.

Implements the two artifact use cases of Okto Nexus V1:

* ``artifact_put`` - register a ``file``/``text``/``json``/``markdown`` artifact
  in the workspace resolved from ``project_root``. Requires at least one of
  ``path`` or ``content``; enforces the 64 KB inline limit (inclusive), JSON
  well-formedness for ``json`` artifacts, and workspace-root containment for
  ``path`` references. On success it persists the metadata row (plus inline
  content when small) and emits ``artifact.created`` in the SAME unit of work.
* ``artifact_get`` - retrieve an artifact by id within the resolved workspace;
  cross-workspace / unknown ids surface as ``NOT_FOUND`` (never a leak). It
  never reads external files: ``stored=path`` returns the path + metadata only.

Application layer: depends only on the ports in
:mod:`okto_nexus.application.ports`, the pure :mod:`okto_nexus.domain` helpers,
the error catalogue and :class:`NexusConfig`. It NEVER imports ``sqlite3`` nor
``mcp`` (enforced by the import-boundary test). Every coordinated mutation and
its audit event commit atomically through a single injected unit of work.

Note on metadata: the ``artifacts`` table carries no dedicated metadata blob
column, so the optional ``metadata`` object is serialised into the
``content_type`` column (which is not surfaced by any artifact contract) and
round-tripped back on read.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from ..config import NexusConfig
from ..domain.artifacts import (
    ARTIFACT_CREATED_EVENT,
    ARTIFACT_STREAM,
    STORED_INLINE,
    STORED_PATH,
    ensure_well_formed_json,
    ensure_within_inline_limit,
    normalize_artifact_type,
)
from ..domain.base import new_id
from ..domain.ids import resolve_realpath, resolve_workspace_id
from ..domain.governance import ACTION_ARTIFACT_PUT
from ..domain.policy import snapshot_permits, snapshot_to_selector
from ..errors import ErrorCode, OktoNexusError
from .governance import GovernanceService
from .permissions import permission_set_for
from .ports import (
    AgentRepo,
    ArtifactRepo,
    Clock,
    ConnectionFactory,
    EventEmitter,
    FileStore,
    UnitOfWork,
    WorkspaceRepo,
)

#: Visibility tag stamped on the artifact audit event. ``public`` means visible
#: to every agent operating in the same workspace - an artifact is a
#: workspace-scoped resource, not directed at a single agent. ``public`` is one
#: of the canonical visibilities understood by ``can_agent_see_event``, so the
#: event is observable via ``event_get`` / ``event_wait`` on the ``workspace``
#: stream (an invalid visibility would be treated as non-visible and hidden).
ARTIFACT_VISIBILITY = "public"

#: Visibility of an AUDIENCE-SCOPED ``artifact.created`` event (D-ART/BR7). When
#: the publisher had an effective outbound audience, the event is gated by that
#: SAME audience (folded into a ``tag`` target) so an out-of-audience agent
#: never sees it on the stream - the stream must not leak what ``artifact_get``
#: hides. An artifact with NO audience keeps ``ARTIFACT_VISIBILITY`` (public),
#: byte-identical to the pre-policy event (zero-regression).
ARTIFACT_SCOPED_VISIBILITY = "eligible"


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


class ArtifactService:
    """Use-case orchestration for ``artifact_put`` / ``artifact_get``."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        artifacts: ArtifactRepo,
        workspaces: WorkspaceRepo,
        files: FileStore,
        clock: Clock,
        config: NexusConfig,
        event_emitter: Optional[EventEmitter] = None,
        agents: Optional[AgentRepo] = None,
        governance: Optional[GovernanceService] = None,
    ) -> None:
        self._cf = connection_factory
        self._agents = agents
        self._artifacts = artifacts
        self._workspaces = workspaces
        self._files = files
        self._clock = clock
        self._config = config
        self._emitter = event_emitter
        # Policy enforcement (spec 80624c1a): when wired, artifact_put is
        # enforced pre-persistence against the publisher's attached policies;
        # None = no gate (and no bindings = no gate either).
        self._governance = governance

    def _put_uow(self, *, workspace_id: str, agent_id: Any):
        """The write UoW for artifact_put: governance-guarded when wired.

        The guard emits ``governance.denied`` in its own UoW AFTER a denial
        rolled the main one back (BR6); with no governance wired it is exactly
        ``unit_of_work()``.
        """
        if self._governance is not None:
            return self._governance.guard(workspace_id=workspace_id, agent_id=agent_id)
        return self._cf.unit_of_work()

    # ------------------------------------------------------------------ #
    # artifact_put
    # ------------------------------------------------------------------ #
    def artifact_put(
        self,
        *,
        project_root: Any,
        artifact_type: Any,
        name: str | None = None,
        path: Any = None,
        content: Any = None,
        metadata: Any = None,
        agent_id: Any = None,
    ) -> dict[str, Any]:
        """Register an artifact, emitting ``artifact.created`` atomically.

        Validation order (all BEFORE any write, so failures persist nothing):
        workspace resolution -> artifact_type whitelist -> at-least-one of
        path|content -> inline size ceiling -> JSON well-formedness -> path
        containment. Returns
        ``{artifact_id, workspace_id, artifact_type, stored, path?, size_bytes,
        created_at}``.
        """
        workspace_id, root_realpath = self._resolve_workspace(project_root)
        norm_type = normalize_artifact_type(artifact_type)

        has_content = content is not None
        has_path = _is_nonempty_str(path)
        if not has_content and not has_path:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "artifact_put requires at least one of 'path' or 'content'.",
                {},
            )

        size_bytes = 0
        if has_content:
            if not isinstance(content, str):
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    "content must be a UTF-8 string for inline storage.",
                    {"content_type": type(content).__name__},
                )
            # Size ceiling first (a too-large JSON string is rejected by size,
            # not by an expensive parse), then JSON well-formedness.
            size_bytes = ensure_within_inline_limit(
                content, self._config.max_inline_bytes
            )
            if norm_type == "json":
                ensure_well_formed_json(content)

        # Whenever a path is supplied it MUST be contained, even alongside
        # content (FR6): a path escaping the root fails the whole put.
        resolved_path: str | None = None
        if has_path:
            resolved_path = self._files.resolve(root_realpath, path)

        if has_content:
            stored = STORED_INLINE
            stored_content: str | None = content
            stored_path: str | None = None
        else:
            stored = STORED_PATH
            stored_content = None
            stored_path = resolved_path
            size_bytes = self._path_size(resolved_path)

        metadata_blob = self._serialize_metadata(metadata)
        now = self._clock.now_iso()
        artifact_id = new_id("art")

        with self._put_uow(workspace_id=workspace_id, agent_id=agent_id) as uow:
            # Permission gate (migration 011): ``agent_id`` is the OPTIONAL
            # caller identity - the HTTP transport passes the authenticated
            # agent; cooperative stdio has none (default-allow).
            permission_set_for(self._agents, uow, agent_id).require("artifacts", "put")
            # Governance gate (spec 80624c1a): deny + quotas from the publisher's
            # attached policies, composed and evaluated PRE-persistence in this
            # same UoW (no bindings = no governance inside enforce() - BR2).
            # Without a caller identity there are no bindings, so nothing bites.
            audience_snapshot: list[Any] | None = None
            if self._governance is not None:
                self._governance.enforce(
                    uow,
                    agent_id=agent_id,
                    action=ACTION_ARTIFACT_PUT,
                    size_bytes=size_bytes,
                )
                # Freeze the publisher's EFFECTIVE OUTBOUND as this artifact's
                # audience (D-ART/D11), captured in the SAME UoW so it reflects
                # exactly the bindings enforced above and never changes again.
                # Empty -> None (a publisher with no outbound restriction, or no
                # bindings, writes a NULL audience = public, zero-regression).
                audience_snapshot = (
                    self._governance.outbound_snapshot_for(uow, agent_id=agent_id)
                    or None
                )
            # Ensure the workspace row exists for the FK (idempotent upsert);
            # the client passed project_root, the server owns the identity.
            self._workspaces.upsert(
                uow,
                workspace_id=workspace_id,
                root_realpath=root_realpath,
                last_seen_at=now,
            )
            artifact = self._artifacts.create(
                uow,
                artifact_id=artifact_id,
                workspace_id=workspace_id,
                artifact_type=norm_type,
                name=name,
                path=stored_path,
                content=stored_content,
                size_bytes=size_bytes,
                content_type=metadata_blob,
                created_by=str(agent_id)
                if isinstance(agent_id, str) and agent_id.strip()
                else None,
                created_at=now,
                audience=audience_snapshot,
            )
            # artifact.created is emitted INSIDE the same uow so the row and the
            # event (with its server-assigned event_id) commit atomically (BR7).
            self._emit_created(uow, artifact=artifact, stored=stored)

        data: dict[str, Any] = {
            "artifact_id": artifact.artifact_id,
            "workspace_id": artifact.workspace_id,
            "artifact_type": artifact.artifact_type,
            "stored": stored,
            "size_bytes": artifact.size_bytes,
            "created_at": artifact.created_at,
        }
        if stored == STORED_PATH:
            data["path"] = artifact.path
        return data

    # ------------------------------------------------------------------ #
    # artifact_get
    # ------------------------------------------------------------------ #
    def artifact_get(
        self, *, project_root: Any, artifact_id: Any, agent_id: Any = None
    ) -> dict[str, Any]:
        """Retrieve an artifact by id within the resolved workspace.

        Unknown ids and ids owned by another workspace both surface as
        ``NOT_FOUND`` with no field leakage (FR10 / BR9). ``stored=path`` returns
        only the path + metadata, never the referenced file's bytes (FR11/BR10).

        Audience gate (D-ART/BR7): when the artifact froze an outbound audience
        at ``artifact_put`` time, a reader whose tags do NOT satisfy it is
        answered EXACTLY like a missing id - same ``NOT_FOUND``, same details, no
        confirmation the artifact exists. ``agent_id`` is the OPTIONAL reader
        identity (the HTTP transport passes the authenticated agent; cooperative
        stdio has none). A NULL/empty audience (legacy rows, or an unrestricted
        publisher) permits every reader, so pre-policy artifacts stay public.
        """
        workspace_id, _root = self._resolve_workspace(project_root)
        if not _is_nonempty_str(artifact_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "artifact_id is required.",
                {"artifact_id": artifact_id},
            )

        with self._cf.unit_of_work() as uow:
            artifact = self._artifacts.get(
                uow, workspace_id=workspace_id, artifact_id=artifact_id
            )
            reader_tags = (
                self._reader_tags(uow, agent_id) if artifact is not None else None
            )
        if artifact is None or not snapshot_permits(artifact.audience, reader_tags):
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "artifact_id not found in the resolved workspace.",
                {"artifact_id": artifact_id},
            )

        stored = STORED_INLINE if artifact.content is not None else STORED_PATH
        data: dict[str, Any] = {
            "artifact_id": artifact.artifact_id,
            "workspace_id": artifact.workspace_id,
            "artifact_type": artifact.artifact_type,
            "stored": stored,
            "size_bytes": artifact.size_bytes,
            "metadata": self._deserialize_metadata(artifact.content_type),
            "created_at": artifact.created_at,
        }
        if stored == STORED_INLINE:
            data["content"] = artifact.content
        else:
            data["path"] = artifact.path
        return data

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _resolve_workspace(self, project_root: Any) -> tuple[str, str]:
        """Resolve ``(workspace_id, root_realpath)`` from a client project_root.

        ``WORKSPACE_REQUIRED`` when absent/blank; ``WORKSPACE_UNRESOLVED`` when
        realpath cannot be resolved (broken symlink / missing). Never falls back
        to a default/shared workspace (FR0 / BR1).
        """
        if not _is_nonempty_str(project_root):
            raise OktoNexusError(
                ErrorCode.WORKSPACE_REQUIRED,
                "project_root is required to resolve the workspace.",
                {},
            )
        root_realpath = resolve_realpath(project_root)  # WORKSPACE_UNRESOLVED
        workspace_id = resolve_workspace_id(project_root)
        return workspace_id, root_realpath

    def _reader_tags(self, uow: UnitOfWork, agent_id: Any) -> Any:
        """The reader's tags for the artifact-audience gate (FR7/BR7).

        The audience snapshot is the publisher's OUTBOUND selector; a read is
        permitted iff the READER's tags satisfy it (:func:`snapshot_permits`).
        Returns ``None`` (no tags) when there is no reader identity, no agent
        repo is wired, or the id is unknown - so a restrictive audience hides the
        artifact from a tag-less reader (fail-safe), while a NULL audience still
        permits everyone.
        """
        if self._agents is None or not _is_nonempty_str(agent_id):
            return None
        agent = self._agents.get(uow, str(agent_id))
        return getattr(agent, "tags", None) if agent is not None else None

    def _path_size(self, abs_path: str | None) -> int:
        """Return the on-disk byte size of a referenced file (metadata only).

        Uses ``stat`` (never reads the bytes), returning ``0`` when the file does
        not yet exist or cannot be stat-ed.
        """
        if not abs_path:
            return 0
        try:
            if os.path.isfile(abs_path):
                return int(os.path.getsize(abs_path))
        except OSError:
            return 0
        return 0

    def _serialize_metadata(self, metadata: Any) -> str | None:
        if metadata is None:
            return None
        try:
            return json.dumps(metadata, ensure_ascii=False)
        except (TypeError, ValueError):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "metadata must be JSON-serialisable.",
                {"metadata_type": type(metadata).__name__},
            ) from None

    @staticmethod
    def _deserialize_metadata(blob: str | None) -> dict[str, Any]:
        if blob is None:
            return {}
        try:
            loaded = json.loads(blob)
        except (ValueError, TypeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def _emit_created(
        self, uow: UnitOfWork, *, artifact: Any, stored: str
    ) -> int | None:
        """Emit ``artifact.created`` inside ``uow`` (skipped when unwired).

        The payload carries ``workspace_id, artifact_id, artifact_type,
        size_bytes, created_at`` (plus ``stored``/``path``); the global
        monotonic ``event_id`` is assigned by the Event Log inside this same
        transaction (contract imported, not redefined - FR12).
        """
        if self._emitter is None:
            return None
        payload: dict[str, Any] = {
            "workspace_id": artifact.workspace_id,
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "stored": stored,
            "size_bytes": artifact.size_bytes,
            "created_at": artifact.created_at,
        }
        if stored == STORED_PATH and artifact.path is not None:
            payload["path"] = artifact.path
        # The event carries the SAME audience as the artifact (BR7): the frozen
        # outbound snapshot is folded into ONE rich-form tag selector, so an
        # out-of-audience agent never sees artifact.created on the stream (the
        # stream must not leak what artifact_get hides). No audience -> the
        # historic public, target-less event. target is always a ROUTING RULE,
        # never a bare entity id (the id already rides in the payload).
        visibility, target = self._audience_event_scope(artifact.audience)
        return self._emitter.emit(
            uow,
            workspace_id=artifact.workspace_id,
            stream=ARTIFACT_STREAM,
            type=ARTIFACT_CREATED_EVENT,
            payload=payload,
            visibility=visibility,
            target=target,
        )

    @staticmethod
    def _audience_event_scope(audience: Any) -> tuple[str, dict[str, Any] | None]:
        """Map a frozen artifact-audience snapshot to (visibility, event target).

        Empty/NULL audience -> ``(public, None)``: the historic workspace-wide
        event, so legacy rows and unrestricted publishers stay byte-identical.
        Otherwise the snapshot's AND is folded LOSSLESSLY into ONE rich-form
        ``tag`` selector (:func:`snapshot_to_selector`) and the event goes out
        ``eligible`` - an agent sees it IFF its tags satisfy the same AND that
        gates ``artifact_get`` (BR7 - identical audience, no leak, no over-hide).
        """
        selector = snapshot_to_selector(audience)
        if selector is None:
            return ARTIFACT_VISIBILITY, None
        return ARTIFACT_SCOPED_VISIBILITY, {"strategy": "tag", "selector": selector}
