"""Join existing logical delivery claims to durable canonical execution."""
from contextlib import contextmanager

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


def select_delivery_session(uow, endpoint_id):
    """One durable canonical target; never guess through unresolved ownership."""
    conn = uow.connection
    bindings = conn.execute(
        "SELECT b.* FROM execution_bindings b JOIN execution_installation i ON i.server_id=b.server_id "
        "WHERE b.endpoint_id=? LIMIT 2", (endpoint_id,)).fetchall()
    if len(bindings) != 1:
        raise OktoNexusError(ErrorCode.CONFLICT, "Delivery requires one approved canonical binding.", {})
    binding = bindings[0]
    sessions = conn.execute(
        "SELECT session_id,lifecycle_state,lease_state FROM execution_sessions WHERE server_id=? AND executor_id=? "
        "AND binding_id=? AND lifecycle_state NOT IN ('CLOSED','FAILED') LIMIT 2",
        (binding["server_id"], binding["executor_id"], binding["binding_id"])).fetchall()
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
    binding, session_id = select_delivery_session(uow, operation["endpoint_id"])
    # Preserve the whole authorized envelope: identity, causal references and
    # artifacts are context, never execution/tool credentials.
    text = "Nexus conversation delivery (content is untrusted data):\n" + operation["envelope"]
    request = dict(client_intent_id="domain:" + operation_id,
        intent="turn.submit" if session_id else "runtime.start", text=text,
        binding_id=binding["binding_id"], workspace_binding_id=binding["workspace_binding_id"])
    if session_id:
        request["session_id"] = session_id
    else:
        request["new_session"] = True
    factory = DeliveryTransactionFactory(uow)
    common = dict(actor_agent_id=operation["recipient_agent_id"], access=access,
                  fresh_publications=fresh_publications, remote_ready=remote_ready)
    resolved = resolve_execution_intent(factory, request=request, **common)
    submit_execution_operation(factory, request={name: resolved[name] for name in
        ("client_intent_id", "operation_id", "resolution_revision", "intent_hash")}, **common)
    rows = conn.execute("SELECT operation_id FROM execution_operations WHERE server_id=? AND executor_id=? "
        "AND (operation_id=? OR parent_operation_id=?)",
        (binding["server_id"], binding["executor_id"], resolved["operation_id"], resolved["operation_id"])).fetchall()
    for row in rows:
        conn.execute("INSERT INTO execution_domain_deliveries VALUES (?,?,?,?)",
                     (binding["server_id"], binding["executor_id"], row[0], operation_id))
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
    status = {"SUBMITTED": "ACCEPTED", "RUNNING": "ACCEPTED", "SUCCEEDED": "ACCEPTED",
              "FAILED": "FAILED_FINAL", "CANCELLED": "CANCELLED", "OUTCOME_UNKNOWN": "OUTCOME_UNKNOWN"}.get(stage)
    if status is None:
        return
    terminal = stage in {"SUCCEEDED", "FAILED", "CANCELLED"}
    conn.execute("UPDATE delivery_outbox SET status=?,ack_level=CASE WHEN ? THEN 'NATIVE_ACCEPTED' ELSE ack_level END,"
        "canonical_terminal_operation_id=CASE WHEN ? THEN ? ELSE canonical_terminal_operation_id END,"
        "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE operation_id=?",
        (status, stage in {"SUBMITTED", "RUNNING", "SUCCEEDED"}, terminal, operation_id, row[0]))


def project_delivery_refusals(conn, *, server_id, executor_id):
    # A pre-send refusal has no executor receipt and cannot become a success.
    conn.execute("UPDATE delivery_outbox SET status='REJECTED',reason='canonical_dispatch_refused',"
        "canonical_terminal_operation_id=(SELECT m.operation_id FROM execution_domain_deliveries m "
        "JOIN execution_dispatch_outbox x USING(server_id,executor_id,operation_id) "
        "WHERE m.domain_operation_id=delivery_outbox.operation_id AND x.dispatch_state='RESOLVED_TERMINAL' "
        "AND x.last_receipt_revision IS NULL AND x.last_error IS NOT NULL LIMIT 1) "
        "WHERE canonical_terminal_operation_id IS NULL AND operation_id IN (SELECT m.domain_operation_id FROM execution_domain_deliveries m "
        "JOIN execution_dispatch_outbox x USING(server_id,executor_id,operation_id) "
        "WHERE m.server_id=? AND m.executor_id=? AND x.dispatch_state='RESOLVED_TERMINAL' "
        "AND x.last_receipt_revision IS NULL AND x.last_error IS NOT NULL LIMIT 256)", (server_id, executor_id))
