"""Scoped delegation and opaque access audit; no external I/O."""
import json


class SqliteRuntimeGrantRepo:
    def insert(self, uow, *, grant):
        values = dict(grant)
        values["actions"] = json.dumps(sorted(values["actions"]))
        columns = tuple(values)
        uow.connection.execute(
            f"INSERT INTO runtime_execution_grants({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
            tuple(values.values()))

    def candidates(self, uow, *, actor_id):
        return [dict(row) | {"actions": json.loads(row["actions"])} for row in uow.connection.execute(
            "SELECT * FROM runtime_execution_grants WHERE actor_agent_id=? AND revoked_at IS NULL ORDER BY grant_id",
            (actor_id,))]

    def revoke(self, uow, *, grant_id, now):
        uow.connection.execute(
            "UPDATE runtime_execution_grants SET revoked_at=?,revision=revision+1 WHERE grant_id=? AND revoked_at IS NULL",
            (now, grant_id))

    def consume(self, uow, *, grant_id):
        # Called under the same IMMEDIATE transaction as policy evaluation.
        uow.connection.execute("UPDATE runtime_execution_grants SET used_executions=used_executions+1 WHERE grant_id=?",
                               (grant_id,))

    def audit(self, uow, *, context, action, endpoint_id, session_id, grant, allowed, now):
        uow.connection.execute(
            "INSERT INTO runtime_access_audit(request_id,actor_agent_id,action,endpoint_id,session_id,grant_id,grant_revision,decision,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)", (context.request_id, context.actor_agent_id, action, endpoint_id, session_id,
                grant["grant_id"] if grant else None, grant["revision"] if grant else None,
                "allow" if allowed else "deny", now))

    def runtime_endpoint(self, uow, session_id):
        row = uow.connection.execute("SELECT endpoint_id FROM harness_sessions WHERE session_id=?", (session_id,)).fetchone()
        return row[0] if row else None
