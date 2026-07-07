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
from typing import Any, Iterable, Mapping, Protocol, Sequence, runtime_checkable

from ..domain.approvals import Approval
from ..domain.comm_preset import CommPresetRecord, CommPresetVersion
from ..domain.governance import Policy
from ..domain.guardrails import (
    AgentGroupMember,
    AgentGroupRecord,
    EffectiveGuardrail,
    GuardrailAssignment,
    GuardrailRecord,
    GuardrailVersion,
)
from ..domain.policy import PolicyRecord, PolicyVersion
from ..domain.models import (
    Agent,
    Artifact,
    CapabilityName,
    Channel,
    Event,
    EphemeralPollToken,
    Handoff,
    Memory,
    Message,
    MessageDelivery,
    Session,
    TagKey,
    TagValue,
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

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool | None: ...

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
        color: str | None = None,
    ) -> Agent:
        """Insert or update the agent, returning the stored row.

        ``color`` follows COALESCE semantics on conflict (``None`` keeps the
        stored value); clearing a color to auto-by-identity is a first-class
        operation on :meth:`set_color`, never here.
        """
        ...

    def get(self, uow: UnitOfWork, agent_id: str) -> Agent | None:
        """Return the agent, or ``None`` if it does not exist."""
        ...

    def list(self, uow: UnitOfWork) -> list[Agent]:
        """Return ALL agents (global; identities are not workspace-scoped)."""
        ...

    def touch(self, uow: UnitOfWork, *, agent_id: str, at: str | None = None) -> bool:
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

    def set_active(self, uow: UnitOfWork, *, agent_id: str, is_active: bool) -> bool:
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

    def set_permissions(
        self,
        uow: UnitOfWork,
        *,
        agent_id: str,
        permissions: Mapping[str, Any] | None,
        preset_id: str | None,
    ) -> bool:
        """Overwrite the agent's permission flags + preset reference.

        Always a full overwrite of BOTH columns (``permissions=None`` resets
        to unrestricted default-allow). Returns ``True`` if the agent existed.
        """
        ...

    def set_tags(self, uow: UnitOfWork, *, agent_id: str, tags: Any) -> bool:
        """Overwrite the agent's tag map (migration 013).

        Full overwrite (``None`` resets to "no tags"); the caller has already
        validated shape AND catalog existence. Returns ``True`` if the agent
        existed.
        """
        ...

    def set_comm_scope(
        self, uow: UnitOfWork, *, agent_id: str, comm_scope: Any
    ) -> bool:
        """Overwrite the agent's communication scope (migration 013).

        Full overwrite (``None`` resets to unrestricted). The value is
        operator-set and PRIVATE (never exposed on discovery). Returns
        ``True`` if the agent existed.
        """
        ...

    def set_color(self, uow: UnitOfWork, *, agent_id: str, color: str | None) -> bool:
        """Overwrite the agent's display color (migration 024).

        Full overwrite (``None`` resets to auto-by-identity); mirrors
        :meth:`set_tags`. The value is stored verbatim (format validation is
        the caller's job). Returns ``True`` if the agent existed.
        """
        ...


@runtime_checkable
class TagCatalogRepo(Protocol):
    """Persistence for the central tag catalog (migration 013).

    The single registry behind the fail-closed tag-scoping rule: keys and
    values must exist here before anything may reference them. Existence
    checks and the ``TAG_IN_USE`` deletion guard live in
    :mod:`okto_nexus.application.tags`.
    """

    def create_key(
        self, uow: UnitOfWork, *, key: str, description: str | None = None
    ) -> TagKey:
        """Register a key (unique). ``VALIDATION_ERROR`` on a duplicate."""
        ...

    def get_key(self, uow: UnitOfWork, key: str) -> TagKey | None:
        """Return the key, or ``None`` if it is not registered."""
        ...

    def list_keys(self, uow: UnitOfWork) -> list[TagKey]:
        """Return every registered key, sorted by key."""
        ...

    def delete_key(self, uow: UnitOfWork, *, key: str) -> bool:
        """Delete a key (values cascade). True if it existed.

        Callers MUST run the in-use guard first (application layer).
        """
        ...

    def create_value(
        self,
        uow: UnitOfWork,
        *,
        key: str,
        value: str,
        description: str | None = None,
    ) -> TagValue:
        """Register a value under a registered key.

        ``NOT_FOUND`` when the key is unregistered; ``VALIDATION_ERROR`` on a
        duplicate value.
        """
        ...

    def get_value(self, uow: UnitOfWork, *, key: str, value: str) -> TagValue | None:
        """Return the value, or ``None`` if it is not registered."""
        ...

    def list_values(self, uow: UnitOfWork, *, key: str | None = None) -> list[TagValue]:
        """Values (optionally of one key), sorted by ``(key, value)``."""
        ...

    def delete_value(self, uow: UnitOfWork, *, key: str, value: str) -> bool:
        """Delete one value. True if it existed (in-use guard is upstream)."""
        ...


@runtime_checkable
class CapabilityCatalogRepo(Protocol):
    """Persistence for the central capability catalog (migration 014).

    The single registry behind the fail-closed capability rule: a name must
    exist here before anything may reference it (agent ``capabilities``,
    ``strategy: "capability"`` targets). Existence checks and the
    ``CAPABILITY_IN_USE`` deletion guard live in
    :mod:`okto_nexus.application.capabilities`.
    """

    def create(
        self, uow: UnitOfWork, *, name: str, description: str | None = None
    ) -> CapabilityName:
        """Register a name (unique). ``VALIDATION_ERROR`` on a duplicate."""
        ...

    def ensure(self, uow: UnitOfWork, *, name: str) -> bool:
        """Insert-or-ignore a name (seed path). True if inserted now."""
        ...

    def get(self, uow: UnitOfWork, name: str) -> CapabilityName | None:
        """Return the name, or ``None`` if it is not registered."""
        ...

    def list(self, uow: UnitOfWork) -> list[CapabilityName]:
        """Return every registered name, sorted by name."""
        ...

    def delete(self, uow: UnitOfWork, *, name: str) -> bool:
        """Delete one name. True if it existed (in-use guard is upstream)."""
        ...


