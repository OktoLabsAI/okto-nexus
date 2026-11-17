"""Unpaged, authority-free Home entry relations (UI-017/018).

This is an internal read projection, not an HTTP envelope or grant. Pagination
and target validation are deliberately owned by subsequent integration steps.
"""
from dataclasses import dataclass, field
from typing import Literal

from .attention import digest
from .home import ConnectionTarget, HomeActivity, HomeResult, HomeTarget, RuntimeRef, SessionTarget, SourceRef


EntryKind = Literal['work', 'session', 'connection', 'external', 'attention']
EntryState = Literal[
    'running', 'awaiting_owner', 'claimed', 'queued', 'native_accepted',
    'awaiting_dependency', 'awaiting_operator', 'awaiting_agent',
    'awaiting_verification', 'outcome_unknown', 'completed', 'turn_completed',
    'result_available_cleanup_pending', 'failed', 'cancelled',
    'configured', 'connected', 'idle', 'offline', 'stale',
]
Evidence = Literal['confirmed', 'reported', 'inferred', 'unknown']
SourceState = Literal['ready', 'partial', 'unavailable', 'disabled', 'forbidden']


@dataclass(frozen=True)
class SessionContext:
    server_id: str
    executor_id: str
    workspace_id: str
    session_id: str
    binding_id: str
    workspace_binding_id: str
    agent_id: str | None
    lifecycle_state: str


@dataclass(frozen=True)
class ConnectionContext:
    server_id: str
    executor_id: str
    workspace_id: str
    binding_id: str
    workspace_binding_id: str
    agent_id: str
    harness_id: str | None = None
    workspace_label: str | None = None
    host_label: str | None = None
    agent_label: str | None = None
    connect_id: str | None = None


@dataclass
class EntryRecord:
    id: str
    kind: EntryKind
    source_ref: SourceRef
    workspace_id: str
    agent_id: str | None
    title: str
    display_state: EntryState
    evidence: Evidence
    target: HomeTarget | SessionTarget | ConnectionTarget | None
    connection: ConnectionContext | None = None
    sessions: tuple[SessionContext, ...] = ()
    operations: list[RuntimeRef] = field(default_factory=list)
    attention: list[dict[str, object]] = field(default_factory=list)
    results: list[HomeResult] = field(default_factory=list)
    external: list[dict[str, object]] = field(default_factory=list)
    activity: HomeActivity | None = None
    # Complete persisted operation-to-binding proofs. The singleton legacy
    # connection/group identity above deliberately remains unchanged.
    registered_connections: tuple[ConnectionContext, ...] = ()

    def group_key(self):
        c = self.connection
        # A label or agent alone never proves a shared connection.
        return (1, c.server_id, c.executor_id, c.binding_id, c.workspace_id,
                c.workspace_binding_id, c.agent_id) if c else (1, 'origin', self.id)

    @property
    def group_id(self):
        return 'home_group_' + digest(self.group_key())


@dataclass
class EntryRelations:
    entries: list[EntryRecord]
    server_attention: list[dict[str, object]]
    source_status: dict[str, SourceState]
    # Authorized workspace inventory, before presentation filters and paging.
    # None is unknown, including adapters that do not supply this evidence.
    connection_count: int | None = None
    connections: tuple[ConnectionContext, ...] | None = None
    harness_blocking: list[dict[str, object]] | None = None

    @property
    def total_is_exact(self):
        return all(value == 'ready' for value in self.source_status.values())

    @property
    def total(self):
        return len(self.entries) if self.total_is_exact else None


def activity_record(item: HomeActivity, *, agent_id: str | None = None):
    return EntryRecord(id=item['id'], kind='work', source_ref=item['source_ref'],
        workspace_id=item['workspace_id'], agent_id=agent_id, title=item['title'],
        display_state=item['display_state'], evidence=item['evidence_status'],
        target=item['detail_target'], activity=item)


def passive_record(context: SessionContext | ConnectionContext):
    is_session = isinstance(context, SessionContext)
    kind = 'session' if is_session else 'connection'
    source_id = context.session_id if is_session else context.binding_id
    identity = [1, context.server_id, context.executor_id, kind, source_id]
    target = dict(kind=kind, server_id=context.server_id, executor_id=context.executor_id,
                  workspace_id=context.workspace_id)
    if is_session:
        target['session_id'] = source_id
    else:
        target.update(binding_id=source_id, agent_id=context.agent_id)
    # Persisted configuration/session presence is not evidence of live execution.
    state = 'idle' if is_session and context.lifecycle_state in ('READY', 'ACTIVE') else 'offline' if is_session else 'configured'
    return EntryRecord(id='home_entry_' + digest(identity), kind=kind,
        source_ref=dict(type=kind, id=source_id, revision=digest(context.__dict__)),
        workspace_id=context.workspace_id, agent_id=context.agent_id,
        title='Session' if is_session else 'Connection', display_state=state,
        evidence='confirmed', target=target)
