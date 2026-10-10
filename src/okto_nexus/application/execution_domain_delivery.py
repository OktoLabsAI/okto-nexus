"""Join existing logical delivery claims to durable canonical execution."""
from contextlib import contextmanager
import json

from ..errors import ErrorCode, OktoNexusError
from .execution_intents import resolve_execution_intent
from .execution_admission import submit_execution_operation


class DeliveryTransactionFactory:
    """The message transaction owns commit and rollback of every admission row."""
    def __init__(self, uow):
        self.uow = uow

    @contextmanager
    def unit_of_work(self, write=True):
        yield self.uow


def select_delivery_session(uow, endpoint_id, *, sender_agent_id=None, source_session_key=''):
    """One durable canonical target; never guess through unresolved ownership."""
    conn = uow.connection
    bindings = conn.execute(
        "SELECT b.*,e.session_policy FROM execution_bindings b "
        "JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id "
        "JOIN execution_installation i ON i.server_id=b.server_id "
        "WHERE b.endpoint_id=? LIMIT 2", (endpoint_id,)).fetchall()
    if len(bindings) != 1:
        raise OktoNexusError(ErrorCode.CONFLICT, "Delivery requires one approved canonical binding.", {})
    binding = dict(bindings[0])
    from .runtime_policy import effective
    agent_id = conn.execute('SELECT agent_id FROM agent_endpoints WHERE endpoint_id=?', (endpoint_id,)).fetchone()[0]
    binding['session_policy'] = effective(conn, agent_id)['session_policy']
    if binding['session_policy'] == 'one_shot':
        return binding, None
    per_sender = binding["session_policy"] in {"per_sender", "per_sender_session"}
    if per_sender and not sender_agent_id:
        raise OktoNexusError(ErrorCode.CONFLICT, "Sender identity is required for an isolated session.", {})
    sessions = conn.execute(
        "SELECT s.session_id,s.lifecycle_state,s.lease_state FROM execution_sessions s "
        "LEFT JOIN execution_sender_sessions a USING(server_id,executor_id,session_id) "
        "WHERE s.server_id=? AND s.executor_id=? AND s.binding_id=? "
        "AND s.lifecycle_state NOT IN ('CLOSED','FAILED') AND s.lease_state<>'REVOKED' AND "
        + ("a.sender_agent_id=? AND a.isolation_policy=? AND a.source_session_key=?" if per_sender else "a.session_id IS NULL") + " LIMIT 2",
        (binding["server_id"], binding["executor_id"], binding["binding_id"])
        + ((sender_agent_id, binding['session_policy'],
            source_session_key if binding['session_policy'] == 'per_sender_session' else '') if per_sender else ())).fetchall()
    if len(sessions) > 1:
        raise OktoNexusError(ErrorCode.CONFLICT, "AMBIGUOUS_BINDING", {})
    if sessions and (sessions[0]["lifecycle_state"] != "READY" or sessions[0]["lease_state"] != "ACTIVE"):
        raise OktoNexusError(ErrorCode.CONFLICT, "Delivery session requires reconciliation.", {})
    return binding, sessions[0]["session_id"] if sessions else None