@runtime_checkable
class GovernanceRepo(Protocol):
    """Persistence + consumption counters for governance policies (migration 016).

    V1 policy engine (spec ffef15bf): GLOBAL deny-only policies (subject x
    action x limit). Form validation lives in
    :func:`okto_nexus.domain.governance.validate_policy_form`; matching and the
    deny-overrides verdict in the same domain module; the enforcement
    orchestration in :mod:`okto_nexus.application.governance`. The counters are
    pre-fetched INSIDE the write path's unit of work (on-demand windows - never
    a counter table).
    """

    def create(
        self,
        uow: UnitOfWork,
        *,
        policy_id: str,
        subject_kind: str,
        subject_value: str | None,
        action: str,
        limit_kind: str,
        limit_value: int | None,
        window: str | None,
        enabled: bool = True,
        created_at: str | None = None,
    ) -> Policy:
        """Insert one policy row; returns the stored :class:`Policy`."""
        ...

    def get(self, uow: UnitOfWork, policy_id: str) -> Policy | None:
        """Return the policy, or ``None`` when absent."""
        ...

    def list(self, uow: UnitOfWork) -> list[Policy]:
        """Every policy (enabled and disabled), ``(created_at, policy_id)`` order."""
        ...

    def list_active(self, uow: UnitOfWork) -> list[Policy]:
        """Enabled policies only, same deterministic order (enforcement read)."""
        ...

    def update(
        self, uow: UnitOfWork, *, policy_id: str, fields: Mapping[str, Any]
    ) -> Policy | None:
        """Patch validated ``fields``; returns the updated row or ``None``."""
        ...

    def delete(self, uow: UnitOfWork, *, policy_id: str) -> bool:
        """Remove the policy. ``True`` if it existed."""
        ...

    def actions_since(
        self, uow: UnitOfWork, *, agent_id: str, action: str, since: str
    ) -> int:
        """COUNT of the caller's persisted ``action`` rows at/after ``since``."""
        ...

    def open_handoffs(self, uow: UnitOfWork, *, agent_id: str) -> int:
        """COUNT of the caller's handoffs in a non-terminal status (global)."""
        ...


@runtime_checkable
class PolicyRepo(Protocol):
    """Persistence for NAMED global policies + their append-only versions
    (migration 022, spec 80624c1a).

    A policy row is metadata (``name`` + ``description``); its audience +
    governance live in immutable :class:`PolicyVersion` rows keyed by
    ``(policy_id, version)``. Publishing an edit APPENDS a new version (the
    repo assigns the next number atomically); versions are never mutated.
    Global (no ``workspace_id``), matching the governance/tag/capability
    catalogs. Form validation is upstream
    (:mod:`okto_nexus.domain.policy`); this port persists.
    """

    def create(
        self,
        uow: UnitOfWork,
        *,
        policy_id: str,
        name: str,
        description: str | None = None,
        created_at: str | None = None,
    ) -> PolicyRecord:
        """Insert one catalog row (UNIQUE ``name``); returns the stored record."""
        ...

    def get(self, uow: UnitOfWork, policy_id: str) -> PolicyRecord | None:
        """Return the policy record (with ``latest_version``), or ``None``."""
        ...

    def get_by_name(self, uow: UnitOfWork, name: str) -> PolicyRecord | None:
        """Return the policy record by its unique ``name``, or ``None``."""
        ...

    def list(self, uow: UnitOfWork) -> list[PolicyRecord]:
        """Every policy, ``(created_at, policy_id)`` order, with latest version."""
        ...

    def update(
        self,
        uow: UnitOfWork,
        *,
        policy_id: str,
        name: str | None = None,
        description: Any = "__unset__",
    ) -> PolicyRecord | None:
        """Patch the METADATA (name/description); ``None`` when absent.

        Versions are append-only and never touched here. ``description`` uses
        the ``"__unset__"`` sentinel so ``None`` can explicitly clear it.
        """
        ...

    def delete(self, uow: UnitOfWork, *, policy_id: str) -> bool:
        """Remove the policy (versions cascade). ``True`` if it existed.

        Callers MUST run the ``POLICY_IN_USE`` guard first (application layer):
        a binding still referencing the policy blocks deletion.
        """
        ...

    def add_version(
        self,
        uow: UnitOfWork,
        *,
        policy_id: str,
        audience: Mapping[str, Any] | None,
        governance: Sequence[Mapping[str, Any]],
        published_at: str | None = None,
    ) -> PolicyVersion:
        """Append the next immutable version; returns the stored version.

        The version number is ``MAX(version)+1`` computed inside ``uow`` (the
        write lock serialises it). ``audience``/``governance`` are the already
        validated bodies; the adapter serialises them to JSON TEXT.
        """
        ...

    def get_version(
        self, uow: UnitOfWork, *, policy_id: str, version: int
    ) -> PolicyVersion | None:
        """Return one exact version (the ``pinned`` read), or ``None``."""
        ...

    def latest_version(
        self, uow: UnitOfWork, *, policy_id: str
    ) -> PolicyVersion | None:
        """Return the highest-numbered version (the ``latest`` read), or ``None``."""
        ...

    def list_versions(self, uow: UnitOfWork, *, policy_id: str) -> list[PolicyVersion]:
        """Every version of a policy, ascending ``version`` (history surface)."""
        ...

    def versions_for(
        self, uow: UnitOfWork, *, policy_ids: Sequence[str]
    ) -> dict[str, list[PolicyVersion]]:
        """Bulk-fetch versions for a set of policies (the resolution read).

        Returns ``{policy_id: [versions ascending]}`` for the ids that have
        any version; a missing id simply has no key. Feeds
        :func:`okto_nexus.domain.policy.resolve_effective_sources` as
        ``versions_by_policy``.
        """
        ...


