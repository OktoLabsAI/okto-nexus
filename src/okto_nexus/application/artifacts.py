"""Artifacts slice application service.

Implements the two artifact use cases of Okto Nexus V1:

* ``artifact_put`` - register a ``file``/``text``/``json``/``markdown``/``html``
  artifact
  in the workspace resolved from ``project_root``. Requires at least one of
  ``path`` or ``content``; enforces the 64 KB inline limit (inclusive), JSON
  well-formedness for ``json`` artifacts, and workspace-root containment for
  ``path`` references. On success it writes the payload through the injected
  ``ArtifactStore``, persists only searchable catalog metadata in SQLite and
  emits ``artifact.created`` in the SAME unit of work.
* ``artifact_get`` - retrieve an artifact by id within the resolved workspace;
  cross-workspace / unknown ids surface as ``NOT_FOUND`` (never a leak). It
  never reads external files: ``stored=path`` returns the path + metadata only.

Application layer: depends only on the ports in
:mod:`okto_nexus.application.ports`, the pure :mod:`okto_nexus.domain` helpers,
the error catalogue and :class:`NexusConfig`. It NEVER imports ``sqlite3`` nor
``mcp`` (enforced by the import-boundary test). Every coordinated mutation and
its audit event commit atomically through a single injected unit of work.

Free-form artifact metadata lives beside the payload in the store manifest.
The legacy ``content``/``content_type`` database columns remain readable only
for compatibility with stores created before migration 028.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from typing import Any, Optional

from ..config import NexusConfig
from ..domain.artifacts import (
    ARTIFACT_CREATED_EVENT,
    ARTIFACT_STREAM,
    STORED_INLINE,
    STORED_PATH,
    StoredArtifactPayload,
    ensure_well_formed_json,
    ensure_within_inline_limit,
    normalize_artifact_type,
)
from ..domain.base import new_id
from ..domain.governance import ACTION_ARTIFACT_PUT
from ..domain.ids import resolve_realpath, resolve_workspace_id
from ..domain.models import Artifact
from ..domain.policy import snapshot_permits, snapshot_to_selector
from ..errors import ErrorCode, OktoNexusError
from .governance import GovernanceService
from .guardrails import GuardrailService
from .permissions import permission_set_for
from .ports import (
    AgentRepo,
    ArtifactRepo,
    ArtifactStore,
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


def _date_bound(value: str | None, *, end_of_day: bool) -> str | None:
    if value is None or not value.strip():
        return None
    raw = value.strip()
    try:
        if len(raw) == 10:
            parsed_date = date.fromisoformat(raw)
            parsed = datetime.combine(
                parsed_date,
                time.max if end_of_day else time.min,
                tzinfo=timezone.utc,
            )
        else:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            parsed = parsed.astimezone(timezone.utc)
    except ValueError:
        raise OktoNexusError(
            ErrorCode.VALIDATION_ERROR,
            "Artifact date filters must be ISO dates or timestamps.",
            {"value": value},
        ) from None
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


def externalize_legacy_artifacts(
    *,
    connection_factory: ConnectionFactory,
    artifacts: ArtifactRepo,
    artifact_store: ArtifactStore,
) -> dict[str, int]:
    """Move legacy SQLite payloads into the configured artifact store.

    This bootstrap migration is deliberately idempotent. Each successfully
    copied artifact is repointed and has ``path``, ``content`` and
    ``content_type`` cleared in one database transaction. Missing legacy path
    references are left untouched because silently inventing payload bytes
    would corrupt the artifact; inline payloads are always migrated.
    """
    with connection_factory.unit_of_work(write=False) as uow:
        legacy = artifacts.list_legacy(uow)

    migrated = 0
    skipped = 0
    for artifact in legacy:
        if artifact.content is None and (
            artifact.path is None or not os.path.isfile(artifact.path)
        ):
            skipped += 1
            continue
        stored = STORED_INLINE if artifact.content is not None else STORED_PATH
        descriptor: StoredArtifactPayload | None = None
        try:
            descriptor = artifact_store.put(
                workspace_id=artifact.workspace_id,
                agent_id=artifact.created_by,
                artifact_id=artifact.artifact_id,
                artifact_type=artifact.artifact_type,
                storage_kind=stored,
                name=artifact.name,
                content=artifact.content,
                source_path=artifact.path if stored == STORED_PATH else None,
                metadata=ArtifactService._deserialize_metadata(
                    artifact.content_type
                ),
                created_at=artifact.created_at,
            )
            with connection_factory.unit_of_work() as uow:
                artifacts.set_external_storage(
                    uow,
                    artifact_id=artifact.artifact_id,
                    storage_path=descriptor.storage_path,
                    storage_kind=descriptor.storage_kind,
                    filename=descriptor.filename,
                    media_type=descriptor.media_type,
                    size_bytes=descriptor.size_bytes,
                )
            migrated += 1
        except Exception:
            if descriptor is not None:
                artifact_store.delete(descriptor.storage_path)
            raise
    return {"migrated": migrated, "skipped": skipped}


class ArtifactService:
    """Use-case orchestration for ``artifact_put`` / ``artifact_get``."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        artifacts: ArtifactRepo,
        artifact_store: ArtifactStore,
        workspaces: WorkspaceRepo,
        files: FileStore,
        clock: Clock,
        config: NexusConfig,
        event_emitter: Optional[EventEmitter] = None,
        agents: Optional[AgentRepo] = None,
        governance: Optional[GovernanceService] = None,
        guardrails: Optional[GuardrailService] = None,
    ) -> None:
        self._cf = connection_factory
        self._agents = agents
        self._artifacts = artifacts
        self._artifact_store = artifact_store
        self._workspaces = workspaces
        self._files = files
        self._clock = clock
        self._config = config
        self._emitter = event_emitter
        # Policy enforcement (spec 80624c1a): when wired, artifact_put is
        # enforced pre-persistence against the publisher's attached policies;
        # None = no gate (and no bindings = no gate either).
        self._governance = governance
        # Communication guardrails: when wired, artifact fields are evaluated
        # after pure artifact validation and before persistence/event emission.
        self._guardrails = guardrails

    @contextmanager
    def _put_uow(
        self,
        *,
        workspace_id: str,
        agent_id: Any,
    ):
        """The write UoW for artifact_put: guardrail/governance audited.

        A denial rolls back the main UoW, then the owning service emits its
        scrubbed audit event in a separate UoW. Guardrails run before any
        artifact row or artifact.created event can persist.
        """
        try:
            with self._cf.unit_of_work() as uow:
                yield uow
        except OktoNexusError as exc:
            if self._guardrails is not None:
                self._guardrails.emit_denied(
                    workspace_id=workspace_id,
                    actor_agent_id=agent_id,
                    exc=exc,
                )
            if self._governance is not None:
                self._governance.emit_denied(
                    workspace_id=workspace_id,
                    agent_id=agent_id,
                    exc=exc,
                )
            raise

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
        metadata_value = self._deserialize_metadata(metadata_blob)
        now = self._clock.now_iso()
        artifact_id = new_id("art")
        guardrail_fields: dict[str, Any] = {
            "artifact_type": norm_type,
            "name": name,
            "content": content if has_content else None,
            "metadata": metadata,
            "path": resolved_path if has_path else None,
            "path_reference": resolved_path if has_path else None,
        }

        stored_payload: StoredArtifactPayload | None = None
        artifact: Artifact | None = None
        try:
            with self._put_uow(workspace_id=workspace_id, agent_id=agent_id) as uow:
                # Permission gate (migration 011): ``agent_id`` is the OPTIONAL
                # caller identity - the HTTP transport passes the authenticated
                # agent; cooperative stdio has none (default-allow).
                permission_set_for(self._agents, uow, agent_id).require(
                    "artifacts", "put"
                )
                # Ensure the workspace row exists before the catalog FK is needed.
                self._workspaces.upsert(
                    uow,
                    workspace_id=workspace_id,
                    root_realpath=root_realpath,
                    last_seen_at=now,
                )
                if (
                    self._guardrails is not None
                    and self._guardrails.has_enabled_assignments(uow)
                ):
                    self._guardrails.enforce(
                        uow,
                        workspace_id=workspace_id,
                        actor_agent_id=agent_id,
                        surface="artifact_put",
                        fields=guardrail_fields,
                    )
                # Governance runs before filesystem persistence.  The database
                # keeps the minimal authorship fields used by quotas, never the
                # artifact payload itself.
                audience_snapshot: list[Any] | None = None
                if self._governance is not None:
                    self._governance.enforce(
                        uow,
                        agent_id=agent_id,
                        action=ACTION_ARTIFACT_PUT,
                        size_bytes=size_bytes,
                    )
                    audience_snapshot = (
                        self._governance.outbound_snapshot_for(uow, agent_id=agent_id)
                        or None
                    )

                stored_payload = self._artifact_store.put(
                    workspace_id=workspace_id,
                    agent_id=(
                        str(agent_id)
                        if isinstance(agent_id, str) and agent_id.strip()
                        else None
                    ),
                    artifact_id=artifact_id,
                    artifact_type=norm_type,
                    storage_kind=stored,
                    name=name,
                    content=stored_content,
                    source_path=stored_path,
                    metadata=metadata_value,
                    created_at=now,
                )
                artifact = self._artifacts.create(
                    uow,
                    artifact_id=artifact_id,
                    workspace_id=workspace_id,
                    artifact_type=norm_type,
                    name=name,
                    # Payload, source path and free-form metadata are owned by
                    # ArtifactStore.  These legacy DB columns stay NULL.
                    path=None,
                    content=None,
                    size_bytes=stored_payload.size_bytes,
                    content_type=None,
                    created_by=str(agent_id)
                    if isinstance(agent_id, str) and agent_id.strip()
                    else None,
                    created_at=now,
                    audience=audience_snapshot,
                    storage_path=stored_payload.storage_path,
                    storage_kind=stored_payload.storage_kind,
                    filename=stored_payload.filename,
                    media_type=stored_payload.media_type,
                )
                # Catalog row + event are transactional.  A failure removes the
                # already-written payload below as a compensating action.
                self._emit_created(uow, artifact=artifact, stored=stored)
        except Exception:
            if stored_payload is not None:
                self._artifact_store.delete(stored_payload.storage_path)
            raise

        if artifact is None or stored_payload is None:  # pragma: no cover
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "Artifact persistence completed without a catalog row.",
                {"artifact_id": artifact_id},
            )
        data: dict[str, Any] = {
            "artifact_id": artifact.artifact_id,
            "workspace_id": artifact.workspace_id,
            "artifact_type": artifact.artifact_type,
            "stored": stored,
            "size_bytes": stored_payload.size_bytes,
            "created_at": artifact.created_at,
        }
        if stored == STORED_PATH:
            data["path"] = stored_payload.source_path
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

        stored, descriptor = self._storage_descriptor(artifact)
        data: dict[str, Any] = {
            "artifact_id": artifact.artifact_id,
            "workspace_id": artifact.workspace_id,
            "artifact_type": artifact.artifact_type,
            "stored": stored,
            "size_bytes": artifact.size_bytes,
            "metadata": (
                descriptor.metadata
                if descriptor
                else self._deserialize_metadata(artifact.content_type)
            ),
            "created_at": artifact.created_at,
        }
        if stored == STORED_INLINE:
            data["content"] = (
                self._artifact_store.read_text(artifact.storage_path)
                if artifact.storage_path
                else artifact.content
            )
        else:
            data["path"] = descriptor.source_path if descriptor else artifact.path
        return data

    # ------------------------------------------------------------------ #
    # Operator dashboard reads
    # ------------------------------------------------------------------ #
    def browse(
        self,
        *,
        workspace_id: str,
        artifact_type: str | None = None,
        producer_ids: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        """Page lean artifact catalog entries for the operator dashboard."""
        norm_type = normalize_artifact_type(artifact_type) if artifact_type else None
        try:
            safe_page = max(1, int(page))
            safe_page_size = max(1, min(int(page_size), 100))
        except (TypeError, ValueError):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "page and page_size must be integers.",
                {"page": page, "page_size": page_size},
            ) from None
        producers = list(
            dict.fromkeys(
                producer.strip()
                for producer in (producer_ids or [])
                if isinstance(producer, str) and producer.strip()
            )
        )
        created_from = _date_bound(date_from, end_of_day=False)
        created_to = _date_bound(date_to, end_of_day=True)
        if created_from and created_to and created_from > created_to:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "date_from must be before or equal to date_to.",
                {"date_from": date_from, "date_to": date_to},
            )
        offset = (safe_page - 1) * safe_page_size
        with self._cf.unit_of_work(write=False) as uow:
            rows, total = self._artifacts.browse_catalog(
                uow,
                workspace_id=None if workspace_id == "all" else workspace_id,
                artifact_type=norm_type,
                producer_ids=producers,
                created_from=created_from,
                created_to=created_to,
                query=(query or "").strip() or None,
                limit=safe_page_size,
                offset=offset,
            )
        items = [
            self._operator_shape(row, include_content=False)
            for row in rows
        ]
        total_pages = (total + safe_page_size - 1) // safe_page_size
        return {
            "count": len(items),
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": total_pages,
            "items": items,
        }

    def get_for_operator(self, *, workspace_id: str, artifact_id: str) -> dict[str, Any]:
        """Return one artifact without the agent-audience gate."""
        if not _is_nonempty_str(artifact_id):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "artifact_id is required.",
                {"artifact_id": artifact_id},
            )
        artifact = self._find_operator_artifact(
            workspace_id=workspace_id, artifact_id=str(artifact_id)
        )
        if artifact is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "artifact_id not found in the resolved workspace.",
                {"artifact_id": artifact_id},
            )
        return self._operator_shape(artifact, include_content=True)

    def payload_for_operator(
        self, *, workspace_id: str, artifact_id: str
    ) -> tuple[bytes, str, str]:
        """Return payload bytes, media type and filename for preview/download."""
        artifact = self._find_operator_artifact(
            workspace_id=workspace_id, artifact_id=artifact_id
        )
        if artifact is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "artifact_id not found in the resolved workspace.",
                {"artifact_id": artifact_id},
            )
        if artifact.storage_path:
            descriptor = self._artifact_store.describe(artifact.storage_path)
            return (
                self._artifact_store.read_bytes(artifact.storage_path),
                descriptor.media_type,
                descriptor.filename,
            )
        if artifact.content is not None:
            return (
                artifact.content.encode("utf-8"),
                artifact.media_type or "text/plain",
                artifact.filename or artifact.name or f"{artifact.artifact_id}.txt",
            )
        raise OktoNexusError(
            ErrorCode.NOT_FOUND,
            "Artifact payload is not available in managed storage.",
            {"artifact_id": artifact_id},
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _find_operator_artifact(
        self, *, workspace_id: str, artifact_id: str
    ) -> Artifact | None:
        with self._cf.unit_of_work(write=False) as uow:
            if workspace_id != "all":
                return self._artifacts.get(
                    uow, workspace_id=workspace_id, artifact_id=artifact_id
                )
            return next(
                (
                    item
                    for item in self._artifacts.list_all(uow)
                    if item.artifact_id == artifact_id
                ),
                None,
            )

    def _storage_descriptor(
        self, artifact: Artifact
    ) -> tuple[str, StoredArtifactPayload | None]:
        if artifact.storage_path:
            descriptor = self._artifact_store.describe(artifact.storage_path)
            return artifact.storage_kind or descriptor.storage_kind, descriptor
        legacy_kind = STORED_INLINE if artifact.content is not None else STORED_PATH
        return legacy_kind, None

    def _operator_shape(
        self, artifact: Artifact, *, include_content: bool
    ) -> dict[str, Any]:
        if artifact.storage_path and not include_content:
            stored = artifact.storage_kind or STORED_PATH
            descriptor = None
        else:
            stored, descriptor = self._storage_descriptor(artifact)
        filename = (
            descriptor.filename
            if descriptor
            else artifact.filename
            or artifact.name
            or artifact.artifact_id
        )
        metadata = descriptor.metadata if descriptor else {}
        if not artifact.storage_path:
            metadata = self._deserialize_metadata(artifact.content_type)
        available = bool(artifact.storage_path or artifact.content is not None)
        data: dict[str, Any] = {
            "artifact_id": artifact.artifact_id,
            "workspace_id": artifact.workspace_id,
            "artifact_type": artifact.artifact_type,
            "name": artifact.name,
            "filename": filename,
            "stored": stored,
            "size_bytes": artifact.size_bytes or 0,
            "media_type": (
                descriptor.media_type
                if descriptor
                else artifact.media_type or "application/octet-stream"
            ),
            "created_by": artifact.created_by,
            "created_at": artifact.created_at,
            "metadata": metadata,
            "managed": artifact.storage_path is not None,
            "available": available,
        }
        if stored == STORED_PATH:
            data["source_path"] = (
                descriptor.source_path if descriptor else artifact.path
            )
        if include_content and available and self._is_text_preview(artifact, data):
            data["content"] = (
                self._artifact_store.read_text(artifact.storage_path)
                if artifact.storage_path
                else artifact.content
            )
        return data

    @staticmethod
    def _is_text_preview(artifact: Artifact, data: dict[str, Any]) -> bool:
        media_type = str(data.get("media_type") or "").lower()
        return artifact.artifact_type in {"text", "json", "markdown", "html"} or (
            media_type.startswith("text/") or media_type == "application/json"
        )

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
