"""Shared domain entities (pure dataclasses).

These dataclasses are the in-memory shape of the persisted rows. They are
referenced by the application ports so that every slice agrees on a single
representation. JSON-ish columns (``payload``, ``capabilities``, ``metadata``,
``artifacts``) are modelled as native Python ``dict``/``list``; the SQLite
adapter is responsible for (de)serialising them to/from TEXT.

Pure module: stdlib only, no ``sqlite3``/``mcp`` (enforced by the boundary
test). Fields mirror the columns declared in ``migrations/001_core.sql``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Workspace:
    """A coordination workspace, keyed by the deterministic ``workspace_id``."""

    workspace_id: str
    created_at: str
    display_name: str | None = None
    root_realpath: str | None = None
    last_seen_at: str | None = None


@dataclass(slots=True)
class Agent:
    """A logical agent identity (global; not workspace-scoped).

    ``api_key_hash``/``is_active`` (migration 009, Nexus v2): a registered
    key is the primary credential on the HTTP transport. Only the SHA256
    hash is ever stored; ``api_key_hash`` is ``None`` while no key has been
    issued (V1 agents pre `admin issue-keys`). ``is_active`` is the
    revocation switch - an inactive agent's key must not authenticate.
    """

    agent_id: str
    created_at: str
    role: str | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_seen_at: str | None = None
    api_key_hash: str | None = None
    is_active: bool = True
    # Migration 011: communication permissions. ``None`` = full access
    # (default-allow); ``preset_id`` records which preset the flags were
    # copied from (informational - enforcement reads ``permissions`` only).
    permissions: dict[str, Any] | None = None
    preset_id: str | None = None
    # Migration 013: tag-based communication scoping. ``tags`` is the
    # catalog-validated multi-value tag map ({} = none; exposed on discovery);
    # ``comm_scope`` is the operator-set communication scope (``None`` =
    # unrestricted) and is NEVER exposed on any discovery surface.
    tags: dict[str, Any] = field(default_factory=dict)
    comm_scope: dict[str, Any] | None = None
    # Migration 024: per-agent display color for the dashboard graph cards.
    # ``None`` = unset = auto-by-identity (derived from ``agent_id`` on the
    # client). Stored verbatim (e.g. "#22c55e").
    color: str | None = None


@dataclass(slots=True)
class PermissionPreset:
    """A CUSTOM permission preset (built-ins live in domain.permissions)."""

    preset_id: str
    name: str
    flags: dict[str, Any]
    created_at: str
    updated_at: str
    description: str | None = None


@dataclass(slots=True)
class TagKey:
    """A registered tag key in the central catalog (migration 013)."""

    key: str
    created_at: str
    description: str | None = None


@dataclass(slots=True)
class TagValue:
    """A registered tag value, existing only under its registered key."""

    key: str
    value: str
    created_at: str
    description: str | None = None


@dataclass(slots=True)
class CapabilityName:
    """A registered capability name in the central catalog (migration 014)."""

    name: str
    created_at: str
    description: str | None = None


@dataclass(slots=True)
class Session:
    """A live agent session bound to a workspace."""

    session_id: str
    agent_id: str
    workspace_id: str
    status: str
    started_at: str
    last_heartbeat_at: str | None = None
    closed_at: str | None = None


@dataclass(slots=True, frozen=True)
class Event:
    """An append-only, immutable coordination event.

    ``event_id`` is a global, monotonic INTEGER assigned inside the writing
    transaction. ``None`` only before insertion (it is server-assigned).
    """

    workspace_id: str
    stream: str
    type: str
    created_at: str
    event_id: int | None = None
    actor_agent_id: str | None = None
    payload: dict[str, Any] | None = None
    visibility: str | None = None
    target: str | None = None


@dataclass(slots=True)
class Channel:
    """A named message channel within a workspace (unique per ``(workspace, name)``)."""

    channel_id: str
    workspace_id: str
    name: str
    created_at: str


@dataclass(slots=True)
class Message:
    """A message posted to a channel or directed at a target."""

    message_id: str
    workspace_id: str
    from_agent_id: str
    created_at: str
    channel_id: str | None = None
    from_session_id: str | None = None
    target: str | None = None
    subject: str | None = None
    body: str | None = None
    artifacts: list[Any] = field(default_factory=list)
    parent_message_id: str | None = None
    trace_id: str | None = None


@dataclass(slots=True)
class MessageDelivery:
    """A per-recipient delivery record for a message (the inbox lane, ADR 0001).

    GLOBAL (not workspace-scoped): an agent's inbox spans every workspace.
    ``status`` is one of ``unread`` / ``delivered`` (in-flight, leased) /
    ``read`` (acknowledged into history). Mirrors ``migrations/005``.
    """

    delivery_id: str
    message_id: str
    recipient_agent_id: str
    status: str
    created_at: str
    delivered_at: str | None = None
    lease_expires_at: str | None = None
    read_at: str | None = None


@dataclass(slots=True)
class Task:
    """A unit of work tracked within a workspace."""

    task_id: str
    workspace_id: str
    title: str
    status: str
    created_at: str
    description: str | None = None
    created_by: str | None = None


@dataclass(slots=True)
class Handoff:
    """A claimable transfer of work, optionally linked to a task."""

    handoff_id: str
    workspace_id: str
    status: str
    created_at: str
    task_id: str | None = None
    from_agent_id: str | None = None
    target: str | None = None
    visibility: str | None = None
    claimed_by: str | None = None
    lease_expires_at: str | None = None
    updated_at: str | None = None
    payload: str | None = None
    trace_id: str | None = None


@dataclass(slots=True)
class Artifact:
    """A stored artifact (inline content or a workspace-relative path reference)."""

    artifact_id: str
    workspace_id: str
    artifact_type: str
    created_at: str
    name: str | None = None
    path: str | None = None
    content: str | None = None
    size_bytes: int | None = None
    content_type: str | None = None
    # Migration 016: authoring agent (None on legacy rows / identity-less
    # cooperative stdio puts). Backs the artifact_put governance quota; never
    # surfaced by the artifact contracts.
    created_by: str | None = None
    # Migration 022 (spec 80624c1a, D-ART): the publisher's EFFECTIVE OUTBOUND
    # audience, FROZEN as an ordered selector list at artifact_put time and
    # IMMUTABLE thereafter (D11). ``None`` = no restriction (public / legacy
    # rows). Re-evaluated against a reader's tags on artifact_get (AND, via
    # ``policy.snapshot_permits``); the ``artifact.created`` event carries the
    # same audience so the stream never leaks what the read-path hides (BR7).
    audience: list[Any] | None = None


@dataclass(slots=True)
class Memory:
    """A durable workspace memory entry (migration 020).

    Append-only for agents: correction happens by superseding (``supersedes``
    on the new row + ``superseded_by`` stamped on the target, both in the same
    unit of work). ``author_agent_id`` is NOT NULL - a memory without an
    author never exists. Provenance (``source_kind``/``source_id``) is an
    informative pointer whose target existence is never verified.
    """

    memory_id: str
    workspace_id: str
    author_agent_id: str
    title: str
    content: str
    created_at: str
    topics: list[str] = field(default_factory=list)
    source_kind: str | None = None
    source_id: str | None = None
    supersedes: str | None = None
    superseded_by: str | None = None
    trace_id: str | None = None
