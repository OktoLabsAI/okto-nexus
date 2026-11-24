"""Derive next-turn support from the current owner and exact Core build."""

import json
from dataclasses import asdict

from nexus_connector_core import CAPACITY_CONTRACT_REVISION
from nexus_connector_core.turn_operation import PI_LITERAL_INPUT_REVISION

from ..adapters.outbound.sqlite.execution_leases import SqliteExecutionLeaseRepository
from ..adapters.outbound.sqlite.session_interaction import (
    _current_session,
    _scope_params,
)
from ..adapters.outbound.sqlite.session_interaction_queue_controls import (
    has_unresolved_interrupt,
)
from ..domain.attention import digest
from ..domain.session_interaction import InputScope
from .execution_inventory_freshness import inventory_is_fresh
from .execution_inventory_revalidation import accepts_binding, selection
from .execution_native_session_mapping import (
    read_managed_native_session,
    reviewed_pi_presentation_context,
)
from .executor_inventory import load_current_executor_inventory


def literal_input_available(uow, scope: InputScope, host) -> bool:
    if host is None or PI_LITERAL_INPUT_REVISION not in host.channel.control_capabilities:
        return False
    mapping = read_managed_native_session(uow, scope)
    return (mapping is not None and reviewed_pi_presentation_context(mapping)
            and mapping.launch_build.qualification == 'qualified')


def queue_pause_revision(uow, scope: InputScope, paused: bool, *, current_next_turn_revision) -> str | None:
    if not _current_session(uow.connection, _scope_params(scope), require_active_lease=not paused):
        return None
    next_turn = None
    if not paused:
        if has_unresolved_interrupt(uow.connection, scope.session):
            return None
        next_turn = current_next_turn_revision(uow, scope)
        if next_turn is None:
            return None
    return 'sha256:' + digest({'action': 'queue.pause.v1' if paused else 'queue.resume.v1',
                              'scope': _scope_params(scope), 'next_turn': next_turn})


def next_turn_state(uow, scope: InputScope, *, stream_epoch, connection_id, connection_generation) -> str:
    """Describe timing for a qualified managed session, without reserving capacity."""
    params = _scope_params(scope) | {'stream_epoch': stream_epoch, 'connection_id': connection_id,
                                    'connection_generation': connection_generation}
    stream = uow.connection.execute("""
        SELECT 1 FROM execution_event_watermarks w
        WHERE w.server_id=:server_id AND w.executor_id=:executor_id AND w.session_id=:session_id
          AND w.stream_epoch=:stream_epoch AND w.committed_contiguous>0 AND w.gap_state='none'
          AND NOT EXISTS (
            SELECT 1 FROM execution_event_ingress e
            WHERE e.server_id=w.server_id AND e.executor_id=w.executor_id AND e.session_id=w.session_id
              AND e.stream_epoch=w.stream_epoch AND e.sequence<=w.committed_contiguous
              AND e.event_type='error' AND CASE WHEN json_valid(e.payload_json)
                  THEN json_extract(e.payload_json,'$.native_type')='core.event_pump_failed' ELSE 1 END
          )
    """, params).fetchone()
    if stream is None:
        return 'unknown'

    # A submitted turn from this owner occupies the next-turn lane. Uncertain
    # admission or a pending control prevents a positive idle observation.
    pending = uow.connection.execute("""
        SELECT CASE WHEN o.action='turn.submit' AND o.admission_state='DISPATCHED'
             AND o.binding_id=:binding_id AND o.workspace_id=:workspace_id
             AND o.workspace_binding_id=:workspace_binding_id AND o.subject_agent_id=:agent_id
             AND CASE WHEN json_valid(o.expected_revisions_json)
                 THEN json_extract(o.expected_revisions_json,'$.session_owner_generation')=:owner_generation END
             AND d.dispatch_state='DISPATCHED' AND r.stage IN ('SUBMITTED','ACCEPTED')
             AND r.source_connection_id=:connection_id AND r.source_connection_generation=:connection_generation
             AND result.terminal_sequence IS NULL
           THEN 1 ELSE 0 END AS occupies_next_turn
        FROM execution_operations o
        LEFT JOIN execution_dispatch_outbox d USING(server_id, executor_id, operation_id)
        LEFT JOIN execution_receipts r ON r.server_id=o.server_id AND r.executor_id=o.executor_id
          AND r.operation_id=o.operation_id AND r.receipt_revision=d.last_receipt_revision
        LEFT JOIN execution_results result ON result.server_id=o.server_id AND result.executor_id=o.executor_id
          AND result.operation_id=o.operation_id
        WHERE o.server_id=:server_id AND o.executor_id=:executor_id AND o.session_id=:session_id
          AND o.action IN ('turn.submit','turn.steer','turn.interrupt','runtime.close')
          AND o.admission_state NOT IN ('REJECTED','RESOLVED_TERMINAL')
        ORDER BY occupies_next_turn DESC LIMIT 1
    """, params).fetchone()
    if pending is None:
        return 'idle'
    return 'busy' if pending['occupies_next_turn'] else 'unknown'


