"""One-shot orchestration through the existing authorized R4 execution path.

Both embedded hosts and remote Connectors receive ordinary canonical open,
turn and close operations. Reservations never bypass admission or lease checks.
"""
import hashlib
import json
import time

from . import one_shot_capacity as capacity
from ..errors import ErrorCode, OktoNexusError


def digest(conn, binding):
    endpoint = dict(conn.execute('SELECT revision,public_config,agent_id FROM agent_endpoints WHERE endpoint_id=?',
                                (binding['endpoint_id'],)).fetchone())
    from .runtime_policy import effective
    preset = conn.execute('SELECT configuration_digest FROM runtime_mcp_presets WHERE endpoint_id=?',
                          (binding['endpoint_id'],)).fetchone()
    body = dict(binding=dict(binding), endpoint=endpoint,
                inherit_mcps=effective(conn, endpoint['agent_id'])['inherit_global_mcps'],
                preset=preset[0] if preset else None)
    body['binding'].pop('session_policy', None)
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def host_limit(conn, executor_id):
    row = conn.execute('SELECT max_instances FROM one_shot_host_limits WHERE executor_id=?', (executor_id,)).fetchone()
    limit = row[0] if row else 64
    # Non-one-shot sessions share the physical host budget. A tracked session
    # must not be counted a second time as a reservation and a canonical session.
    other = conn.execute("SELECT count(*) FROM execution_sessions s WHERE executor_id=? "
        "AND NOT (lifecycle_state IN ('CLOSED','FAILED') AND lease_state IN ('NONE','CLOSED')) "
        "AND NOT EXISTS (SELECT 1 FROM one_shot_slots p "
        'WHERE p.executor_id=s.executor_id AND p.session_id=s.session_id)', (executor_id,)).fetchone()[0]
    return max(0, limit - other)


def admit_call(uow, operation, binding, *, caller_id):
    conn = uow.connection
    previous = conn.execute('SELECT call_id FROM one_shot_calls WHERE call_id=?', (operation['operation_id'],)).fetchone()
    call = capacity.admit(conn, call_id=operation['operation_id'], agent_id=operation['recipient_agent_id'],
        executor_id=binding['executor_id'], caller_id=caller_id, request_hash=operation['request_hash'],
        configuration_digest=digest(conn, binding), host_limit=host_limit(conn, binding['executor_id']), now=time.time())
    if call['state'] in ('FAILED', 'CANCELLED', 'SUCCEEDED'):
        if not previous and call['state'] == 'FAILED':
            error = json.loads(call['outcome_json'])['error']
            raise OktoNexusError(ErrorCode.CONFLICT, error['code'] + ': ' + error['message'], error)
        return None
    # This durable logical call, not the legacy retry worker, owns its queue.
    conn.execute("UPDATE delivery_outbox SET status='ACCEPTED',owner_epoch=NULL,lease_expires_at=NULL WHERE operation_id=?",
                 (operation['operation_id'],))
    if call['state'] == 'QUEUED':
        return None
    row = conn.execute('SELECT * FROM one_shot_slots WHERE call_id=?', (call['call_id'],)).fetchone()
    if row is None:
        return None  # Capacity reserved; wait for any compatible ready instance.
    slot = dict(row)
    conn.execute('UPDATE one_shot_slots SET server_id=?,binding_id=? WHERE slot_id=?',
                 (binding['server_id'], binding['binding_id'], slot['slot_id']))
    return slot


def before_send(conn, operation):
    """Fence productive dispatch before the send, including initial turn children."""
    if operation['action'] != 'turn.submit':
        return
    slot = conn.execute('SELECT p.* FROM one_shot_slots p JOIN execution_domain_deliveries d ON d.domain_operation_id=p.call_id '
        'WHERE d.server_id=? AND d.executor_id=? AND d.operation_id=?',
        (operation['server_id'], operation['executor_id'], operation['operation_id'])).fetchone()
    if not slot:
        return
    if slot['state'] == 'STARTING':
        capacity.ready(conn, slot_id=slot['slot_id'], session_id=operation['session_id'])
    capacity.started(conn, call_id=slot['call_id'], now=time.time())


