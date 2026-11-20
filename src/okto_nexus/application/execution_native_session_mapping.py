"""Read a managed native identity from the canonical opening and its receipt."""

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from uuid import UUID

from nexus_connector_core.native.claude_history_identity import (
    CLAUDE_HISTORY_IDENTITY,
    confirmed_claude_history,
)

from ..adapters.outbound.sqlite.session_interaction import _scope_params
from ..domain.session_interaction import InputScope
from .execution_inventory_revalidation import selection


@dataclass(frozen=True, slots=True)
class NativeLaunchBuild:
    version: str
    platform: str
    architecture: str
    content_fingerprint: str
    build_identity: str | None
    qualification: str


def native_launch_build(snapshot: dict, opening: dict) -> dict | None:
    """Capture validated managed launch evidence at canonical admission."""
    if opening.get('mode') != 'managed' or opening.get('inventory_revision') != snapshot['inventory_revision']:
        return None
    selected = selection(snapshot, opening['adapter_id'], opening['candidate_ref'])
    if selected is None:
        return None
    build = _launch_build(selected['evidence'])
    return asdict(build) if build is not None else None


def _launch_build(evidence: dict) -> NativeLaunchBuild | None:
    fields = ('version', 'platform', 'architecture', 'content_fingerprint', 'qualification')
    values = {name: evidence.get(name) for name in fields}
    if not all(type(value) is str and value for value in values.values()):
        return None
    build_identity = evidence.get('build_identity')
    if build_identity is not None and (type(build_identity) is not str or not build_identity):
        return None
    return NativeLaunchBuild(**values, build_identity=build_identity)


@dataclass(frozen=True, slots=True)
class ClaudeHistoryIdentity:
    session_uuid: str
    operation_id: str
    event_hash: str


@dataclass(frozen=True, slots=True)
class ManagedNativeSession:
    scope: InputScope
    opening_operation_id: str
    adapter_id: str
    native_session_id: str
    stream_epoch: str | None
    launch_candidate_ref: str
    launch_inventory_revision: str
    launch_profile_revision: int
    launch_build: NativeLaunchBuild | None
    receipt_connection_id: str | None
    receipt_connection_generation: int | None
    codex_thread_id: str | None
    codex_configuration_hash: str | None
    claude_history: ClaudeHistoryIdentity | None = None


# Windows x64 app-server used in the local viewer and saved-history probes.
_CODEX_STATE_ENGINE = (
    '0.157.0', 'win32', 'x86_64',
    'sha256:ed1c7b36e44536809c868864c833af8a857f56599a7a7fe23b908a1ba1093b1f',
)


def reviewed_codex_context(mapping: ManagedNativeSession) -> bool:
    build = mapping.launch_build
    return (mapping.adapter_id == 'codex_app_server' and mapping.codex_thread_id is not None
            and build is not None and build.qualification == 'qualified'
            and (build.version, build.platform, build.architecture, build.content_fingerprint) == _CODEX_STATE_ENGINE)


_CLAUDE_SAVED_ENGINE = (
    '2.1.328', 'win32', 'x86_64',
    'sha256:551d573567b46ce78aba1b20beb20ac2494f5f8adffd1b41dfd269a96e1d9839',
)


def reviewed_claude_saved_context(mapping: ManagedNativeSession) -> bool:
    return mapping.claude_history is not None and reviewed_claude_terminal_context(mapping)


def reviewed_claude_terminal_context(mapping: ManagedNativeSession) -> bool:
    build = mapping.launch_build
    return (mapping.adapter_id == 'claude_stream'
            and build is not None
            and (build.version, build.platform, build.architecture, build.content_fingerprint) == _CLAUDE_SAVED_ENGINE)


# Portable identity of the full Node and Pi dependency closure exercised by
# the Windows hosted-renderer proof. The Core independently guards launch.
_PI_PRESENTATION_BUILD = (
    '0.87.1', 'win32', 'x86_64',
    'sha256:caf8bfad84ea26a7c8eaee06e0cde3dd7e34ef05e00dbebc348dfb3f22de487b',
)


