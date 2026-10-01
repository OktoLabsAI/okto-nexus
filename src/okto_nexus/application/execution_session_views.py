"""Scoped durable session observations; a read never authorizes execution."""
from datetime import datetime, timezone
import json

from ..errors import ErrorCode, OktoNexusError


def read_execution_session(factory, *, server_id, session_id, context, access,
                           executor_id=None):
    actor_agent_id = context.actor_agent_id
    for value in (session_id, actor_agent_id):
        if not isinstance(value, str) or not 1 <= len(value) <= 160:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid session query.", {})
    if executor_id is not None and (not isinstance(executor_id, str) or not 1 <= len(executor_id) <= 160):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid executor ID.", {})
    with factory.unit_of_work(write=False) as uow:
        operator = access.authenticate(context, uow=uow, require_feature=False)
        conn = uow.connection
        rows = conn.execute(
            "SELECT s.*,o.expected_revisions_json,o.created_at,o.subject_agent_id,"
            "e.control_state,e.generation,e.revoked_at FROM execution_sessions s "
            "JOIN execution_operations o ON o.server_id=s.server_id AND o.executor_id=s.executor_id "
            "AND o.operation_id=s.open_operation_id AND o.session_id=s.session_id "
            "JOIN execution_executors e ON e.server_id=s.server_id AND e.executor_id=s.executor_id "
            "WHERE s.server_id=? AND s.session_id=? "
            "AND (o.subject_agent_id=? OR o.actor_agent_id=? OR ?) "
            "AND (? IS NULL OR s.executor_id=?) LIMIT 2",
            (server_id, session_id, actor_agent_id, actor_agent_id, operator, executor_id, executor_id)).fetchall()
        if not rows:
            raise OktoNexusError(ErrorCode.NOT_FOUND, "The session was not found in this scope.", {})
        if len(rows) != 1:
            raise OktoNexusError(ErrorCode.CONFLICT, "The session ID is ambiguous; specify executor_id.", {})
        row = rows[0]
        stored = json.loads(row["expected_revisions_json"])
        scope = {name: stored[name] for name in (
            "server_id", "executor_id", "binding_id", "agent_id", "workspace_id",
            "workspace_binding_id", "session_id", "session_owner_generation",
            "authorization_revision", "configuration_revision", "binding_revision", "credential_epoch")}
        scope["session_owner_generation"] = row["owner_generation"]
        lease = conn.execute(
            "SELECT * FROM execution_leases WHERE server_id=? AND executor_id=? AND session_id=? "
            "ORDER BY lease_serial DESC LIMIT 1", (server_id, row["executor_id"], session_id)).fetchone()
        observed = conn.execute(
            "SELECT MAX(r.received_at) FROM execution_receipts r JOIN execution_operations o "
            "ON o.server_id=r.server_id AND o.executor_id=r.executor_id AND o.operation_id=r.operation_id "
            "WHERE o.server_id=? AND o.executor_id=? AND o.session_id=?",
            (server_id, row["executor_id"], session_id)).fetchone()[0]
        closing = conn.execute(
            "SELECT 1 FROM execution_operations WHERE server_id=? AND executor_id=? "
            "AND session_id=? AND action='runtime.close' AND admission_state='ACCEPTED' LIMIT 1",
            (server_id, row["executor_id"], session_id)).fetchone()
        expired = bool(lease and lease["status"] == "ACTIVE" and
            datetime.fromisoformat(lease["valid_until_server"].replace("Z", "+00:00")) <= datetime.now(timezone.utc))
        available = bool(not expired and lease and lease["status"] == "ACTIVE" and row["lease_state"] == "ACTIVE"
            and row["lifecycle_state"] == "READY" and row["control_state"] == "CONTROL_READY"
            and row["revoked_at"] is None and lease["owner_generation"] == row["owner_generation"]
            and lease["connection_generation"] == row["generation"])
        # Process handles and proofs are executor-local. Lifecycle/lease facts do
        # not establish process exit (especially for attached runtimes).
        return dict(scope=scope, connection_generation=row["generation"],
            lifecycle_state=row["lifecycle_state"], process_state="UNKNOWN", ownership="UNKNOWN",
            lease_state="EXPIRED" if expired and row["lease_state"] == "ACTIVE" else row["lease_state"],
            durable_release_pending=bool(closing and row["lifecycle_state"] != "CLOSED"),
            control_available=available, last_observed_at=observed)