def _admit(uow, access, fresh, remote, binding, identity, intent, session_id=None, slot_id=None):
    from .execution_domain_delivery import DeliveryTransactionFactory
    from .execution_intents import resolve_execution_intent
    from .execution_admission import submit_execution_operation
    agent = uow.connection.execute('SELECT agent_id FROM agent_endpoints WHERE endpoint_id=?', (binding['endpoint_id'],)).fetchone()[0]
    request = dict(client_intent_id=identity, intent=intent, binding_id=binding['binding_id'],
                   workspace_binding_id=binding['workspace_binding_id'])
    request.update({'new_session': True} if intent == 'runtime.start' else {'session_id': session_id})
    factory = DeliveryTransactionFactory(uow)
    common = dict(actor_agent_id=agent, access=access, fresh_publications=fresh, remote_ready=remote)
    resolved = resolve_execution_intent(factory, request=request, one_shot_slot_id=slot_id, **common)
    if not resolved['can_submit']:
        raise OktoNexusError(ErrorCode.CONFLICT, 'One-shot runtime is not ready.', {'blockers': resolved['blockers']})
    submit_execution_operation(factory, request={k: resolved[k] for k in
        ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')}, **common)
    return resolved


def _settle(conn, slot, now):
    if not slot['call_id']:
        return
    call = capacity._row(conn, slot['call_id'])
    if call['outcome_json']:
        return
    result = conn.execute('SELECT r.* FROM runtime_results r WHERE operation_id=? AND canonical_server_id IS NOT NULL '
                          'ORDER BY captured_at DESC LIMIT 1', (slot['call_id'],)).fetchone()
    if result and result['delivery_outcome'] == 'success':
        capacity.finish(conn, call_id=slot['call_id'], outcome={'response': result['output_text']}, now=now)
        return
    failure = conn.execute("SELECT r.stage,r.error_code FROM execution_domain_deliveries d JOIN execution_receipts r "
        "USING(server_id,executor_id,operation_id) WHERE d.domain_operation_id=? AND r.stage IN ('FAILED','CANCELLED','OUTCOME_UNKNOWN') "
        'ORDER BY receipt_revision DESC LIMIT 1', (slot['call_id'],)).fetchone()
    refusal = conn.execute('SELECT x.last_error FROM execution_domain_deliveries d JOIN execution_dispatch_outbox x '
        "USING(server_id,executor_id,operation_id) WHERE d.domain_operation_id=? AND x.dispatch_state='RESOLVED_TERMINAL' "
        'AND x.last_error IS NOT NULL LIMIT 1', (slot['call_id'],)).fetchone()
    if failure or refusal or (result and result['delivery_outcome'] != 'success'):
        code = (failure['error_code'] or failure['stage']) if failure else 'ONE_SHOT_DISPATCH_FAILED'
        capacity.fail(conn, call_id=slot['call_id'], code=code, stage='execution' if call['started_at'] else 'opening',
            message='The one-shot call could not complete. Its execution details are retained in Nexus.', now=now,
            retry_safe=not call['started_at'], cancelled=bool(failure and failure['stage'] == 'CANCELLED'))


def tick(deps):
    """A bounded owner scan; no native I/O while holding a database transaction."""
    from ..bootstrap.execution_authority import build_execution_access
    from ..adapters.outbound.execution.core_inventory import protocol_info
    from .runtime_policy import effective
    from .execution_domain_delivery import admit_domain_delivery
    access = build_execution_access(deps)
    fresh, remote = deps.execution_fresh_publications, protocol_info()['remote_execution_ready']
    now = time.time()
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        bindings = {b['binding_id']: dict(b) for b in conn.execute('SELECT * FROM execution_bindings')}
        for slot_row in conn.execute('SELECT * FROM one_shot_slots ORDER BY last_checked_at,created_at LIMIT 256').fetchall():
            slot = dict(slot_row)
            conn.execute('SAVEPOINT one_shot_slot')
            try:
                _settle(conn, slot, now)
                # A cleanup admission failure must not roll back the final
                # outcome and turn a successful call into a later timeout.
                conn.execute('RELEASE one_shot_slot')
                conn.execute('SAVEPOINT one_shot_slot')
                current = conn.execute('SELECT * FROM one_shot_slots WHERE slot_id=?', (slot['slot_id'],)).fetchone()
                slot = dict(current)
                session = conn.execute('SELECT * FROM execution_sessions WHERE server_id=? AND executor_id=? AND session_id=?',
                    (slot['server_id'], slot['executor_id'], slot['session_id'])).fetchone() if slot['session_id'] else None
                if session and session['lifecycle_state'] == 'READY' and slot['state'] == 'STARTING':
                    capacity.ready(conn, slot_id=slot['slot_id'], session_id=slot['session_id'])
                # Reconciliation can prove a pre-open failure without a Core
                # receipt (FAILED/CLOSED). Its warm slot must not remain
                # STARTING forever. FAILED with a live lease still owns capacity.
                released = bool(session and session['lifecycle_state'] in ('CLOSED', 'FAILED')
                                and session['lease_state'] == 'CLOSED')
                opening = conn.execute('SELECT stage,possible_effect FROM execution_receipts WHERE server_id=? AND executor_id=? '
                    'AND operation_id=? ORDER BY receipt_revision DESC LIMIT 1',
                    (slot['server_id'], slot['executor_id'], slot['open_operation_id'])).fetchone()
                no_effect = bool(opening and opening['stage'] == 'FAILED' and not opening['possible_effect'])
                never_opened = (slot['state'] == 'CLOSING' and slot['session_id'] is None
                    and slot['open_operation_id'] is None and not conn.execute(
                        'SELECT 1 FROM execution_domain_deliveries WHERE domain_operation_id=?', (slot['call_id'],)).fetchone())
                if released or no_effect or never_opened:
                    if slot['call_id'] and capacity._row(conn, slot['call_id'])['outcome_json'] is None:
                        capacity.fail(conn, call_id=slot['call_id'], code='ONE_SHOT_SESSION_ENDED', stage='runtime',
                            message='The one-shot session ended before a final response was recorded.', now=now, retry_safe=no_effect)
                    elif not slot['call_id']:
                        capacity.warm_failed(conn, slot_id=slot['slot_id'], now=now)
                    conn.execute("UPDATE one_shot_slots SET state='CLOSING' WHERE slot_id=?", (slot['slot_id'],))
                    capacity.dispose_confirmed(conn, slot_id=slot['slot_id'], session_id=slot['session_id'])
                elif slot['state'] == 'CLOSING' and slot['session_id'] and session and session['lifecycle_state'] == 'READY':
                    closing = conn.execute('SELECT stage FROM execution_receipts WHERE server_id=? AND executor_id=? '
                        'AND operation_id=? ORDER BY receipt_revision DESC LIMIT 1',
                        (slot['server_id'], slot['executor_id'], slot['close_operation_id'])).fetchone()
                    if closing and closing[0] in ('FAILED', 'CANCELLED', 'OUTCOME_UNKNOWN'):
                        conn.execute('UPDATE one_shot_slots SET close_operation_id=NULL,next_cleanup_at=? WHERE slot_id=?',
                            (now + min(2 ** min(slot['close_attempts'], 8), 300), slot['slot_id']))
                    elif not slot['close_operation_id'] and slot['next_cleanup_at'] <= now:
                        closed = _admit(uow, access, fresh, remote, bindings[slot['binding_id']],
                            'one-shot-close:' + slot['slot_id'] + ':' + str(slot['close_attempts']), 'runtime.close', slot['session_id'])
                        conn.execute('UPDATE one_shot_slots SET close_operation_id=?,close_attempts=close_attempts+1 WHERE slot_id=?',
                                     (closed['operation_id'], slot['slot_id']))
            except OktoNexusError:
                conn.execute('ROLLBACK TO one_shot_slot')
            finally:
                conn.execute('RELEASE one_shot_slot')
                conn.execute('UPDATE one_shot_slots SET last_checked_at=? WHERE slot_id=?', (now, slot['slot_id']))
        hosts = {b['executor_id'] for b in bindings.values()} | {r[0] for r in conn.execute(
            "SELECT DISTINCT executor_id FROM one_shot_calls WHERE state IN ('QUEUED','ADMITTED','RUNNING')")}
        # Shutdown/reset owns containment. Keep settling outcomes above, but
        # never reserve replacement resources while admission is fenced.
        if deps.runtime_admission_fence.closed:
            return 0
        for host in hosts:
            capacity.expire_executions(conn, executor_id=host, now=now)
            capacity.advance_queue(conn, executor_id=host, host_limit=host_limit(conn, host), now=now)
        for row in conn.execute("SELECT call_id FROM one_shot_calls c WHERE state='ADMITTED' AND NOT EXISTS "
            '(SELECT 1 FROM execution_domain_deliveries d WHERE d.domain_operation_id=c.call_id) ORDER BY enqueued_at LIMIT 32').fetchall():
            conn.execute('SAVEPOINT one_shot_admission')
            try:
                admit_domain_delivery(uow, operation_id=row[0], access=access, fresh_publications=fresh, remote_ready=remote)
            except OktoNexusError:
                conn.execute('ROLLBACK TO one_shot_admission')
            finally:
                conn.execute('RELEASE one_shot_admission')
        for binding in bindings.values():
            agent = conn.execute('SELECT agent_id,enabled FROM agent_endpoints WHERE endpoint_id=?', (binding['endpoint_id'],)).fetchone()
            policy = effective(conn, agent['agent_id'])
            if policy['session_policy'] != 'one_shot' or not policy['runtime_enabled'] or not agent['enabled']:
                conn.execute("UPDATE one_shot_slots SET state='CLOSING' WHERE binding_id=? AND call_id IS NULL", (binding['binding_id'],))
                continue
            key = digest(conn, binding)
            capacity.retire_warm(conn, agent_id=agent['agent_id'], executor_id=binding['executor_id'],
                                 configuration_digest=key, binding_id=binding['binding_id'])
            capacity.trim_warm(conn, agent_id=agent['agent_id'], executor_id=binding['executor_id'])
            # Reserve the whole deficit in this pass. Native opens are independent
            # outbox effects, never awaited here or spread across maintenance ticks.
            for _ in range(256):
                slot_id = capacity.reserve_warm(conn, agent_id=agent['agent_id'], executor_id=binding['executor_id'],
                    configuration_digest=key, host_limit=host_limit(conn, binding['executor_id']), now=now)
                if slot_id is None:
                    break
            pending = conn.execute("SELECT slot_id FROM one_shot_slots WHERE agent_id=? AND executor_id=? "
                "AND configuration_digest=? AND state='STARTING' AND call_id IS NULL "
                "AND session_id IS NULL AND open_operation_id IS NULL ORDER BY created_at,slot_id LIMIT 256",
                (agent['agent_id'], binding['executor_id'], key)).fetchall()
            for pending_slot in pending:
                slot_id = pending_slot['slot_id']
                conn.execute('UPDATE one_shot_slots SET server_id=?,binding_id=? WHERE slot_id=?',
                             (binding['server_id'], binding['binding_id'], slot_id))
                conn.execute('SAVEPOINT one_shot_warm_open')
                try:
                    opened = _admit(uow, access, fresh, remote, binding, 'one-shot-warm:' + slot_id, 'runtime.start', slot_id=slot_id)
                    conn.execute('UPDATE one_shot_slots SET session_id=?,open_operation_id=? WHERE slot_id=?',
                                 (opened['session_id'], opened['operation_id'], slot_id))
                except OktoNexusError:
                    conn.execute('ROLLBACK TO one_shot_warm_open')
                    capacity.warm_failed(conn, slot_id=slot_id, now=now)
                    capacity.dispose_confirmed(conn, slot_id=slot_id, session_id=None)
                finally:
                    conn.execute('RELEASE one_shot_warm_open')
    return 0
