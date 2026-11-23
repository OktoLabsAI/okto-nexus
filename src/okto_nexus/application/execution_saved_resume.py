"""Authorize a single exact successor for a verified, retired local source."""

import json

from nexus_connector_core import CodexRolloutEvidence
from nexus_connector_core.native.codex_rollout import saved_launch_configuration as saved_opening_profile

from ..errors import ErrorCode, OktoNexusError

_SAME_SCOPE = (
    'server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id', 'workspace_binding_id',
    'authorization_revision', 'configuration_revision', 'binding_revision', 'credential_epoch',
)


def rollout_evidence(document):
    return CodexRolloutEvidence(**(document | {
        key: tuple(document[key]) for key in ('relative_path', 'home_identity', 'file_identity')
    }))


def require_saved_resume_operator(*, actor, context, enabled):
    if not enabled:
        raise OktoNexusError(ErrorCode.CONFLICT, 'Saved session resume is unavailable.', {})
    if (actor != 'operator' or context is None or context.actor_agent_id != actor
            or context.authentication_source != 'operator_session' or not context.trusted_local_operator):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Sign in as a human operator to resume a saved session.', {})


def saved_source(conn, scope, source_session_id, source_generation, *, adapter_id='codex_app_server'):
    row = conn.execute("""
        SELECT c.witness_json, c.close_operation_id, c.release_digest, s.lifecycle_state, s.lease_state
        FROM execution_sessions s
        JOIN execution_executors e USING (server_id, executor_id)
        LEFT JOIN embedded_saved_contexts c ON c.server_id=s.server_id AND c.executor_id=s.executor_id
          AND c.session_id=s.session_id AND c.owner_generation=s.owner_generation
          AND c.status='VERIFIED' AND c.adapter_id=?
          AND s.open_operation_id=c.opening_operation_id AND s.stream_epoch=c.stream_epoch
          AND s.lifecycle_state='CLOSED' AND s.lease_state='CLOSED'
        WHERE s.server_id=? AND s.executor_id=? AND s.session_id=? AND s.owner_generation=?
          AND e.kind='embedded' AND s.binding_id=? AND s.workspace_id=? AND s.workspace_binding_id=?
    """, (adapter_id, scope['server_id'], scope['executor_id'], source_session_id, source_generation, scope['binding_id'],
          scope['workspace_id'], scope['workspace_binding_id'])).fetchone()
    if row is not None and row['lifecycle_state'] == 'READY' and row['lease_state'] == 'ACTIVE':
        raise OktoNexusError(ErrorCode.CONFLICT, 'The source session is still active. Saved resume requires a verified '
                          'close. Use live attachment when available.', {})
    if row is None or row['witness_json'] is None:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The exact session has no verified saved context on this host.', {})
    witness = json.loads(row['witness_json'])
    if adapter_id == 'claude_stream' and not witness.get('opening_profile', {}).get('claude_resume_profile'):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The saved Claude profile has no reviewed launch evidence.', {})
    if any(witness['scope'].get(key) != scope[key] for key in _SAME_SCOPE):
        raise OktoNexusError(ErrorCode.CONFLICT, 'The authority or configuration of the saved session changed.', {})
    lineage = {'source_session_id': source_session_id, 'source_session_generation': source_generation,
               'source_close_operation_id': row['close_operation_id'], 'source_release_digest': row['release_digest']}
    return lineage, witness


def require_saved_source_exclusive(conn, scope, lineage, *, successor=None):
    current = conn.execute("""
        SELECT session_id FROM execution_sessions
        WHERE server_id=? AND executor_id=? AND saved_resume_json IS NOT NULL
          AND json_extract(saved_resume_json, '$.source_session_id')=?
          AND json_extract(saved_resume_json, '$.source_session_generation')=?
    """, (scope['server_id'], scope['executor_id'], lineage['source_session_id'],
          lineage['source_session_generation'])).fetchone()
    if (current[0] if current else None) != successor:
        raise OktoNexusError(ErrorCode.CONFLICT, 'A successor already owns this saved session. Recover its original receipt.', {})


def require_saved_source_settled(conn, scope, source_session_id):
    key = scope['server_id'], scope['executor_id'], source_session_id
    if conn.execute("""
        SELECT 1 FROM execution_operations
        WHERE server_id=? AND executor_id=? AND session_id=? AND action<>'runtime.open'
          AND admission_state<>'RESOLVED_TERMINAL' LIMIT 1
    """, key).fetchone() or conn.execute("""
        SELECT 1 FROM session_interaction_inputs
        WHERE server_id=? AND executor_id=? AND session_id=?
          AND status IN ('DISPATCHING', 'DELIVERY_UNKNOWN') LIMIT 1
    """, key).fetchone():
        raise OktoNexusError(ErrorCode.CONFLICT, 'The saved session still has an unsettled delivery.', {})
