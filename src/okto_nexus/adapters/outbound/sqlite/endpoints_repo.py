"""Runtime binding/profile persistence. Every method uses the caller's UoW."""
import json
import sqlite3

from ....errors import ErrorCode, OktoNexusError, db_error_from_exception


class SqliteEndpointRepo:
    def put_profile(self, uow, *, profile_id, adapter_id, config, secret_refs,
                    inherit_ambient, enabled, now):
        try:
            uow.connection.execute(
                "INSERT INTO runtime_profiles(profile_id,adapter_id,config,secret_refs,inherit_ambient,enabled,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (profile_id, adapter_id, json.dumps(config), json.dumps(secret_refs), int(inherit_ambient), int(enabled), now, now))
        except sqlite3.IntegrityError:
            raise OktoNexusError(ErrorCode.CONFLICT, "Runtime profile already exists or violates a constraint.", {}) from None

    def profile(self, uow, profile_id):
        row = uow.connection.execute("SELECT * FROM runtime_profiles WHERE profile_id=?", (profile_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["config"] = json.loads(result["config"])
        result["secret_refs"] = json.loads(result["secret_refs"])
        return result

    def create(self, uow, *, endpoint, now):
        try:
            uow.connection.execute(
                "INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,profile_id,enabled,"
                "activation_state,priority,selection_group,consumption,response_policy,public_config,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (endpoint.endpoint_id, endpoint.agent_id, endpoint.workspace_id, endpoint.adapter_id, endpoint.protocol,
                 endpoint.runtime_profile_id, int(endpoint.enabled), endpoint.activation_state, endpoint.priority,
                 endpoint.selection_group, endpoint.delivery_consumption, endpoint.response_policy,
                 json.dumps(endpoint.public_config), now, now))
        except sqlite3.IntegrityError:
            raise OktoNexusError(ErrorCode.CONFLICT, "Endpoint exists or violates a binding constraint.", {}) from None

    def get(self, uow, endpoint_id):
        row = uow.connection.execute("SELECT * FROM agent_endpoints WHERE endpoint_id=?", (endpoint_id,)).fetchone()
        return self._row(row) if row else None

    def list(self, uow, *, agent_id=None, workspace_id=None):
        query, values = "SELECT * FROM agent_endpoints WHERE 1=1", []
        if agent_id is not None:
            query += " AND agent_id=?"
            values.append(agent_id)
        if workspace_id is not None:
            query += " AND workspace_id=?"
            values.append(workspace_id)
        return [self._row(r) for r in uow.connection.execute(query + " ORDER BY priority DESC,endpoint_id", values)]

    def set_enabled(self, uow, *, endpoint_id, enabled, expected_revision, now):
        cur = uow.connection.execute(
            "UPDATE agent_endpoints SET enabled=?,revision=revision+1,updated_at=? WHERE endpoint_id=? AND revision=?",
            (int(enabled), now, endpoint_id, expected_revision))
        if cur.rowcount != 1:
            raise OktoNexusError(ErrorCode.CONFLICT, "Endpoint revision changed or endpoint is unavailable.", {})

    def bind_session(self, uow, *, session_id, endpoint_id, workspace_id, presence_session_id):
        try:
            uow.connection.execute(
                "UPDATE harness_sessions SET endpoint_id=?,workspace_id=?,presence_session_id=?,lifecycle_state='protocol_ready' "
                "WHERE session_id=?",
                (endpoint_id, workspace_id, presence_session_id, session_id))
        except sqlite3.Error as exc:
            raise db_error_from_exception("binding runtime session", exc) from exc

    def detach_session(self, uow, *, session_id):
        # This records loss of our connection, not an observed process exit.
        uow.connection.execute(
            "UPDATE harness_sessions SET lifecycle_state='detached' WHERE session_id=?",
            (session_id,))

    def legacy_diagnostics(self, uow):
        return [dict(row) for row in uow.connection.execute(
            "SELECT session_id,owning_agent_id,status FROM harness_sessions "
            "WHERE lifecycle_state='legacy_unlinked' ORDER BY session_id")]

    @staticmethod
    def _row(row):
        result = dict(row)
        result["public_config"] = json.loads(result["public_config"])
        return result
