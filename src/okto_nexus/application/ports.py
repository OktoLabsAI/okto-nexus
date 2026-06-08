"""Application ports - the contracts that domain slices implement.

These :class:`typing.Protocol` definitions are the seams of the hexagonal
architecture. Inbound adapters (MCP tools) depend on them; outbound adapters
(SQLite repos, file store, clock) implement them. Dependencies point INWARD.

Conventions (normative for all slices):

* **UoW-first**: every repository method takes a :class:`UnitOfWork` as its
  first positional argument and operates on ``uow.connection``. Writes happen
  inside the active transaction; reads share the same connection. This keeps
  event emission and state mutation atomic within a single transaction.
* **Keyword-only payloads**: fields after ``uow`` are keyword-only for
  forward compatibility.
* **workspace_id everywhere**: every coordinated read/write is scoped by
  ``workspace_id``; no cross-workspace access.
* **Domain dataclasses**: methods return the dataclasses from
  :mod:`okto_nexus.domain.models`; ``get`` returns ``None`` when absent.

This module is pure: it never imports ``sqlite3`` or ``mcp`` (enforced by the
import boundary test). The concrete connection type is referenced as ``Any``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ..domain.models import (
    Agent,
    Artifact,
    Channel,
    Event,
    Handoff,
    Message,
    Session,
    Task,
    Workspace,
)

# A concrete DB connection (``sqlite3.Connection`` in the adapter). Typed as
# ``Any`` here to keep the application layer free of ``sqlite3``.
Connection = Any


# --------------------------------------------------------------------------- #
# Infrastructure ports
# --------------------------------------------------------------------------- #
@runtime_checkable
class Clock(Protocol):
    """Source of time. Injected so slices/tests stay deterministic."""

    def now_iso(self) -> str:
        """Return current UTC time as ISO-8601 with a ``Z`` suffix."""
        ...

    def now_epoch(self) -> float:
        """Return current time as a POSIX epoch (seconds, float)."""
        ...


@runtime_checkable
class UnitOfWork(Protocol):
    """Transactional scope wrapping a single DB connection.

    Used as a context manager: ``with uow_factory() as uow: ...``. On clean
    exit the transaction is committed; on exception it is rolled back. The live
    connection is exposed via :attr:`connection`.
    """

    connection: Connection

    def __enter__(self) -> "UnitOfWork":
        ...

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool | None:
        ...

    def commit(self) -> None:
        """Commit the active transaction."""
        ...

    def rollback(self) -> None:
        """Roll back the active transaction."""
        ...


@runtime_checkable
class ConnectionFactory(Protocol):
    """Creates connections / units of work against the SQLite store."""

    def get_connection(self) -> Connection:
        """Return a configured connection (PRAGMAs applied, ``Row`` factory)."""
        ...

    def unit_of_work(self) -> UnitOfWork:
        """Return a fresh :class:`UnitOfWork` bound to a new connection."""
        ...


# --------------------------------------------------------------------------- #
# Workspace / agent / session
# --------------------------------------------------------------------------- #
@runtime_checkable
class WorkspaceRepo(Protocol):
    """Persistence for :class:`Workspace` rows (keyed by ``workspace_id``)."""

    def upsert(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        display_name: str | None = None,
        root_realpath: str | None = None,
        last_seen_at: str | None = None,
    ) -> Workspace:
        """Insert or update the workspace, returning the stored row."""
        ...

    def get(self, uow: UnitOfWork, workspace_id: str) -> Workspace | None:
        """Return the workspace, or ``None`` if it does not exist."""
        ...


@runtime_checkable
class AgentRepo(Protocol):
    """Persistence for :class:`Agent` rows (global identities)."""

    def upsert(
        self,
        uow: UnitOfWork,
        *,
        agent_id: str,
        role: str | None = None,
        capabilities: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Agent:
        """Insert or update the agent, returning the stored row."""
        ...

    def get(self, uow: UnitOfWork, agent_id: str) -> Agent | None:
        """Return the agent, or ``None`` if it does not exist."""
        ...


@runtime_checkable
class SessionRepo(Protocol):
    """Persistence for :class:`Session` rows (workspace-scoped)."""

    def create(
        self,
        uow: UnitOfWork,
        *,
        session_id: str,
        agent_id: str,
        workspace_id: str,
        status: str,
        started_at: str | None = None,
    ) -> Session:
        """Create a session, returning the stored row."""
        ...

    def get(self, uow: UnitOfWork, session_id: str) -> Session | None:
        """Return the session, or ``None`` if it does not exist."""
        ...

    def heartbeat(
        self, uow: UnitOfWork, *, session_id: str, at: str | None = None
    ) -> Session:
        """Update ``last_heartbeat_at``; raise ``NOT_FOUND`` if missing."""
        ...

    def list(
        self, uow: UnitOfWork, *, workspace_id: str, status: str | None = None
    ) -> list[Session]:
        """List sessions in a workspace, optionally filtered by status."""
        ...


# --------------------------------------------------------------------------- #
# Events (append-only log) + emitter facade
# --------------------------------------------------------------------------- #
@runtime_checkable
class EventRepo(Protocol):
    """Append-only, immutable event log. ``event_id`` is global & monotonic."""

    def append(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        stream: str,
        type: str,
        payload: Mapping[str, Any] | None = None,
        actor_agent_id: str | None = None,
        visibility: str | None = None,
        target: str | None = None,
    ) -> int:
        """Append one event INSIDE ``uow``'s transaction; return its ``event_id``."""
        ...

    def list_after(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        stream: str,
        cursor: int = 0,
        limit: int = 100,
        filters: Mapping[str, Any] | None = None,
    ) -> list[Event]:
        """Return events with ``event_id > cursor`` for a stream, oldest first."""
        ...