def admit_domain_delivery(uow, *, operation_id, access, fresh_publications, remote_ready):
    conn = uow.connection
    operation = conn.execute("SELECT * FROM delivery_outbox WHERE operation_id=?", (operation_id,)).fetchone()
    if operation is None:
        raise OktoNexusError(ErrorCode.NOT_FOUND, "The logical delivery is unavailable.", {})
    operation = dict(operation)
    validate = getattr(access, "validate_domain_delivery", None)
    if validate is None:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Delivery authorization is unavailable.", {})
    validate(uow, operation)
    prior = conn.execute("SELECT operation_id FROM execution_domain_deliveries WHERE domain_operation_id=?",
                         (operation_id,)).fetchall()
    if prior:
        return [row[0] for row in prior]
    sender = conn.execute("SELECT from_agent_id FROM messages WHERE message_id=?",
                          (operation["message_id"],)).fetchone()
    if sender is None:
        raise OktoNexusError(ErrorCode.CONFLICT, "The delivery sender is unavailable.", {})
    from .message_session_origin import for_message
    source_session_key = for_message(conn, operation['message_id'])
    binding, session_id = select_delivery_session(uow, operation["endpoint_id"], sender_agent_id=sender[0],
                                                   source_session_key=source_session_key)
    one_shot_slot = None
    if binding['session_policy'] == 'one_shot':
        from .one_shot_runtime import admit_call
        one_shot_slot = admit_call(uow, operation, binding, caller_id=sender[0])
        if one_shot_slot is None:
            return []
        session_id = one_shot_slot['session_id']
    # Preserve the whole authorized envelope: identity, causal references and
    # artifacts are context, never execution/tool credentials.
    from .runtime_bootstrap import delivery_prompt
    text = delivery_prompt(json.loads(operation["envelope"]))
    if operation.get('admission_binding'):
        endpoint = conn.execute('SELECT profile_id FROM agent_endpoints WHERE endpoint_id=?', (operation['endpoint_id'],)).fetchone()
        current = dict(schema_version=1, operation_id=operation_id, endpoint_id=operation['endpoint_id'],
            endpoint_revision=operation['endpoint_revision'], workspace_id=operation['workspace_id'],
            canonical_envelope_hash=operation['request_hash'],
            execution_profile=dict(profile_id=endpoint['profile_id'], revision=operation['profile_revision']))
        text += '\nNEXUS TRANSPORT BINDING: current server-owned attempt; the delivery context is its admission snapshot.\n' + json.dumps(current, sort_keys=True)
    attempt = max(1, operation['attempt_count'])
    request = dict(client_intent_id="domain:" + operation_id + (f":attempt:{attempt}" if attempt > 1 else ''),
        intent="turn.submit" if session_id else "runtime.start", text=text,
        binding_id=binding["binding_id"], workspace_binding_id=binding["workspace_binding_id"])
    if session_id:
        request["session_id"] = session_id
    else:
        request["new_session"] = True
    factory = DeliveryTransactionFactory(uow)
    common = dict(actor_agent_id=operation["recipient_agent_id"], access=access,
                  fresh_publications=fresh_publications, remote_ready=remote_ready)
    resolved = resolve_execution_intent(factory, request=request,
        one_shot_slot_id=one_shot_slot['slot_id'] if one_shot_slot else None, **common)
    if not resolved['can_submit']:
        blockers = resolved['blockers']
        message = 'Runtime delivery is unavailable: ' + ', '.join(blockers) + '.'
        if 'inventory_not_fresh' in blockers:
            message += ' The host must publish a fresh inventory.'
        if 'inventory_binding_review_required' in blockers:
            message += ' Automatic revalidation could not confirm the selected installation. Review this connection.'
        raise OktoNexusError(ErrorCode.CONFLICT, message, {'blockers': blockers})
    submit_execution_operation(factory, request={name: resolved[name] for name in
        ("client_intent_id", "operation_id", "resolution_revision", "intent_hash")}, **common)
    if one_shot_slot is not None and session_id is None:
        conn.execute('UPDATE one_shot_slots SET session_id=?,open_operation_id=? WHERE slot_id=?',
                     (resolved['session_id'], resolved['operation_id'], one_shot_slot['slot_id']))
    if session_id is None and binding["session_policy"] in {"per_sender", "per_sender_session"}:
        # The admission and affinity commit together under the message's write
        # transaction, including OPENING sessions; concurrent arrivals cannot
        # allocate another session for the same sender.
        conn.execute("INSERT INTO execution_sender_sessions VALUES (?,?,?,?,?,?)",
                     (binding["server_id"], binding["executor_id"], resolved["session_id"], sender[0],
                      binding['session_policy'], source_session_key if binding['session_policy'] == 'per_sender_session' else ''))
    rows = conn.execute("SELECT operation_id,action FROM execution_operations WHERE server_id=? AND executor_id=? "
        "AND (operation_id=? OR parent_operation_id=?)",
        (binding["server_id"], binding["executor_id"], resolved["operation_id"], resolved["operation_id"])).fetchall()
    for row in rows:
        conn.execute("INSERT INTO execution_domain_deliveries VALUES (?,?,?,?)",
                     (binding["server_id"], binding["executor_id"], row[0], operation_id))
    # The logical inbox delivery survives retries, while each canonical turn
    # has its own identity. Retain that identity from admission so the existing
    # immutable history records receipt transitions even on the first attempt.
    turn_id = next(row[0] for row in rows if row[1] == 'turn.submit')
    conn.execute('UPDATE delivery_outbox SET attempt_count=max(attempt_count,1),attempt_id=? WHERE operation_id=?',
                 (turn_id, operation_id))
    return [row[0] for row in rows]


