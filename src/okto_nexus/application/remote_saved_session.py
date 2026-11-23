"""Read a closed native session from canonical Nexus facts and the current Connector."""

import asyncio
from datetime import datetime, timezone
import json

from nexus_connector_core import CoreError, r4_resource_release_digest
from nexus_connector_core.native.pi_saved_history import is_pi_saved_session_id
from nexus_connector_core.saved_context_link import (
    CLAUDE_SAVED_CONTEXT, CODEX_SAVED_CONTEXT, PI_SAVED_CONTEXT, saved_native_session_digest,
)

from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ..adapters.outbound.sqlite.execution_leases import SqliteExecutionLeaseRepository
from ..domain.execution.keys import SessionKey, SessionOwnerGeneration
from ..domain.session_interaction import InputScope
from ..errors import ErrorCode, OktoNexusError
from .execution_leases import require_execution_lane
from .execution_native_session_mapping import (
    read_managed_native_session, reviewed_claude_saved_context, reviewed_codex_context, reviewed_pi_context,
)
from .execution_reconciliation import _receipt
from .execution_saved_resume import (
    require_saved_resume_operator, require_saved_source_exclusive, require_saved_source_settled,
)


REMOTE_SAVED_CONTEXTS = {
    CODEX_SAVED_CONTEXT.adapter_id: CODEX_SAVED_CONTEXT,
    CLAUDE_SAVED_CONTEXT.adapter_id: CLAUDE_SAVED_CONTEXT,
    PI_SAVED_CONTEXT.adapter_id: PI_SAVED_CONTEXT,
}
SAVED_RESUME_MARKERS = frozenset(f'saved_{codec.name}_resume' for codec in REMOTE_SAVED_CONTEXTS.values())


def _unavailable():
    return OktoNexusError(ErrorCode.CONFLICT, 'The exact session has no verified saved context on this Connector.', {})


def read_retired_remote_session(uow, scope, *, session_id, generation, adapter_id=None):
    """Derive the wire origin from one reviewed, closed opening and its exact close."""
    conn = uow.connection
    source_scope = dict(scope, session_id=session_id, session_owner_generation=generation)
    key = scope['server_id'], scope['executor_id'], session_id
    selected = conn.execute("""
        SELECT s.lifecycle_state,s.lease_state,s.stream_epoch,s.open_operation_id,o.expected_revisions_json,e.kind
        FROM execution_sessions s JOIN execution_executors e USING(server_id,executor_id)
        JOIN execution_operations o ON o.server_id=s.server_id AND o.executor_id=s.executor_id
          AND o.operation_id=s.open_operation_id AND o.session_id=s.session_id AND o.action='runtime.open'
        WHERE s.server_id=? AND s.executor_id=? AND s.session_id=? AND s.owner_generation=?
          AND s.binding_id=? AND s.workspace_id=? AND s.workspace_binding_id=? AND o.subject_agent_id=?
    """, (*key, generation, scope['binding_id'], scope['workspace_id'], scope['workspace_binding_id'],
          scope['agent_id'])).fetchone()
    if (selected is None or selected['kind'] != 'remote' or selected['lifecycle_state'] != 'CLOSED'
            or selected['lease_state'] != 'CLOSED' or not selected['stream_epoch']
            or json.loads(selected['expected_revisions_json']) != source_scope):
        raise _unavailable()
    exact = InputScope(SessionKey(*key), SessionOwnerGeneration(generation), scope['binding_id'],
                       scope['workspace_id'], scope['workspace_binding_id'], scope['agent_id'])
    mapping = read_managed_native_session(uow, exact, include_claude_history=adapter_id != 'codex_app_server')
    if mapping is None or (adapter_id is not None and mapping.adapter_id != adapter_id):
        raise _unavailable()
    codec = REMOTE_SAVED_CONTEXTS.get(mapping.adapter_id)
    reviewers = {CODEX_SAVED_CONTEXT: reviewed_codex_context, CLAUDE_SAVED_CONTEXT: reviewed_claude_saved_context,
                 PI_SAVED_CONTEXT: reviewed_pi_context}
    if codec is None or not reviewers[codec](mapping):
        raise _unavailable()
    if codec is PI_SAVED_CONTEXT and not is_pi_saved_session_id(mapping.native_session_id):
        raise _unavailable()
    facts = conn.execute("""
        SELECT r.*,o.action,o.expected_revisions_json,o.intent_hash AS operation_intent
        FROM execution_operations o JOIN execution_receipts r USING(server_id,executor_id,operation_id)
        WHERE o.server_id=? AND o.executor_id=? AND o.session_id=? AND (
          o.operation_id=? OR (o.action='runtime.close' AND o.admission_state='RESOLVED_TERMINAL' AND r.stage='SUCCEEDED'))
          AND r.receipt_revision=(SELECT MAX(revisions.receipt_revision) FROM execution_receipts revisions
            WHERE revisions.server_id=o.server_id AND revisions.executor_id=o.executor_id
              AND revisions.operation_id=o.operation_id)
        LIMIT 3
    """, (*key, selected['open_operation_id'])).fetchall()
    if len(facts) != 2 or {row['action'] for row in facts} != {'runtime.open', 'runtime.close'}:
        raise _unavailable()
    receipts = {}
    for row in facts:
        receipt = _receipt(row)
        if (receipt is None or not receipt['possible_effect'] or row['operation_intent'] != receipt['intent_hash']
                or json.loads(row['expected_revisions_json']) != source_scope
                or any(receipt.get(field) != scope[field] for field in ('agent_id', 'binding_id'))
                or receipt['session_id'] != session_id or receipt['connection_id'] != mapping.receipt_connection_id
                or receipt['connection_generation'] != mapping.receipt_connection_generation):
            raise _unavailable()
        receipts[row['action']] = receipt
    opening, closing = receipts['runtime.open'], receipts['runtime.close']
    source = dict(source_connection_id=opening['connection_id'],
        source_connection_generation=opening['connection_generation'], stream_epoch=selected['stream_epoch'],
        opening_operation_id=opening['operation_id'], close_operation_id=closing['operation_id'],
        resource_release_digest=r4_resource_release_digest(server_id=key[0], executor_id=key[1], session_id=key[2],
            opening_operation_id=opening['operation_id'], opening_intent_hash=opening['intent_hash'],
            owner_generation=generation))
    if codec is CLAUDE_SAVED_CONTEXT:
        source['native_session_digest'] = saved_native_session_digest(mapping.claude_history.session_uuid)
    elif codec is PI_SAVED_CONTEXT:
        source['native_session_digest'] = saved_native_session_digest(mapping.native_session_id)
    lineage = dict(source_session_id=session_id, source_session_generation=generation,
        source_close_operation_id=closing['operation_id'], source_release_digest=source['resource_release_digest'],
        connector_source=source)
    require_saved_source_settled(conn, scope, session_id)
    return lineage, source_scope, mapping.launch_build, codec