@runtime_checkable
class AgentPolicyBindingRepo(Protocol):
    """Persistence for an agent's ordered policy bindings (migration 022).

    Bindings live in their OWN table (not a JSON column on ``agents``) so the
    ``POLICY_IN_USE`` guard is a single indexed lookup. :meth:`replace` is a
    full overwrite (mirroring ``AgentRepo.set_comm_scope``); the stored dicts
    are the already-validated output of
    :func:`okto_nexus.domain.policy.validate_agent_bindings`.
    """

    def replace(
        self, uow: UnitOfWork, *, agent_id: str, bindings: Sequence[Mapping[str, Any]]
    ) -> None:
        """Overwrite ALL of an agent's bindings, preserving list order.

        Deletes the agent's existing binding rows and inserts the new ones at
        ascending positions in ONE unit of work. An empty sequence clears the
        bindings (back to unrestricted).
        """
        ...

    def list_for_agent(self, uow: UnitOfWork, *, agent_id: str) -> list[dict[str, Any]]:
        """Return the agent's bindings as validated dicts, in position order."""
        ...

    def agents_binding_policy(self, uow: UnitOfWork, *, policy_id: str) -> list[str]:
        """Distinct agent ids with a GLOBAL binding to ``policy_id`` (in-use guard).

        Empty list means the policy is unreferenced and safe to delete.
        """
        ...


@runtime_checkable
class AgentGroupRepo(Protocol):
    """Persistence for explicit agent groups used by guardrail assignments.

    Groups are rosters of concrete agent ids, not tags and not routing targets.
    """

    def create(
        self,
        uow: UnitOfWork,
        *,
        group_id: str,
        name: str,
        description: str | None = None,
        created_at: str | None = None,
    ) -> AgentGroupRecord:
        """Insert a group catalog row; returns the stored record."""
        ...

    def get(self, uow: UnitOfWork, group_id: str) -> AgentGroupRecord | None:
        """Return the group record, or ``None``."""
        ...

    def get_by_name(self, uow: UnitOfWork, name: str) -> AgentGroupRecord | None:
        """Return the group by unique name, or ``None``."""
        ...

    def list(self, uow: UnitOfWork) -> list[AgentGroupRecord]:
        """Every group in deterministic order."""
        ...

    def update(
        self,
        uow: UnitOfWork,
        *,
        group_id: str,
        name: str | None = None,
        description: Any = "__unset__",
    ) -> AgentGroupRecord | None:
        """Patch group metadata; ``None`` when absent."""
        ...

    def delete(self, uow: UnitOfWork, *, group_id: str) -> bool:
        """Delete a group. Callers must guard active assignments first."""
        ...

    def add_member(
        self,
        uow: UnitOfWork,
        *,
        group_id: str,
        agent_id: str,
        created_at: str | None = None,
    ) -> AgentGroupMember:
        """Add an agent to the roster idempotently."""
        ...

    def get_member(
        self, uow: UnitOfWork, *, group_id: str, agent_id: str
    ) -> AgentGroupMember | None:
        """Return one membership row, or ``None``."""
        ...

    def remove_member(self, uow: UnitOfWork, *, group_id: str, agent_id: str) -> bool:
        """Remove one membership row."""
        ...

    def list_members(self, uow: UnitOfWork, *, group_id: str) -> list[AgentGroupMember]:
        """Return group members ordered by agent id."""
        ...

    def groups_for_agent(self, uow: UnitOfWork, *, agent_id: str) -> list[str]:
        """Return group ids containing ``agent_id``."""
        ...


@runtime_checkable
class GuardrailRepo(Protocol):
    """Persistence for named guardrails and version lifecycle rows."""

    def create(
        self,
        uow: UnitOfWork,
        *,
        guardrail_id: str,
        name: str,
        description: str | None = None,
        created_at: str | None = None,
    ) -> GuardrailRecord:
        """Insert a guardrail catalog row; returns the stored record."""
        ...

    def get(self, uow: UnitOfWork, guardrail_id: str) -> GuardrailRecord | None:
        """Return the guardrail record, or ``None``."""
        ...

    def get_by_name(self, uow: UnitOfWork, name: str) -> GuardrailRecord | None:
        """Return the guardrail by unique name, or ``None``."""
        ...

    def list(self, uow: UnitOfWork) -> list[GuardrailRecord]:
        """Every guardrail in deterministic order."""
        ...

    def update(
        self,
        uow: UnitOfWork,
        *,
        guardrail_id: str,
        name: str | None = None,
        description: Any = "__unset__",
    ) -> GuardrailRecord | None:
        """Patch guardrail metadata."""
        ...

    def delete(self, uow: UnitOfWork, *, guardrail_id: str) -> bool:
        """Delete a guardrail. Callers must guard active assignments first."""
        ...

    def add_version(
        self,
        uow: UnitOfWork,
        *,
        guardrail_id: str,
        status: str,
        evaluator_kind: str,
        evaluator_config: Mapping[str, Any],
        surfaces: Sequence[str],
        field_targets: Sequence[str],
        created_at: str | None = None,
        activated_at: str | None = None,
    ) -> GuardrailVersion:
        """Append the next version; returns the stored version."""
        ...

    def get_version(
        self, uow: UnitOfWork, *, guardrail_id: str, version: int
    ) -> GuardrailVersion | None:
        """Return an exact guardrail version, or ``None``."""
        ...

    def latest_active_version(
        self, uow: UnitOfWork, *, guardrail_id: str
    ) -> GuardrailVersion | None:
        """Return max active version, or ``None``."""
        ...

    def list_versions(
        self, uow: UnitOfWork, *, guardrail_id: str
    ) -> list[GuardrailVersion]:
        """Return every version for one guardrail."""
        ...

    def versions_for(
        self, uow: UnitOfWork, *, guardrail_ids: Sequence[str]
    ) -> dict[str, list[GuardrailVersion]]:
        """Bulk-fetch versions for effective assignment resolution."""
        ...

    def update_version_status(
        self,
        uow: UnitOfWork,
        *,
        guardrail_id: str,
        version: int,
        status: str,
    ) -> GuardrailVersion | None:
        """Patch only version lifecycle status."""
        ...