def require_domain_delivery(uow, *, access, server_id, executor_id, operation_id):
    row = uow.connection.execute("SELECT d.* FROM execution_domain_deliveries m "
        "JOIN delivery_outbox d ON d.operation_id=m.domain_operation_id "
        "WHERE m.server_id=? AND m.executor_id=? AND m.operation_id=?",
        (server_id, executor_id, operation_id)).fetchone()
    if row is None:
        return
    validate = getattr(access, "validate_domain_delivery", None)
    if validate is None:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Delivery authorization is unavailable.", {})
    validate(uow, dict(row))


def project_delivery_receipt(conn, *, server_id, executor_id, operation_id, action, stage):
    if action != "turn.submit" and not (action == "runtime.open" and stage in {"FAILED", "CANCELLED", "OUTCOME_UNKNOWN"}):
        return
    row = conn.execute("SELECT domain_operation_id FROM execution_domain_deliveries "
        "WHERE server_id=? AND executor_id=? AND operation_id=?", (server_id, executor_id, operation_id)).fetchone()
    if row is None:
        return
    if conn.execute('SELECT 1 FROM execution_delivery_releases WHERE domain_operation_id=?', (row[0],)).fetchone():
        return
    status = {"SUBMITTED": "ACCEPTED", "RUNNING": "ACCEPTED", "SUCCEEDED": "ACCEPTED",
              "FAILED": "FAILED_FINAL", "CANCELLED": "CANCELLED", "OUTCOME_UNKNOWN": "OUTCOME_UNKNOWN"}.get(stage)
    if status is None:
        return
    if action == "turn.submit" and stage in {"SUBMITTED", "RUNNING", "SUCCEEDED"}:
        # This path runs only after accepting a correlated Core receipt. Opening
        # a runtime or writing to its transport does not prove message delivery.
        # Keep MCP-owned deliveries and the final read acknowledgement separate.
        conn.execute(
            "UPDATE message_deliveries SET delivered_at=COALESCE(delivered_at,"
            "strftime('%Y-%m-%dT%H:%M:%fZ','now')),"
            "status=CASE WHEN status='unread' THEN 'delivered' ELSE status END "
            "WHERE consumer_kind='push' AND consumer_operation_id=? "
            "AND status IN ('unread','delivered','read') AND EXISTS ("
            "SELECT 1 FROM delivery_outbox o WHERE o.operation_id=? "
            "AND o.reconciliation_id IS NULL AND o.delivery_id=message_deliveries.delivery_id "
            "AND o.message_id=message_deliveries.message_id "
            "AND o.recipient_agent_id=message_deliveries.recipient_agent_id)",
            (row[0], row[0]))
    terminal = stage in {"SUCCEEDED", "FAILED", "CANCELLED"}
    conn.execute("UPDATE delivery_outbox SET status=?,ack_level=CASE WHEN ? THEN 'NATIVE_ACCEPTED' ELSE ack_level END,"
        "canonical_terminal_operation_id=CASE WHEN ? THEN ? ELSE canonical_terminal_operation_id END,"
        "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE operation_id=?",
        (status, stage in {"SUBMITTED", "RUNNING", "SUCCEEDED"}, terminal, operation_id, row[0]))
    if action == 'turn.submit' and stage == 'FAILED':
        from .execution_delivery_retry import mark_retry_wait
        mark_retry_wait(conn, row[0])