async def review_saved_session_on_connector(factory, body, *, context, config, auth, human_ref, links):
    """Consult the exact Connector outside the transaction, then repeat the authority checks."""
    require_saved_resume_operator(actor=context.actor_agent_id, context=context, enabled=config.runtime_session_interaction_enabled)

    def select():
        with auth.authority_fence() as human, factory.unit_of_work(write=False) as uow:
            if human_ref is None or not human(human_ref):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The operator session ended.', {})
            conn = uow.connection
            if conn.execute('SELECT 1 FROM execution_client_intents WHERE actor_agent_id=? AND client_intent_id=?',
                            (context.actor_agent_id, body['client_intent_id'])).fetchone():
                return None  # Resolve will validate and return the durable receipt.
            facts = conn.execute("""
                SELECT o.expected_revisions_json,e.kind,e.control_state,e.owner_instance_id,e.generation,e.revoked_at
                FROM execution_sessions s JOIN execution_executors e USING(server_id,executor_id)
                JOIN execution_operations o ON o.server_id=s.server_id AND o.executor_id=s.executor_id
                  AND o.operation_id=s.open_operation_id AND o.session_id=s.session_id
                WHERE s.session_id=? AND s.owner_generation=? AND s.binding_id=? AND s.workspace_binding_id=?
                  AND o.subject_agent_id=? LIMIT 2
            """, (body.get('session_id'), body.get('source_session_generation'), body['binding_id'],
                  body['workspace_binding_id'], body.get('agent_id'))).fetchall()
            if len(facts) != 1 or facts[0]['kind'] != 'remote':
                return None  # The canonical resolution handles the local or missing source.
            row = facts[0]
            scope = json.loads(row['expected_revisions_json'])
            server, revisions, _ = current_agent_revisions(factory, agent_id=scope['agent_id'], uow=uow, persist=False)
            link = links.get((scope['server_id'], scope['executor_id']))
            if (link is None or link.closed or row['control_state'] != 'CONTROL_READY'
                    or row['revoked_at'] is not None or (row['owner_instance_id'], row['generation']) !=
                        (link.channel.connection_id, link.channel.connection_generation)
                    or server != scope['server_id'] or (revisions.authorization, revisions.configuration,
                        revisions.credential_epoch) != (scope['authorization_revision'], scope['configuration_revision'],
                        scope['credential_epoch'])):
                raise _unavailable()
            owner = SqliteExecutionLeaseRepository().authority(uow, scope)
            if (owner is None or not owner['is_active'] or not owner['enabled'] or owner['activation_state'] != 'approved'
                    or owner['health'] == 'quarantined' or owner['workspace_status'] != 'READY'
                    or owner['realization_status'] != 'READY' or owner['binding_revision'] != scope['binding_revision']
                    or owner['realization_revision'] != owner['current_realization_revision']):
                raise _unavailable()
            require_execution_lane(uow, scope=scope, channel=link.channel, now=datetime.now(timezone.utc))
            lineage, source_scope, build, codec = read_retired_remote_session(uow, scope,
                session_id=body['session_id'], generation=body['source_session_generation'])
            require_saved_source_exclusive(conn, source_scope, lineage)
            if not link.supports_saved_context(codec):
                raise _unavailable()
            return lineage, source_scope, build, link, codec

    review = await asyncio.to_thread(select)
    if review is None:
        return None
    lineage, scope, _, link, codec = review
    try:
        available = await link.probe_saved_context(codec, scope=scope, source=lineage['connector_source'])
    except CoreError:
        raise _unavailable() from None
    if not available or await asyncio.to_thread(select) != review:
        raise _unavailable()
    return lineage