@runtime_checkable
class GuardrailAssignmentRepo(Protocol):
    """Persistence for global/group guardrail assignments."""

    def create(
        self,
        uow: UnitOfWork,
        *,
        assignment_id: str,
        scope_kind: str,
        group_id: str | None,
        guardrail_id: str,
        version_mode: str = "latest",
        pinned_version: int | None = None,
        mode: str = "enforce",
        priority: int = 100,
        enabled: bool = True,
        created_at: str | None = None,
    ) -> GuardrailAssignment:
        """Insert one assignment after validating pinned active versions."""
        ...

    def get(
        self, uow: UnitOfWork, assignment_id: str
    ) -> GuardrailAssignment | None:
        """Return an assignment, or ``None``."""
        ...

    def list(self, uow: UnitOfWork) -> list[GuardrailAssignment]:
        """Return every assignment."""
        ...

    def list_for_group(
        self, uow: UnitOfWork, *, group_id: str
    ) -> list[GuardrailAssignment]:
        """Return assignments referencing a group."""
        ...

    def list_for_guardrail(
        self, uow: UnitOfWork, *, guardrail_id: str
    ) -> list[GuardrailAssignment]:
        """Return assignments referencing a guardrail."""
        ...

    def list_for_agent(
        self, uow: UnitOfWork, *, agent_id: str
    ) -> list[GuardrailAssignment]:
        """Return global plus group assignments applicable to an agent."""
        ...

    def effective_for_agent(
        self, uow: UnitOfWork, *, agent_id: str
    ) -> list[EffectiveGuardrail]:
        """Resolve applicable assignments to active runtime versions."""
        ...

    def update(
        self,
        uow: UnitOfWork,
        *,
        assignment_id: str,
        mode: str | None = None,
        priority: int | None = None,
        enabled: bool | None = None,
    ) -> GuardrailAssignment | None:
        """Patch mutable assignment controls."""
        ...

    def delete(self, uow: UnitOfWork, *, assignment_id: str) -> bool:
        """Delete one assignment."""
        ...


@runtime_checkable
class CommPresetRepo(Protocol):
    """Persistence for NAMED global communication presets + their append-only
    versions (migration 023, spec 6f961722).

    A preset row is metadata (``name`` + ``description``); its style ``content``
    lives in immutable :class:`CommPresetVersion` rows keyed by
    ``(preset_id, version)``. Publishing an edit APPENDS a new version (the repo
    assigns the next number atomically); versions are never mutated. Global (no
    ``workspace_id``), like the policy/governance/tag/capability catalogs. Form
    validation is upstream (:mod:`okto_nexus.domain.comm_preset`); this port
    persists. Structurally the content-only twin of :class:`PolicyRepo`.
    """

    def create(
        self,
        uow: UnitOfWork,
        *,
        preset_id: str,
        name: str,
        description: str | None = None,
        created_at: str | None = None,
    ) -> CommPresetRecord:
        """Insert one catalog row (UNIQUE ``name``); returns the stored record."""
        ...

    def get(self, uow: UnitOfWork, preset_id: str) -> CommPresetRecord | None:
        """Return the preset record (with ``latest_version``), or ``None``."""
        ...

    def get_by_name(self, uow: UnitOfWork, name: str) -> CommPresetRecord | None:
        """Return the preset record by its unique ``name``, or ``None``."""
        ...

    def list(self, uow: UnitOfWork) -> list[CommPresetRecord]:
        """Every preset, ``(created_at, preset_id)`` order, with latest version."""
        ...

    def update(
        self,
        uow: UnitOfWork,
        *,
        preset_id: str,
        name: str | None = None,
        description: Any = "__unset__",
    ) -> CommPresetRecord | None:
        """Patch the METADATA (name/description); ``None`` when absent.

        Versions are append-only and never touched here. ``description`` uses
        the ``"__unset__"`` sentinel so ``None`` can explicitly clear it.
        """
        ...

    def delete(self, uow: UnitOfWork, *, preset_id: str) -> bool:
        """Remove the preset (versions cascade). ``True`` if it existed.

        Callers MUST run the ``COMM_PRESET_IN_USE`` guard first (application
        layer): a binding still referencing the preset blocks deletion.
        """
        ...

    def add_version(
        self,
        uow: UnitOfWork,
        *,
        preset_id: str,
        content: Mapping[str, Any],
        published_at: str | None = None,
    ) -> CommPresetVersion:
        """Append the next immutable version; returns the stored version.

        The version number is ``MAX(version)+1`` computed inside ``uow`` (the
        write lock serialises it). ``content`` is the already-validated body;
        the adapter serialises it to JSON TEXT.
        """
        ...

    def get_version(
        self, uow: UnitOfWork, *, preset_id: str, version: int
    ) -> CommPresetVersion | None:
        """Return one exact version (the ``pinned`` read), or ``None``."""
        ...

    def latest_version(
        self, uow: UnitOfWork, *, preset_id: str
    ) -> CommPresetVersion | None:
        """Return the highest-numbered version (the ``latest`` read), or ``None``."""
        ...

    def list_versions(
        self, uow: UnitOfWork, *, preset_id: str
    ) -> list[CommPresetVersion]:
        """Every version of a preset, ascending ``version`` (history surface)."""
        ...


@runtime_checkable
class AgentCommBindingRepo(Protocol):
    """Persistence for an agent's SINGLE communication binding (migration 023).

    Unlike :class:`AgentPolicyBindingRepo` (ordered, N-per-agent, composed), a
    communication binding is SINGLE-SOURCE: the ``agent_comm_binding`` table is
    keyed by ``agent_id`` alone, so :meth:`set` is an upsert of AT MOST one row
    and the ``COMM_PRESET_IN_USE`` guard is one indexed lookup. The stored dict
    is the already-validated output of
    :func:`okto_nexus.domain.comm_preset.compose_comm_binding`.
    """

    def set(
        self, uow: UnitOfWork, *, agent_id: str, binding: Mapping[str, Any] | None
    ) -> None:
        """Upsert (or, with ``binding=None``, CLEAR) the agent's single binding.

        A full overwrite of the one row: ``None`` deletes it (back to no preset
        = today's whoami), otherwise it replaces whatever was there.
        """
        ...

    def get(self, uow: UnitOfWork, *, agent_id: str) -> dict[str, Any] | None:
        """Return the agent's binding as a validated dict, or ``None`` if unset."""
        ...

    def agents_binding_preset(self, uow: UnitOfWork, *, preset_id: str) -> list[str]:
        """Distinct agent ids with a GLOBAL binding to ``preset_id`` (in-use guard).

        Empty list means the preset is unreferenced and safe to delete.
        """
        ...


