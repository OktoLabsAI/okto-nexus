"""Scoped durable session observations; a read never authorizes execution."""
from datetime import datetime, timezone
from contextlib import nullcontext
import json

from ..errors import ErrorCode, OktoNexusError


def agent_session_summary(deps, context, agent_id, workspace=None):
    """Read local and Connector history without depending on local realizations."""
    from ..bootstrap.execution_authority import build_execution_access
    access = build_execution_access(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        operator = access.authenticate(context, uow=uow, require_feature=False)
        if not operator and context.actor_agent_id != agent_id:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Session history is outside this identity.', {})
        if access.agents.get(uow, agent_id) is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Agent does not exist.', {})
        if operator and not context.actor_agent_id:
            from dataclasses import replace
            context = replace(context, actor_agent_id='operator')
        rows = uow.connection.execute(
            'SELECT s.server_id,s.executor_id,s.session_id,e.label,e.kind,ep.adapter_id '
            'FROM execution_sessions s JOIN execution_bindings b USING(server_id,executor_id,binding_id) '
            'JOIN execution_executors e USING(server_id,executor_id) '
            'JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id '
            'WHERE ep.agent_id=? AND (? IS NULL OR ep.workspace_id=?) '
            "ORDER BY (s.lifecycle_state NOT IN ('CLOSED','FAILED')) DESC,s.rowid DESC LIMIT 101",
            (agent_id, workspace, workspace)).fetchall()
        items = [read_execution_session(deps.connection_factory, server_id=r['server_id'],
            executor_id=r['executor_id'], session_id=r['session_id'], context=context, access=access, _uow=uow)
            | dict(host=r['label'] or ('Nexus server' if r['kind']=='embedded' else r['executor_id']), harness=r['adapter_id'])
            for r in rows[:100]]
        return dict(items=items, has_more=len(rows)>100)


def list_execution_sessions(factory, *, server_id, context, access, executor_id,
                            binding_id, agent_id, after_session_id="", limit=25):
    for value in (executor_id, binding_id, agent_id):
        if not isinstance(value, str) or not 1 <= len(value) <= 160 or not value.isprintable():
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid session list scope.", {})
    if (not isinstance(after_session_id, str) or len(after_session_id) > 160
            or (after_session_id and not after_session_id.isprintable())
            or type(limit) is not int or not 1 <= limit <= 100):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid session list cursor or limit.", {})
    with factory.unit_of_work(write=False) as uow:
        operator = access.authenticate(context, uow=uow, require_feature=False)
        rows = uow.connection.execute(
            "SELECT s.session_id FROM execution_sessions s JOIN execution_operations o "
            "ON o.server_id=s.server_id AND o.executor_id=s.executor_id "
            "AND o.operation_id=s.open_operation_id AND o.session_id=s.session_id "
            "WHERE s.server_id=? AND s.executor_id=? AND s.binding_id=? "
            "AND o.subject_agent_id=? AND (o.subject_agent_id=? OR o.actor_agent_id=? OR ?) "
            "AND s.session_id>? ORDER BY s.session_id LIMIT ?",
            (server_id, executor_id, binding_id, agent_id, context.actor_agent_id,
             context.actor_agent_id, operator, after_session_id, limit + 1)).fetchall()
        sessions = [read_execution_session(factory, server_id=server_id,
            session_id=row['session_id'], context=context, access=access,
            executor_id=executor_id, _uow=uow) for row in rows[:limit]]
        return dict(sessions=sessions, has_more=len(rows) > limit,
                    next_after_session_id=sessions[-1]['scope']['session_id'] if sessions else after_session_id)


def read_execution_session(factory, *, server_id, session_id, context, access,
                           executor_id=None, _uow=None):
    actor_agent_id = context.actor_agent_id
    for value in (session_id, actor_agent_id):
        if not isinstance(value, str) or not 1 <= len(value) <= 160:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid session query.", {})
    if executor_id is not None and (not isinstance(executor_id, str) or not 1 <= len(executor_id) <= 160):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid executor ID.", {})
    with nullcontext(_uow) if _uow is not None else factory.unit_of_work(write=False) as uow:
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
        from .execution_agent_recovery import agent_recovering
        available = bool(not agent_recovering(conn, server_id, row['executor_id'], row['subject_agent_id']) and not expired and lease and lease["status"] == "ACTIVE" and row["lease_state"] == "ACTIVE"
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
