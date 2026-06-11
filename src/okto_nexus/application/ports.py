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
    MessageDelivery,
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
class Waiter(Protocol):
    """Store-change notification - the blocking seam of the long-poll use cases.

    ``event_wait`` / ``handoff_list_available`` need to park a caller until the
    shared store *may* have changed. That blocking is TRANSPORT, not use-case
    logic, so it lives behind this port: the application layer never imports
    ``time.sleep`` and never decides *how* to wait, only *until when*.

    Contract:

    * :meth:`snapshot` captures an opaque change token. Callers MUST snapshot
      BEFORE scanning, so a write that lands between the scan and the wait is
      reported by the next :meth:`wait_for_change` instead of being slept
      through. Spurious change reports are allowed (the caller just re-scans);
      missed changes are not.
    * :meth:`wait_for_change` blocks the calling thread for at most
      ``timeout_s`` seconds and returns ``True`` iff the store changed since
      ``since`` (the caller should re-scan), ``False`` when the full timeout
      elapsed with no change (the caller may time out WITHOUT re-scanning -
      that is the cheap-re-scan guarantee).
    * :meth:`monotonic` is the waiter's own monotonic clock; deadline
      arithmetic must use it so blocking and time measurement share one time
      domain (deterministic fakes in tests, real time in production).

    The V1 implementation is ``SleepPollWaiter`` (adapters/outbound/waiter.py):
    an incremental sleep loop gated by SQLite's ``PRAGMA data_version`` probe
    exposed by the connection factory. A future push transport (SSE/HTTP
    notify, as promised in the server instructions) replaces it with a
    subscription-backed implementation - same port, ZERO changes to the
    application layer.
    """

    def monotonic(self) -> float:
        """Monotonic seconds in the waiter's own time domain."""
        ...

    def snapshot(self) -> Any:
        """Capture an opaque token of the store's current change state."""
        ...

    def wait_for_change(self, since: Any, timeout_s: float) -> bool:
        """Block up to ``timeout_s``; ``True`` iff the store changed since ``since``."""
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

    def unit_of_work(self, write: bool = True) -> UnitOfWork:
        """Return a fresh :class:`UnitOfWork` bound to a new connection.

        ``write=True`` (default) opens a WRITE transaction up front, so it is
        serialised against every other writer by SQLite's WAL single-writer
        lock. Pass ``write=False`` for strictly read-only use cases (peek /
        count / history-style polling): a read transaction never competes for
        the writer lock, so polling N agents does not serialise the bus.
        """
        ...

    def change_waiter(self) -> Waiter:
        """Return a :class:`Waiter` watching THIS store for committed changes.

        The default blocking seam for the long-poll use cases when no waiter is
        injected explicitly: the factory fronts the store, so it knows how to
        observe "a write was committed by any connection in any process". The
        SQLite implementation returns a ``SleepPollWaiter`` gated by a cached
        read-only ``PRAGMA data_version`` probe; a push transport substitutes
        its own waiter here without touching the application services.
        """
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

    def list_all(self, uow: UnitOfWork) -> list[Workspace]:
        """Return ALL workspaces (global-admin surface; NOT workspace-scoped).

        A deliberately cross-workspace read (as is :meth:`AgentRepo.list`, since
        agents are global identities). Every workspace/session-scoped read is
        keyed by ``workspace_id``.
        """
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

    def list(self, uow: UnitOfWork) -> list[Agent]:
        """Return ALL agents (global; identities are not workspace-scoped)."""
        ...

    def touch(
        self, uow: UnitOfWork, *, agent_id: str, at: str | None = None
    ) -> bool:
        """Best-effort stamp of ``last_seen_at`` for an agent's latest action.

        Returns ``True`` if the agent existed and was updated, ``False`` if no
        such agent is registered (a no-op; never raises ``NOT_FOUND``) - callers
        pass an actor id that may or may not be a registered identity.
        """
        ...

    def get_active_by_key_hash(
        self, uow: UnitOfWork, *, api_key_hash: str
    ) -> Agent | None:
        """Resolve an ACTIVE agent by its key hash (migration 009, D5).

        The authentication lookup: returns ``None`` both for an unknown hash
        and for a matching agent with ``is_active = False`` - callers must
        not distinguish the two (uniform auth failure).
        """
        ...

    def set_key_hash(
        self, uow: UnitOfWork, *, agent_id: str, api_key_hash: str | None
    ) -> bool:
        """Set (or clear, with ``None``) the agent's key hash.

        Returns ``True`` if the agent existed. Replacing the hash is the
        regeneration primitive: the previous key stops resolving in the same
        transaction (immediate invalidation).
        """
        ...

    def set_active(
        self, uow: UnitOfWork, *, agent_id: str, is_active: bool
    ) -> bool:
        """Flip the revocation switch. Returns ``True`` if the agent existed."""
        ...

    def list_without_key(self, uow: UnitOfWork) -> list[Agent]:
        """Agents with no issued key (``api_key_hash IS NULL``), oldest first.

        The `admin issue-keys` batch-migration view (FR7): strictly additive,
        so agents that already hold a key are never returned.
        """
        ...

    def delete(self, uow: UnitOfWork, *, agent_id: str) -> bool:
        """Remove the agent row entirely. Returns ``True`` if it existed.

        Management-surface only (FR4): deactivation (``set_active``) is the
        normal revocation path; deletion is the irreversible cleanup.
        """
        ...