def reviewed_pi_build(version, platform, architecture, build_identity) -> bool:
    return (version, platform, architecture, build_identity) == _PI_PRESENTATION_BUILD


def reviewed_pi_context(mapping: ManagedNativeSession) -> bool:
    build = mapping.launch_build
    return (mapping.adapter_id == 'pi_rpc' and build is not None
            and reviewed_pi_build(build.version, build.platform, build.architecture, build.build_identity))


def _codex_opening_thread(conn, scope, stream_epoch):
    events = conn.execute("""
        SELECT e.sequence,e.event_hash,e.payload_json
        FROM execution_event_ingress e
        JOIN execution_event_watermarks w USING(server_id,executor_id,session_id,stream_epoch)
        WHERE e.server_id=:server_id AND e.executor_id=:executor_id AND e.session_id=:session_id
          AND e.stream_epoch=:stream_epoch AND e.sequence<=w.committed_contiguous
          AND e.event_type='lifecycle' AND w.gap_state='none'
          AND json_extract(e.payload_json,'$.native_type')='core/codex_thread_configuration'
        LIMIT 2
    """, _scope_params(scope) | {'stream_epoch': stream_epoch}).fetchall()
    if len(events) != 1:
        return None, None
    event = events[0]
    raw = event['payload_json']
    if 'sha256:' + sha256(raw.encode()).hexdigest() != event['event_hash']:
        return None, None
    document = json.loads(raw)
    if (tuple(document.get(key) for key in ('server_id', 'executor_id', 'session_id', 'stream_epoch', 'sequence'))
            != (scope.session.server_id, scope.session.executor_id, scope.session.session_id, stream_epoch, event['sequence'])
            or document.get('category') != 'lifecycle' or document.get('operation_id') is not None):
        return None, None
    payload = document.get('payload')
    if (type(payload) is not dict or type(payload.get('schema_version')) is not int or payload['schema_version'] != 1
            or payload.get('adapter_id') != 'codex_app_server'
            or payload.get('source') not in ('thread/start/response', 'thread/resume/response')):
        return None, None
    thread_id = payload.get('thread_id')
    if type(thread_id) is not str or len(thread_id) != 36:
        return None, None
    try:
        if str(UUID(thread_id)) != thread_id:
            return None, None
    except ValueError:
        return None, None
    return thread_id, event['event_hash']


def _claude_history(conn, scope, stream_epoch):
    # The newest terminal result owns the evidence. Searching back for a
    # convenient UUID after a later unverified result can revive a stale owner.
    event = conn.execute("""
        SELECT e.sequence,e.event_hash,e.payload_json,r.operation_id,r.delivery_outcome
        FROM execution_event_ingress e
        JOIN execution_event_watermarks w USING(server_id,executor_id,session_id,stream_epoch)
        JOIN execution_results r ON r.server_id=e.server_id AND r.executor_id=e.executor_id
          AND r.session_id=e.session_id AND r.stream_epoch=e.stream_epoch AND r.terminal_sequence=e.sequence
          AND r.operation_id=json_extract(e.payload_json,'$.operation_id')
        JOIN execution_operations o ON o.server_id=r.server_id AND o.executor_id=r.executor_id
          AND o.operation_id=r.operation_id AND o.session_id=r.session_id
        WHERE e.server_id=:server_id AND e.executor_id=:executor_id AND e.session_id=:session_id
          AND e.stream_epoch=:stream_epoch AND e.sequence<=w.committed_contiguous
          AND e.event_type='turn_state' AND w.gap_state='none'
          AND o.subject_agent_id=:agent_id AND o.binding_id=:binding_id AND o.workspace_id=:workspace_id
          AND o.workspace_binding_id=:workspace_binding_id AND o.action IN ('turn.submit','turn.steer')
          AND json_extract(o.expected_revisions_json,'$.session_owner_generation')=:owner_generation
        ORDER BY e.sequence DESC LIMIT 1
    """, _scope_params(scope) | {'stream_epoch': stream_epoch}).fetchone()
    if event is None or event['delivery_outcome'] != 'success':
        return None
    raw = event['payload_json']
    if 'sha256:' + sha256(raw.encode()).hexdigest() != event['event_hash']:
        return None
    document = json.loads(raw)
    if (tuple(document.get(key) for key in ('server_id', 'executor_id', 'session_id', 'stream_epoch', 'sequence'))
            != (scope.session.server_id, scope.session.executor_id, scope.session.session_id, stream_epoch, event['sequence'])
            or document.get('category') != 'turn_state' or document.get('operation_id') != event['operation_id']
            or document.get('native_type') not in ('result:success', 'Stop')):
        return None
    payload = document.get('payload')
    if (type(payload) is not dict or payload.get('delivery_phase') != 'terminal'
            or payload.get('delivery_outcome') != 'success'):
        return None
    session_uuid = confirmed_claude_history(payload.get(CLAUDE_HISTORY_IDENTITY))
    if session_uuid is None or session_uuid != payload.get('session_id'):
        return None
    return ClaudeHistoryIdentity(session_uuid, event['operation_id'], event['event_hash'])