def next_turn_revision(uow, scope: InputScope, *, availability, fresh_publications) -> str | None:
    """Return a technical revision only. Human and grant authority are separate."""
    session = asdict(scope.session)
    key = (scope.session.server_id, scope.session.executor_id)
    host = availability.current_host(*key)
    if host is None or not host.boot_id:
        return None
    observation = host.observations.get(scope.binding_id)
    if observation is None or observation[2] <= availability.monotonic():
        return None

    conn = uow.connection
    if not _current_session(conn, _scope_params(scope), require_active_lease=True):
        return None
    leases = SqliteExecutionLeaseRepository()
    owner = leases.authority(uow, session)
    if (owner is None or owner['control_state'] != 'CONTROL_READY' or owner['revoked_at'] is not None
            or (owner['owner_instance_id'], owner['generation']) != (
                host.channel.connection_id, host.channel.connection_generation
            )):
        return None
    if owner['kind'] == 'remote' and not host.channel.supports_work_containment:
        return None

    opening = json.loads(owner['semantic_payload'])
    payload = opening.get('payload', {})
    adapter, candidate = owner['adapter_id'], owner['candidate_ref']
    if (opening.get('action') != 'runtime.open' or payload.get('mode') != 'managed'
            or (payload.get('adapter_id'), payload.get('candidate_ref')) != (adapter, candidate)):
        return None

    inventory = leases.inventory(uow, session)
    if (not inventory_is_fresh(inventory, fresh_publications.get(key), adapter)
            or not accepts_binding(conn, owner, inventory['inventory_revision'], *key)):
        return None
    snapshot = load_current_executor_inventory(inventory['canonical_projection'])
    selected = selection(snapshot, adapter, candidate)
    if selected is None or selected['runtime']['connection_mode'] != 'managed':
        return None
    evidence = selected['evidence']
    if (evidence['state'] != 'READY_FOR_RUNTIME' or evidence['trust'] != 'selected'
            or evidence['qualification'] != 'qualified'):
        return None

    opening_revision = payload.get('inventory_revision')
    if opening_revision != inventory['inventory_revision']:
        launched = conn.execute("""
            SELECT canonical_projection FROM execution_inventory_snapshots
            WHERE server_id=? AND executor_id=? AND inventory_revision=?
            ORDER BY publication_sequence DESC LIMIT 1
        """, (*key, opening_revision)).fetchone()
        if launched is None:
            return None
        original = selection(json.loads(launched['canonical_projection']), adapter, candidate)
        if original is None or _build(original['evidence']) != _build(evidence):
            return None

    # Lease renewal and publication heartbeats preserve the revision. Exact
    # capacity requests independently carry the current boot and connection.
    return 'sha256:' + digest({
        'scope': _scope_params(scope),
        'binding_revision': owner['binding_revision'],
        'contract': CAPACITY_CONTRACT_REVISION,
        'candidate': candidate,
        'adapter': adapter,
        'build': _build(evidence),
    })


def _build(evidence):
    return {field: evidence.get(field) for field in (
        'content_fingerprint', 'build_identity', 'version', 'platform', 'architecture', 'qualification',
    )}