@runtime_checkable
class EventEmitter(Protocol):
    """Thin facade over :class:`EventRepo` so slices emit within the SAME uow.

    Slices that mutate state call :meth:`emit` with the active ``uow`` so the
    event and the state change commit atomically.
    """

    def emit(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        stream: str,
        type: str,
        payload: Mapping[str, Any] | None = None,
        actor_agent_id: str | None = None,
        visibility: str | None = None,
        target: str | None = None,
    ) -> int:
        """Emit an event inside ``uow``; return the assigned ``event_id``."""
        ...


# --------------------------------------------------------------------------- #
# Channels / messages
# --------------------------------------------------------------------------- #
@runtime_checkable
class ChannelRepo(Protocol):
    """Persistence for :class:`Channel` rows (unique per ``(workspace, name)``)."""

    def create(
        self,
        uow: UnitOfWork,
        *,
        channel_id: str,
        workspace_id: str,
        name: str,
        created_at: str | None = None,
    ) -> Channel:
        """Create a channel, returning the stored row."""
        ...

    def get(
        self, uow: UnitOfWork, *, workspace_id: str, channel_id: str
    ) -> Channel | None:
        """Return the channel by id, or ``None``."""
        ...

    def get_by_name(
        self, uow: UnitOfWork, *, workspace_id: str, name: str
    ) -> Channel | None:
        """Return the channel by name within a workspace, or ``None``."""
        ...

    def list(self, uow: UnitOfWork, *, workspace_id: str) -> list[Channel]:
        """List channels in a workspace."""
        ...


@runtime_checkable
class MessageRepo(Protocol):
    """Persistence for :class:`Message` rows (workspace-scoped)."""

    def create(
        self,
        uow: UnitOfWork,
        *,
        message_id: str,
        workspace_id: str,
        from_agent_id: str,
        channel_id: str | None = None,
        from_session_id: str | None = None,
        target: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        artifacts: Sequence[Any] | None = None,
        parent_message_id: str | None = None,
        created_at: str | None = None,
    ) -> Message:
        """Create a message, returning the stored row."""
        ...

    def get(
        self, uow: UnitOfWork, *, workspace_id: str, message_id: str
    ) -> Message | None:
        """Return the message, or ``None``."""
        ...

    def list(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        channel_id: str | None = None,
        target: str | None = None,
        limit: int = 100,
    ) -> list[Message]:
        """List messages, optionally filtered by channel or target."""
        ...


# --------------------------------------------------------------------------- #
# Tasks / handoffs / artifacts
# --------------------------------------------------------------------------- #
@runtime_checkable
class TaskRepo(Protocol):
    """Persistence for :class:`Task` rows (workspace-scoped)."""

    def create(
        self,
        uow: UnitOfWork,
        *,
        task_id: str,
        workspace_id: str,
        title: str,
        status: str,
        description: str | None = None,
        created_by: str | None = None,
        created_at: str | None = None,
    ) -> Task:
        """Create a task, returning the stored row."""
        ...

    def get(self, uow: UnitOfWork, *, workspace_id: str, task_id: str) -> Task | None:
        """Return the task, or ``None``."""
        ...

    def update_status(
        self, uow: UnitOfWork, *, workspace_id: str, task_id: str, status: str
    ) -> Task:
        """Set the task status; raise ``NOT_FOUND`` if missing."""
        ...

    def list(
        self, uow: UnitOfWork, *, workspace_id: str, status: str | None = None
    ) -> list[Task]:
        """List tasks in a workspace, optionally filtered by status."""
        ...