@runtime_checkable
class ObservabilityQueries(Protocol):
    """Read-only aggregate queries backing the dashboard (Nexus v2, FR3-FR6).

    Strictly observational: implementations must never write (br_5865bb88).
    Rows come back as plain dicts shaped by the adapter; the
    ``ObservabilityService`` derives presence and assembles the graph.
    """

    def agent_rows(self, uow: UnitOfWork) -> list[dict[str, Any]]:
        """All agents + their freshest ACTIVE session heartbeat (global)."""
        ...

    def inbox_counts(self, uow: UnitOfWork) -> dict[str, dict[str, int]]:
        """Per-agent delivery counts by lane (unread/delivered/read/parked)."""
        ...

    def message_edges(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None,
        since_iso: str,
    ) -> list[dict[str, Any]]:
        """Aggregated (from, to) message pairs inside the window, with in-flight."""
        ...

    def handoff_rows(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None,
        statuses: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        ...

    def channel_rows(
        self, uow: UnitOfWork, *, workspace_id: str | None
    ) -> list[dict[str, Any]]:
        ...

    def session_rows(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        ...

    def messages_page(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None,
        agent_id: str | None,
        channel_id: str | None,
        lane: str | None,
        since_iso: str | None,
        until_iso: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Paginated message history with per-recipient deliveries; (items, total)."""
        ...

    def events_after(
        self,
        uow: UnitOfWork,
        *,
        cursor: int,
        workspace_id: str | None,
        stream: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Event-log rows with ``event_id > cursor``, ascending (SSE/tail feed)."""
        ...


@runtime_checkable
class AuthProvider(Protocol):
    """Turns inbound credentials into agent identities (Nexus v2, D5/D6).

    The seam that keeps the HTTP transport SaaS-ready: the local
    implementation (:class:`okto_nexus.application.auth.AgentKeyAuthService`)
    resolves per-agent API keys against ``agents.api_key_hash``; a cloud
    deployment swaps in an IdP/RBAC-backed provider without touching the
    inbound adapters.
    """

    def issue_key(self, uow: UnitOfWork, *, agent_id: str) -> str:
        """Issue/rotate the agent's key; return the plaintext exactly once."""
        ...

    def set_active(
        self, uow: UnitOfWork, *, agent_id: str, is_active: bool
    ) -> bool:
        """Flip the revocation switch (dropping cached resolutions)."""
        ...

    def resolve(self, uow: UnitOfWork, api_key: str | None) -> Agent | None:
        """Resolve a credential to its ACTIVE agent; uniform ``None`` failure."""
        ...

    def invalidate_agent(self, agent_id: str) -> None:
        """Drop any cached resolution for the agent."""
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
        session_secret: str | None = None,
    ) -> Session:
        """Create a session, returning the stored row."""
        ...

    def get(self, uow: UnitOfWork, session_id: str) -> Session | None:
        """Return the session, or ``None`` if it does not exist."""
        ...

    def get_secret(self, uow: UnitOfWork, *, session_id: str) -> str | None:
        """Return the stored ``session_secret`` (or ``None``).

        ``None`` for an unknown session AND for a pre-007 row (NULL column);
        callers distinguish via :meth:`get`. The secret never travels on the
        :class:`Session` dataclass, so read surfaces cannot leak it.
        """
        ...

    def heartbeat(
        self, uow: UnitOfWork, *, session_id: str, at: str | None = None
    ) -> Session:
        """Update ``last_heartbeat_at``; raise ``NOT_FOUND`` if missing."""
        ...

    def close(
        self, uow: UnitOfWork, *, session_id: str, at: str | None = None
    ) -> Session:
        """Idempotently close a session, returning the stored row.

        Sets ``status='closed'`` and ``closed_at`` only when the session is not
        already closed; repeating the call is a no-op that keeps the row closed
        (the original ``closed_at`` is preserved). Raises ``NOT_FOUND`` when the
        session does not exist.
        """
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
        stream: str | None = None,
        cursor: int = 0,
        limit: int = 100,
        filters: Mapping[str, Any] | None = None,
    ) -> list[Event]:
        """Return events with ``event_id > cursor``, oldest first.

        ``stream`` selects a single stream; ``None`` spans ALL streams of the
        workspace (a single chronological cursor over the whole workspace log).
        """
        ...

    def max_event_id(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        stream: str | None = None,
    ) -> int:
        """Return the largest ``event_id`` in the (workspace, stream) scope.

        ``0`` when the scope holds no events. The O(1) "end of the log"
        position lookup (an indexed ``MAX``, never a scan) that backs
        ``--from latest`` startup in followers.
        """
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

    def list_by_ids(
        self, uow: UnitOfWork, *, message_ids: Sequence[str]
    ) -> list[Message]:
        """Return messages by id, GLOBAL (no ``workspace_id`` filter).

        Used to materialise a recipient's inbox (ADR 0001): the inbox is global,
        so a delivery's message may live in a different workspace than the
        recipient. Missing ids are simply absent from the result.
        """
        ...


@runtime_checkable
class MessageDeliveryRepo(Protocol):
    """Per-recipient message delivery lanes - the inbox (ADR 0001).

    Deliberately GLOBAL (not ``workspace_id``-scoped): an agent's inbox spans
    every workspace. ``status`` transitions ``unread`` -> ``delivered`` (pulled,
    in-flight under a lease) -> ``read`` (acknowledged into history), plus
    ``parked`` (dead-letter) once a delivery exhausts its claim attempts.

    Read methods (``list_by_status`` / ``counts`` / ``list_history`` /
    ``list_for_message``) MUST NOT write: the effective lane of an in-flight
    delivery whose lease elapsed is COMPUTED at read time (shown/counted as
    ``unread``), never swept by an UPDATE - polling must not become a WAL
    writer. The only physical lane transitions happen in ``claim_pending``,
    ``mark_read`` and ``extend_leases``, all scoped to one recipient.
    """

    def create(
        self,
        uow: UnitOfWork,
        *,
        delivery_id: str,
        message_id: str,
        recipient_agent_id: str,
        status: str,
        created_at: str | None = None,
    ) -> MessageDelivery:
        """Insert one ``unread`` delivery row, returning the stored row."""
        ...

    def claim_pending(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        limit: int,
        now: str,
        lease_expires_at: str,
        max_attempts: int,
    ) -> list[MessageDelivery]:
        """Atomically claim up to ``limit`` of the recipient's claimable rows.

        Claimable = ``unread`` OR ``delivered`` with an elapsed lease (the
        recipient's own redeliveries) - a SINGLE recipient-scoped statement, so
        a pull never touches other recipients' rows. Each claim increments the
        row's ``attempts``; a row that already reached ``max_attempts`` is
        moved to ``parked`` (dead-letter) instead of being redelivered.
        Returns only the rows DELIVERED by this call (``delivered_at = now``,
        leased until ``lease_expires_at``), oldest first; parked rows are
        omitted.
        """
        ...

    def mark_read(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        message_ids: Sequence[str],
        read_at: str,
    ) -> int:
        """Move the recipient's ``unread``/``delivered`` rows for these messages to
        ``read`` (history). Returns the number transitioned (idempotent)."""
        ...

    def extend_leases(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        message_ids: Sequence[str],
        now: str,
        lease_expires_at: str,
    ) -> list[str]:
        """Renew the lease of the recipient's IN-FLIGHT deliveries.

        Only rows that are ``delivered`` with a still-valid lease
        (``lease_expires_at >= now``) are extended; everything else is left
        untouched. Returns the ``message_id`` list actually extended so the
        caller can report precisely which ids were not in-flight.
        """
        ...

    def list_by_status(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        statuses: Sequence[str],
        now: str,
        limit: int,
    ) -> list[MessageDelivery]:
        """READ-ONLY list of a recipient's rows whose EFFECTIVE lane at ``now``
        is in ``statuses`` (an elapsed in-flight lease reads as ``unread``)."""
        ...

    def counts(
        self, uow: UnitOfWork, *, recipient_agent_id: str, now: str
    ) -> dict[str, int]:
        """READ-ONLY ``{lane: count}`` for the recipient's EFFECTIVE lanes at
        ``now`` (an elapsed in-flight lease counts as ``unread``)."""
        ...

    def list_history(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        before: tuple[str, str] | None = None,
        limit: int = 100,
    ) -> list[MessageDelivery]:
        """List the recipient's ``read`` lane, newest first, keyset-paginated.

        ``before`` is the exclusive ``(read_at, delivery_id)`` keyset boundary
        (the last row of the previous page); ``None`` starts at the newest.
        Keyset (not OFFSET) so rows acknowledged between pages can never shift
        already-seen items into a later page.
        """
        ...

    def list_for_messages(
        self,
        uow: UnitOfWork,
        *,
        recipient_agent_id: str,
        message_ids: Sequence[str],
    ) -> list[MessageDelivery]:
        """Return the recipient's PHYSICAL delivery rows for these messages
        (no effective-lane projection; used to explain failed transitions)."""
        ...

    def list_for_message(
        self, uow: UnitOfWork, *, message_id: str, now: str
    ) -> list[Mapping[str, Any]]:
        """READ-ONLY sender-side view of one message's deliveries.

        One mapping per recipient with ``recipient_agent_id``, the EFFECTIVE
        ``status`` at ``now``, ``attempts`` and ``read_at`` (plain mappings:
        ``attempts`` is delivery-bookkeeping, not part of the domain model).
        """
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
        payload: str | None = None,
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

    def transition_claimed(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        handoff_id: str,
        claimed_by: str,
        status: str,
        updated_at: str | None = None,
        result: str | None = None,
        rejected_reason: str | None = None,
    ) -> Handoff | None:
        """Conditionally transition a CLAIMED handoff owned by ``claimed_by``.

        Mirrors :meth:`claim`: the implementation must re-assert
        ``status='CLAIMED' AND claimed_by=?`` atomically (single statement),
        so a stale caller (lease expired, different claimant, already
        terminal) affects 0 rows instead of clobbering the row. The terminal
        outcome (``result`` on complete, ``rejected_reason`` on reject —
        already serialised TEXT) must be written in the SAME conditional
        UPDATE that changes the status, so the row and its outcome can never
        disagree. Return the updated row, or ``None`` when 0 rows were
        affected — the caller re-reads to raise the precise catalogue error.
        """
        ...

    def reject_open(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        handoff_id: str,
        updated_at: str | None = None,
        rejected_reason: str | None = None,
    ) -> Handoff | None:
        """Conditionally reject an unclaimed OPEN handoff (direct-target path).

        Same contract as :meth:`transition_claimed`: the implementation must
        re-assert ``status='OPEN'`` atomically, with the optional
        ``rejected_reason`` riding the same UPDATE; ``None`` on 0 affected
        rows.
        """
        ...

    def read_outcome(
        self, uow: UnitOfWork, *, workspace_id: str, handoff_id: str
    ) -> dict[str, str | None] | None:
        """Return ``{"result", "rejected_reason"}`` for a handoff, or ``None``.

        The outcome columns (migration 008) are read separately from the
        :class:`Handoff` dataclass so the shared domain model stays stable;
        values are the serialised TEXT persisted by
        :meth:`transition_claimed` / :meth:`reject_open`.
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
    deliveries: MessageDeliveryRepo | None = None
    tasks: TaskRepo | None = None
    handoffs: HandoffRepo | None = None
    artifacts: ArtifactRepo | None = None
    files: FileStore | None = None