@runtime_checkable
class ApprovalRepo(Protocol):
    """Persistence for HITL approvals (migration 017, spec 2948b2a2).

    Rows are append-then-decide, never deleted (BR1): ``add`` runs inside the
    intercepting write path's OWN unit of work so the pending row and the
    ``approval.requested`` event commit atomically with the returned envelope.
    ``mark_decided`` is the CONDITIONAL flip (anti double-decision - AC6) and
    ``revert_to_pending`` is the honest rollback when re-execution fails a
    gate (BR3). Payload columns are JSON TEXT; (de)serialisation is upstream.
    """

    def add(
        self,
        uow: UnitOfWork,
        *,
        approval_id: str,
        workspace_id: str,
        agent_id: str,
        action: str,
        policy_id: str,
        request_payload: str,
        trace_id: str | None,
        created_at: str,
    ) -> Approval:
        """Insert one PENDING row; returns the stored :class:`Approval`."""
        ...

    def get(self, uow: UnitOfWork, approval_id: str) -> Approval | None:
        """Return the approval, or ``None`` when absent."""
        ...

    def list(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Approval]:
        """Workspace-scoped rows, ASCENDING ``created_at`` (oldest first).

        ``status=None`` means every status; the queue default (``pending``)
        is decided upstream.
        """
        ...

    def mark_decided(
        self,
        uow: UnitOfWork,
        *,
        approval_id: str,
        status: str,
        decided_by: str,
        justification: str | None,
        decided_at: str,
    ) -> bool:
        """Conditionally flip ``pending`` -> ``status``.

        Returns ``False`` when the row was NOT pending (already decided) so
        the service can raise ``CONFLICT`` - the second decision never
        overwrites the first (AC6).
        """
        ...

    def set_executed_result(
        self, uow: UnitOfWork, *, approval_id: str, executed_result: str
    ) -> None:
        """Record the re-execution's result JSON on an approved row."""
        ...

    def revert_to_pending(self, uow: UnitOfWork, *, approval_id: str) -> None:
        """Honest rollback (BR3): ``approved`` -> ``pending``, clearing the
        decision columns, after the re-execution failed a gate."""
        ...