@runtime_checkable
class HandoffRepo(Protocol):
    """Persistence for :class:`Handoff` rows, including atomic claim semantics."""

    def create(
        self,
        uow: UnitOfWork,
        *,
        handoff_id: str,
        workspace_id: str,
        status: str,
        task_id: str | None = None,
        from_agent_id: str | None = None,
        target: str | None = None,
        visibility: str | None = None,
        created_at: str | None = None,
    ) -> Handoff:
        """Create a handoff, returning the stored row."""
        ...

    def get(
        self, uow: UnitOfWork, *, workspace_id: str, handoff_id: str
    ) -> Handoff | None:
        """Return the handoff, or ``None``."""
        ...

    def claim(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        handoff_id: str,
        claimed_by: str,
        lease_expires_at: str,
        updated_at: str | None = None,
    ) -> Handoff:
        """Atomically claim an eligible handoff.

        Raise ``HANDOFF_ALREADY_CLAIMED`` if already claimed (and lease valid),
        or ``NOT_ELIGIBLE_TO_CLAIM`` if the handoff is not in a claimable state.
        """
        ...

    def update_status(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        handoff_id: str,
        status: str,
        updated_at: str | None = None,
    ) -> Handoff:
        """Update the handoff status; raise ``NOT_FOUND`` if missing."""
        ...

    def list(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        status: str | None = None,
        target: str | None = None,
    ) -> list[Handoff]:
        """List handoffs, optionally filtered by status/target."""
        ...


@runtime_checkable
class ArtifactRepo(Protocol):
    """Persistence for :class:`Artifact` rows (inline content or path refs)."""

    def create(
        self,
        uow: UnitOfWork,
        *,
        artifact_id: str,
        workspace_id: str,
        artifact_type: str,
        name: str | None = None,
        path: str | None = None,
        content: str | None = None,
        size_bytes: int | None = None,
        content_type: str | None = None,
        created_at: str | None = None,
    ) -> Artifact:
        """Create an artifact, returning the stored row."""
        ...

    def get(
        self, uow: UnitOfWork, *, workspace_id: str, artifact_id: str
    ) -> Artifact | None:
        """Return the artifact, or ``None``."""
        ...

    def list(
        self, uow: UnitOfWork, *, workspace_id: str, artifact_type: str | None = None
    ) -> list[Artifact]:
        """List artifacts in a workspace, optionally filtered by type."""
        ...


# --------------------------------------------------------------------------- #
# Filesystem port
# --------------------------------------------------------------------------- #
@runtime_checkable
class FileStore(Protocol):
    """Workspace-contained filesystem access.

    All paths are resolved relative to ``workspace_root`` and must remain
    inside it; escapes raise ``PATH_OUTSIDE_WORKSPACE``.
    """

    def resolve(self, workspace_root: str, relative_path: str) -> str:
        """Resolve a workspace-relative path to an absolute real path.

        Raise ``PATH_OUTSIDE_WORKSPACE`` if the result escapes the root.
        """
        ...

    def exists(self, workspace_root: str, relative_path: str) -> bool:
        """Return whether the contained path exists."""
        ...

    def read_text(self, workspace_root: str, relative_path: str) -> str:
        """Read and return UTF-8 text from a contained path."""
        ...

    def write_text(self, workspace_root: str, relative_path: str, content: str) -> int:
        """Write UTF-8 text to a contained path; return bytes written."""
        ...


# --------------------------------------------------------------------------- #
# Repository registry
# --------------------------------------------------------------------------- #
@dataclass
class Repos:
    """Aggregate of all repository ports, injected via :class:`Deps`.

    Fields are ``None`` until the owning slice provides a concrete
    implementation; integration wiring populates them. Slices type-hint
    against the Protocols above, never the concrete classes.
    """

    workspaces: WorkspaceRepo | None = None
    agents: AgentRepo | None = None
    sessions: SessionRepo | None = None
    events: EventRepo | None = None
    channels: ChannelRepo | None = None
    messages: MessageRepo | None = None
    tasks: TaskRepo | None = None
    handoffs: HandoffRepo | None = None
    artifacts: ArtifactRepo | None = None
    files: FileStore | None = None