def project_delivery_refusals(conn, *, server_id, executor_id):
    # A pre-send refusal has no executor receipt and cannot become a success.
    conn.execute("UPDATE delivery_outbox SET status='REJECTED',reason='canonical_dispatch_refused',"
        "canonical_terminal_operation_id=(SELECT m.operation_id FROM execution_domain_deliveries m "
        "JOIN execution_dispatch_outbox x USING(server_id,executor_id,operation_id) "
        "WHERE m.domain_operation_id=delivery_outbox.operation_id AND x.dispatch_state='RESOLVED_TERMINAL' "
        "AND x.last_receipt_revision IS NULL AND x.last_error IS NOT NULL LIMIT 1) "
        "WHERE reconciliation_id IS NULL AND canonical_terminal_operation_id IS NULL AND operation_id IN (SELECT m.domain_operation_id FROM execution_domain_deliveries m "
        "JOIN execution_dispatch_outbox x USING(server_id,executor_id,operation_id) "
        "WHERE m.server_id=? AND m.executor_id=? AND x.dispatch_state='RESOLVED_TERMINAL' "
        "AND x.last_receipt_revision IS NULL AND x.last_error IS NOT NULL LIMIT 256)", (server_id, executor_id))


def project_released_deliveries(conn, *, server_id, executor_id, session_id, proof):
    """Called only after validating resource release AND complete event replay.

    Release ordering, not the inbox claim: an already submitted turn may have
    caused effects. Never replay it, fabricate a receipt or publish partial text
    as a completed response.
    """
    if not conn.execute("SELECT 1 FROM execution_sessions WHERE server_id=? AND executor_id=? "
            "AND session_id=? AND lifecycle_state='CLOSED' AND lease_state='CLOSED'",
            (server_id, executor_id, session_id)).fetchone():
        raise ValueError('Delivery release requires a closed canonical session.')
    rows = conn.execute("SELECT m.domain_operation_id,p.operation_id FROM execution_operations p "
        "JOIN execution_domain_deliveries m USING(server_id,executor_id,operation_id) "
        "JOIN delivery_outbox d ON d.operation_id=m.domain_operation_id "
        "WHERE p.server_id=? AND p.executor_id=? AND p.session_id=? AND p.action='turn.submit' "
        "AND d.reconciliation_id IS NULL AND d.external_completed_at IS NULL "
        "AND d.terminal_event_id IS NULL AND d.canonical_terminal_operation_id IS NULL "
        "AND d.status IN ('PENDING','CLAIMED','SENDING','ACCEPTED','SENT_UNCONFIRMED','OUTCOME_UNKNOWN') "
        "AND (SELECT stage FROM execution_receipts r WHERE r.server_id=p.server_id "
        "AND r.executor_id=p.executor_id AND r.operation_id=p.operation_id "
        "ORDER BY receipt_revision DESC LIMIT 1) IN ('SUBMISSION_STARTED','SUBMITTED','RUNNING','OUTCOME_UNKNOWN')",
        (server_id, executor_id, session_id)).fetchall()
    for row in rows:
        conn.execute("INSERT INTO execution_delivery_releases VALUES(?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) "
            "ON CONFLICT DO NOTHING", (row['domain_operation_id'], server_id, executor_id,
            row['operation_id'], session_id, json.dumps(proof, sort_keys=True)))
        conn.execute("UPDATE delivery_outbox SET status='OUTCOME_UNKNOWN',reason='session_released_without_result',"
            "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE operation_id=? "
            "AND (status!='OUTCOME_UNKNOWN' OR reason IS NOT 'session_released_without_result')",
            (row['domain_operation_id'],))