@runtime_checkable
class PresetRepo(Protocol):
    """Persistence for CUSTOM permission presets (migration 011).

    Built-in presets live in :mod:`okto_nexus.domain.permissions` as code and
    never reach this table.
    """

    def create(
        self,
        uow: UnitOfWork,
        *,
        preset_id: str,
        name: str,
        flags: Mapping[str, Any],
        description: str | None = None,
    ) -> Any:
        """Create a preset (UNIQUE name). Returns the stored row."""
        ...

    def get(self, uow: UnitOfWork, preset_id: str) -> Any:
        """Return the preset, or ``None``."""
        ...

    def list(self, uow: UnitOfWork) -> list[Any]:
        """Return every custom preset, ordered by name."""
        ...

    def update(
        self,
        uow: UnitOfWork,
        *,
        preset_id: str,
        name: str | None = None,
        description: Any = "__unset__",
        flags: Mapping[str, Any] | None = None,
    ) -> Any:
        """Patch the preset; returns the updated row or ``None`` if absent."""
        ...

    def delete(self, uow: UnitOfWork, *, preset_id: str) -> bool:
        """Remove the preset. Returns ``True`` if it existed."""
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
    ) -> list[dict[str, Any]]: ...

    def handoff_dependency_aggregates(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None,
        handoff_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Per-handoff dependency aggregates for a page of ids (I5).

        ONE ``IN`` query per page (never per row): returns
        ``{handoff_id: {"depends_on": [ids], "total", "satisfied",
        "pending", "failed"}}`` with ONLY ids that have dependency rows -
        a missing key means "no dependencies" and the row keeps its exact
        pre-I5 shape.
        """
        ...

    def last_actions_by_agent(
        self, uow: UnitOfWork, *, workspace_id: str | None
    ) -> dict[str, dict[str, Any]]:
        """Each agent's most-recent event as ``{agent_id: {"type", "at"}}``.

        The action is the ``type`` and ``created_at`` of the highest-``event_id``
        row per ``actor_agent_id`` - the real coordination verb from the log,
        not a derived liveness signal. Scoped to ``workspace_id`` when given
        (``None`` = the "All workspaces" view). ONE GROUP-BY for the whole
        graph (never per-agent - the same anti-N+1 rule as the handoff
        aggregates). Agents with no events in scope are ABSENT from the map,
        so a node with no recent activity keeps a ``None`` last_action.
        """
        ...

    def inbox_depth_by_agent(
        self, uow: UnitOfWork, *, workspace_id: str | None
    ) -> dict[str, int]:
        """Per-agent pending-inbox depth as ``{agent_id: count}`` (migration 024).

        Counts the PHYSICAL not-yet-read lanes (``unread`` + ``delivered``) per
        recipient in ONE GROUP-BY (anti-N+1). Scoped to ``workspace_id`` when
        given (``None`` = all workspaces). Agents with none are ABSENT, so the
        node reads 0.
        """
        ...

    def open_handoffs_by_agent(
        self, uow: UnitOfWork, *, workspace_id: str | None
    ) -> dict[str, int]:
        """Per-agent open-handoff involvement as ``{agent_id: count}``.

        Counts NON-TERMINAL handoffs (OPEN/CLAIMED/VERIFYING) attributed to
        BOTH the origin (``from_agent_id``) and the holder (``claimed_by``) via
        a UNION ALL, in ONE pass (anti-N+1). Scoped to ``workspace_id`` when
        given (``None`` = all workspaces). Agents with none are ABSENT (node
        reads 0).
        """
        ...

    def channel_rows(
        self, uow: UnitOfWork, *, workspace_id: str | None
    ) -> list[dict[str, Any]]: ...

    def session_rows(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str | None,
        status: str | None = None,
    ) -> list[dict[str, Any]]: ...

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
        peer_id: str | None = None,
        undelivered_only: bool = False,
        include_body: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        """Paginated message history with per-recipient deliveries; (items, total).

        ``peer_id`` (with ``agent_id``) narrows to the CONVERSATION between the
        pair, in both directions. ``undelivered_only`` selects the agent's
        sends that fanned out to nobody (the dashboard's failed tab).
        ``include_body`` adds the FULL ``body`` to each item (the default
        keeps the bounded ``preview`` only).
        """
        ...

    def conversation_peers(self, uow: UnitOfWork, *, agent_id: str) -> dict[str, Any]:
        """Aggregate the agent's conversation partners in SQL.

        Returns ``{items: [{peer, count, last_at}], failed_count}`` sorted by
        most recent activity - the scalable backing of the chat's peer picker
        (never materialises message rows).
        """
        ...

    def events_after(
        self,
        uow: UnitOfWork,
        *,
        cursor: int,
        workspace_id: str | None,
        stream: str | None,
        limit: int,
        type_: str | None = None,
        actor_agent_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Event-log rows with ``event_id > cursor``, ascending (SSE/tail feed).

        ``type_`` / ``actor_agent_id`` are optional column equality filters;
        ``trace_id`` filters on the payload-level trace key (I1).
        """
        ...

    def workspace_message_count(
        self, uow: UnitOfWork, *, workspace_id: str, since_iso: str
    ) -> int:
        """COUNT of a workspace's messages created at/after ``since_iso``.

        The TRUE total over the analytics window (workspace-scoped), used to
        detect truncation against the bounded row fetch below.
        """
        ...

    def workspace_message_rows(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        since_iso: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """The window's ``(message_id, from_agent_id, body, created_at)`` rows.

        Workspace-scoped, created at/after ``since_iso``, NEWEST first, capped at
        ``limit`` (the analytics bounded fetch - FR9). Token counting and all
        aggregation happen in Python over these rows (``length()`` != tokens, so
        tokenisation can never be pushed into SQL).
        """
        ...

    def workspace_event_stats(
        self, uow: UnitOfWork, *, workspace_id: str, since_iso: str
    ) -> dict[str, Any]:
        """``{count, last_event_at}`` for a workspace's event log.

        ``count`` is the number of events created at/after ``since_iso`` (the
        rollup window); ``last_event_at`` is the OVERALL most recent event in
        the workspace (``None`` when it has none), regardless of the window.
        """
        ...

    def workspace_delivery_health(
        self, uow: UnitOfWork, *, workspace_id: str
    ) -> dict[str, int]:
        """``{unread, parked}`` delivery counts for messages in this workspace.

        Deliveries are global (ADR 0001), so this JOINs ``message_deliveries``
        to ``messages`` on ``workspace_id``. Counts use the PHYSICAL lane (the
        same basis as ``inbox_counts``); the effective-lane projection is a
        per-recipient read concern, not a workspace rollup.
        """
        ...

    def handoff_lifecycle_events(
        self, uow: UnitOfWork, *, workspace_id: str, since_iso: str
    ) -> tuple[list[tuple[str, str, str]], bool]:
        """Windowed handoff lifecycle events for the health correlation (I7).

        ``(handoff_id, type, created_at)`` tuples - created/claimed/completed/
        rejected only, workspace-scoped, created at/after ``since_iso``, in
        append order, BOUNDED; the second element flags truncation. The
        adapter parses ``handoff_id`` out of the JSON payload (handoff rows
        keep no per-transition timestamps, so events are the only faithful
        claim->complete record - dec_e7bd8ac7).
        """
        ...

    def workspace_unread_by_agent(
        self, uow: UnitOfWork, *, workspace_id: str
    ) -> list[dict[str, Any]]:
        """``[{agent_id, unread}]`` per-recipient unread counts, this workspace.

        Snapshot (not windowed): the same deliveries-to-messages JOIN basis as
        ``workspace_delivery_health``, grouped by recipient, ordered by count
        DESC (agent_id ASC on ties).
        """
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

    def set_active(self, uow: UnitOfWork, *, agent_id: str, is_active: bool) -> bool:
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
# Ephemeral poll tokens (remote monitor data plane)
# --------------------------------------------------------------------------- #
@runtime_checkable
class PollTokenRepo(Protocol):
    """Persistence for short-lived read-only monitor bearer tokens."""

    def issue(
        self,
        uow: UnitOfWork,
        *,
        token_id: str,
        token_hash: str,
        agent_id: str,
        workspace_id: str,
        session_id: str,
        issue_cursor: int,
        scope: Mapping[str, Any],
        expires_at: str,
        created_at: str,
    ) -> EphemeralPollToken:
        """Revoke the active token for ``(agent, workspace)`` and insert one."""
        ...

    def get_active_for_session(
        self, uow: UnitOfWork, *, session_id: str
    ) -> EphemeralPollToken | None:
        """Return the non-revoked token bound to ``session_id``, if any."""
        ...

    def get_by_hash(
        self, uow: UnitOfWork, *, token_hash: str
    ) -> EphemeralPollToken | None:
        """Return the token row with ``token_hash`` regardless of expiry."""
        ...

    def rotate(
        self,
        uow: UnitOfWork,
        *,
        token_id: str,
        token_hash: str,
        expires_at: str,
        renewed_at: str,
    ) -> EphemeralPollToken:
        """Rotate the raw bearer for one active token row."""
        ...

    def revoke_for_session(
        self, uow: UnitOfWork, *, session_id: str, revoked_at: str
    ) -> int:
        """Revoke every active token for ``session_id``; return rows changed."""
        ...

    def touch_used(
        self, uow: UnitOfWork, *, token_id: str, at: str
    ) -> bool:
        """Best-effort weak-observer heartbeat for a data-plane request."""
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
        trace_id: str | None = None,
        created_at: str | None = None,
    ) -> Message:
        """Create a message, returning the stored row."""
        ...

    def get(
        self, uow: UnitOfWork, *, workspace_id: str, message_id: str
    ) -> Message | None:
        """Return the message, or ``None``."""
        ...

    def count_since(self, uow: UnitOfWork, *, from_agent_id: str, since: str) -> int:
        """Count messages SENT by ``from_agent_id`` at/after ``since`` (global).

        Backs the ``limits.messages_per_minute`` permission: the rate window
        is global (not per-workspace) because the limit protects the bus as a
        whole from a runaway sender.
        """
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
    ) -> list[str]:
        """Move the recipient's ``unread``/``delivered`` rows for these messages to
        ``read`` (history). Returns the message_ids actually transitioned
        (idempotent; already-read/unknown ids are simply absent) - the list
        backs the ``message.read`` receipt events."""
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
# Semantic search: embedding provider + message vector store (external services
# behind hexagonal ports - the domain NEVER imports sentence-transformers /
# torch / sqlite; it only ever sees these Protocols). Decisions D-EMB-1/3.
# --------------------------------------------------------------------------- #
@runtime_checkable
class EmbeddingProvider(Protocol):
    """Turns message text into a fixed-dimension embedding vector.

    The EXTERNAL embedding service, fronted so the application never depends on
    a concrete model. Two adapters implement it: a zero-dependency STUB
    (deterministic SHA256 -> floats, used in CI / when the optional extra is
    absent) and a sentence-transformers model (``all-MiniLM-L6-v2``, 384 dims)
    under the ``okto-nexus[embeddings]`` extra. Both return a vector of exactly
    :attr:`dim` floats; the same input always maps to the same vector for a
    given provider.
    """

    @property
    def dim(self) -> int:
        """Fixed dimensionality of every vector this provider emits (e.g. 384)."""
        ...

    @property
    def model(self) -> str:
        """Opaque model identifier stored alongside each vector (provenance)."""
        ...

    def encode(self, text: str) -> list[float]:
        """Embed one text into a ``dim``-length vector of floats."""
        ...

    def encode_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed many texts at once (same order); each row has ``dim`` floats."""
        ...


@runtime_checkable
class Tokenizer(Protocol):
    """Counts LLM tokens for a piece of text (workspace-analytics, FR6).

    The "size" of a message in the analytics view is measured in TOKENS, not
    bytes - tokens estimate the coordination weight a message imposes on an LLM
    far better than its byte length (owner decision, 2026-06-19). Tokenisation
    cannot be pushed into SQL (``length()`` counts characters, not tokens), so
    it lives behind this port and runs in Python at READ time over a bounded
    window; the message write path is never touched.

    The concrete adapter (``adapters/outbound/tokenizer``) wraps tiktoken's
    ``o200k_base`` encoding (the GPT-4o family) loaded fully OFFLINE from a
    vendored BPE blob, and is shipped only under the ``serve`` extra - the
    stdio core never imports it (rule br_7000ed45 / dependency-light invariant).
    A ``None`` / empty body counts as 0 tokens.
    """

    @property
    def encoding(self) -> str:
        """Opaque encoding identifier (e.g. ``o200k_base``) for provenance."""
        ...

    def count(self, text: str | None) -> int:
        """Return the number of tokens in ``text`` (``None``/empty -> 0)."""
        ...

    def count_for_message(self, message_id: str, body: str | None) -> int:
        """Token count for a message's body, memoised by ``message_id``.

        Messages are immutable, so the count is cached process-wide keyed by
        ``message_id`` - re-aggregating overlapping windows never re-tokenises
        the same body. Equivalent to :meth:`count` on the first call for an id.
        """
        ...


@runtime_checkable
class MessageVectorStore(Protocol):
    """Persistence + cosine retrieval for per-message embedding vectors.

    The vector-store seam (D-EMB-3: a SQLite ``message_embeddings`` table with a
    BLOB vector + brute-force cosine today; swappable for ``sqlite-vec`` / an
    external vector DB later without touching the domain). The embedding's
    lifecycle is coupled to the message via ``ON DELETE CASCADE`` (D-EMB-5), so
    this port exposes no bulk-prune method: deleting the message row drops its
    vector automatically.
    """

    def upsert(
        self,
        uow: UnitOfWork,
        *,
        message_id: str,
        vector: Sequence[float],
        model: str,
        dim: int,
        created_at: str | None = None,
    ) -> None:
        """Insert/replace the vector for ``message_id`` (serialised as a BLOB)."""
        ...

    def search(
        self, uow: UnitOfWork, *, query_vector: Sequence[float], k: int
    ) -> list[tuple[str, float]]:
        """Return up to ``k`` ``(message_id, cosine_score)`` pairs, best first.

        Vectors whose stored ``dim`` differs from the query's are SKIPPED (a
        provider change leaves incompatible rows that must not corrupt the
        ranking), never raised on.
        """
        ...

    def delete(self, uow: UnitOfWork, *, message_id: str) -> int:
        """Delete the vector for ``message_id``; return rows removed (0 or 1)."""
        ...


@runtime_checkable
class MemoryRepo(Protocol):
    """Persistence for :class:`Memory` rows (spec 8928b320, I6).

    Append-only for agents: there is no update method by design - correction
    happens via :meth:`mark_superseded` (stamped in the same unit of work as
    the superseding row's :meth:`create`). :meth:`delete` exists solely for
    the operator's REST curation path (BR9).
    """

    def create(
        self,
        uow: UnitOfWork,
        *,
        memory_id: str,
        workspace_id: str,
        author_agent_id: str,
        title: str,
        content: str,
        topics: Sequence[str] = (),
        source_kind: str | None = None,
        source_id: str | None = None,
        supersedes: str | None = None,
        trace_id: str | None = None,
        created_at: str | None = None,
    ) -> Memory:
        """Insert a memory row (born live: ``superseded_by`` NULL)."""
        ...

    def get(
        self, uow: UnitOfWork, *, workspace_id: str, memory_id: str
    ) -> Memory | None:
        """Return the memory (superseded or not), or ``None``."""
        ...

    def get_many(
        self, uow: UnitOfWork, *, workspace_id: str, memory_ids: Sequence[str]
    ) -> dict[str, Memory]:
        """Map ``memory_id`` -> row for the ids that exist in the workspace."""
        ...

    def list(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        include_superseded: bool = False,
        topic: str | None = None,
        author_agent_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Memory]:
        """Newest-first browse; live-only unless ``include_superseded``."""
        ...

    def search_lexical(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        query: str,
        include_superseded: bool = False,
        topic: str | None = None,
        limit: int = 50,
    ) -> list[Memory]:
        """Deterministic substring match over title+content+topics (FR4).

        The degraded ranking when semantic search is unavailable: newest
        first, no score. ``%``/``_`` in ``query`` are matched literally.
        """
        ...

    def mark_superseded(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        memory_id: str,
        superseded_by: str,
    ) -> int:
        """Stamp ``superseded_by`` on a LIVE row; return rows changed (0/1).

        Exactly-once at the SQL level (guarded by ``superseded_by IS NULL``):
        0 means the target was already superseded - the service maps it to
        ``CONFLICT`` (BR4).
        """
        ...

    def delete(self, uow: UnitOfWork, *, workspace_id: str, memory_id: str) -> int:
        """Physically remove a row (operator curation only); rows removed."""
        ...


@runtime_checkable
class MemoryVectorStore(Protocol):
    """Persistence + cosine retrieval for per-memory embedding vectors.

    Same seam as :class:`MessageVectorStore` over the ``memory_embeddings``
    table: BLOB vector + brute-force cosine, lifecycle coupled to the memory
    row via ``ON DELETE CASCADE`` (D-EMB-5), incompatible-dim rows skipped in
    SQL (br_04f0e599).
    """

    def upsert(
        self,
        uow: UnitOfWork,
        *,
        memory_id: str,
        vector: Sequence[float],
        model: str,
        dim: int,
        created_at: str | None = None,
    ) -> None:
        """Insert/replace the vector for ``memory_id`` (serialised as a BLOB)."""
        ...

    def search(
        self, uow: UnitOfWork, *, query_vector: Sequence[float], k: int
    ) -> list[tuple[str, float]]:
        """Return up to ``k`` ``(memory_id, cosine_score)`` pairs, best first."""
        ...

    def delete(self, uow: UnitOfWork, *, memory_id: str) -> int:
        """Delete the vector for ``memory_id``; return rows removed (0 or 1)."""
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
        trace_id: str | None = None,
        acceptance_criteria: str | None = None,
        verify_by: str | None = None,
        created_at: str | None = None,
    ) -> Handoff:
        """Create a handoff, returning the stored row.

        ``acceptance_criteria`` / ``verify_by`` are the serialised TEXT
        verification contract (migration 018); ``None`` keeps the handoff on
        the plain non-verifiable flow.
        """
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

    def transition_verifying(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        handoff_id: str,
        status: str,
        updated_at: str | None = None,
        verification_feedback: str | None = None,
        lease_expires_at: str | None = None,
    ) -> Handoff | None:
        """Conditionally transition a VERIFYING handoff (verify verdict).

        Same contract as :meth:`transition_claimed`: the implementation must
        re-assert ``status='VERIFYING'`` atomically (single statement) and
        write the verdict outcome in that SAME UPDATE - on a ``CLAIMED``
        destination (fail) ``verification_feedback`` is always (over)written,
        including back to NULL, and ``lease_expires_at`` is renewed; on a
        terminal destination (pass) only the status changes. Return the
        updated row, or ``None`` when 0 rows were affected - the caller
        re-reads to raise the precise catalogue error.
        """
        ...

    def read_outcome(
        self, uow: UnitOfWork, *, workspace_id: str, handoff_id: str
    ) -> dict[str, str | None] | None:
        """Return ``{"result", "rejected_reason", "verification_feedback"}``.

        The outcome columns (migrations 008 + 018) are read separately from
        the :class:`Handoff` dataclass so the shared domain model stays
        stable; values are the serialised TEXT persisted by
        :meth:`transition_claimed` / :meth:`reject_open` /
        :meth:`transition_verifying`. ``None`` when the handoff is missing.
        """
        ...

    def read_verification(
        self, uow: UnitOfWork, *, workspace_id: str, handoff_id: str
    ) -> dict[str, str | None] | None:
        """Return ``{"acceptance_criteria", "verify_by"}``, or ``None``.

        The verification contract columns (migration 018) live outside the
        :class:`Handoff` dataclass (decision D6); NULL values mean the
        handoff is not verifiable.
        """
        ...

    def create_dependencies(
        self,
        uow: UnitOfWork,
        *,
        handoff_id: str,
        workspace_id: str,
        depends_on: list[str],
        created_at: str | None = None,
    ) -> None:
        """Persist the dependent's edges (migration 019) in ITS create UoW.

        One row per dependency, preserving the (already validated) list
        order. The rows are IMMUTABLE - the port deliberately exposes no
        update/delete for them.
        """
        ...

    def read_dependencies(
        self, uow: UnitOfWork, *, workspace_id: str, handoff_id: str
    ) -> list[dict[str, Any]]:
        """Return ``[{"depends_on_id", "status"}]`` in creation order.

        ``status`` is the dependency's CURRENT status (blocked-ness is
        derived on-read, never materialised); ``None`` (vanished row) is
        treated as pending by callers. Empty list = no dependencies.
        """
        ...

    def dependents_of(
        self, uow: UnitOfWork, *, workspace_id: str, depends_on_id: str
    ) -> list[str]:
        """Handoff ids that depend on ``depends_on_id`` (reverse index)."""
        ...

    def dependency_aggregates(
        self,
        uow: UnitOfWork,
        *,
        workspace_id: str,
        handoff_ids: Iterable[str],
    ) -> dict[str, dict[str, Any]]:
        """Per-handoff aggregates for a page of ids, in ONE ``IN`` query.

        ``{handoff_id: {"depends_on": [ids], "total", "satisfied",
        "pending", "failed"}}``; ids without dependency rows are absent.
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
        created_by: str | None = None,
        created_at: str | None = None,
        audience: list[Any] | None = None,
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
    presets: PresetRepo | None = None
    message_vectors: MessageVectorStore | None = None
    memories: MemoryRepo | None = None
    memory_vectors: MemoryVectorStore | None = None
    tag_catalog: TagCatalogRepo | None = None
    capability_catalog: CapabilityCatalogRepo | None = None
    governance: GovernanceRepo | None = None
    policies: PolicyRepo | None = None
    policy_bindings: AgentPolicyBindingRepo | None = None
    agent_groups: AgentGroupRepo | None = None
    guardrails: GuardrailRepo | None = None
    guardrail_assignments: GuardrailAssignmentRepo | None = None
    comm_presets: CommPresetRepo | None = None
    comm_bindings: AgentCommBindingRepo | None = None
    approvals: ApprovalRepo | None = None
    poll_tokens: PollTokenRepo | None = None