def read_managed_native_session(uow, scope: InputScope, *, include_claude_history=True) -> ManagedNativeSession | None:
    """Resolve retained identity only. Process ownership and access need separate proof."""
    row = uow.connection.execute("""
        SELECT s.stream_epoch, s.native_launch_build_json, p.operation_id, p.semantic_payload,
               r.native_id, r.source_connection_id, r.source_connection_generation
        FROM execution_sessions s
        JOIN execution_operations p ON p.server_id=s.server_id AND p.executor_id=s.executor_id
          AND p.operation_id=s.open_operation_id AND p.session_id=s.session_id
        JOIN execution_receipts r ON r.server_id=p.server_id AND r.executor_id=p.executor_id
          AND r.operation_id=p.operation_id AND r.receipt_revision=(
            SELECT MAX(prior.receipt_revision) FROM execution_receipts prior
            WHERE prior.server_id=p.server_id AND prior.executor_id=p.executor_id AND prior.operation_id=p.operation_id)
        WHERE s.server_id=:server_id AND s.executor_id=:executor_id AND s.session_id=:session_id
          AND s.binding_id=:binding_id AND s.workspace_id=:workspace_id
          AND s.workspace_binding_id=:workspace_binding_id AND s.owner_generation=:owner_generation
          AND p.action='runtime.open' AND p.subject_agent_id=:agent_id AND p.binding_id=:binding_id
          AND p.workspace_id=:workspace_id AND p.workspace_binding_id=:workspace_binding_id
          AND json_extract(p.expected_revisions_json,'$.session_owner_generation')=:owner_generation
          AND r.intent_hash=p.intent_hash AND r.stage IN ('SUBMITTED','SUCCEEDED')
    """, _scope_params(scope)).fetchone()
    if row is None:
        return None
    native_id = row['native_id']
    if (not isinstance(native_id, str) or not 1 <= len(native_id) <= 160
            or not native_id.isprintable() or 'REDACTED' in native_id):
        return None
    opening = json.loads(row['semantic_payload'])
    payload = opening.get('payload')
    if opening.get('action') != 'runtime.open' or not isinstance(payload, dict) or payload.get('mode') != 'managed':
        return None
    adapter, candidate, inventory = (payload.get(name) for name in ('adapter_id', 'candidate_ref', 'inventory_revision'))
    revision = payload.get('profile_revision')
    if not all(isinstance(value, str) and value for value in (adapter, candidate, inventory)):
        return None
    if type(revision) is not int or revision < 1:
        return None
    build = _launch_build(json.loads(row['native_launch_build_json'])) if row['native_launch_build_json'] else None
    thread, configuration_hash = (None, None)
    if adapter == 'codex_app_server' and row['stream_epoch'] is not None:
        thread, configuration_hash = _codex_opening_thread(uow.connection, scope, row['stream_epoch'])
    claude_history = (_claude_history(uow.connection, scope, row['stream_epoch'])
                      if include_claude_history and adapter == 'claude_stream'
                      and row['stream_epoch'] is not None else None)
    return ManagedNativeSession(scope, row['operation_id'], adapter, native_id, row['stream_epoch'],
        candidate, inventory, revision, build, row['source_connection_id'], row['source_connection_generation'],
        thread, configuration_hash, claude_history)
