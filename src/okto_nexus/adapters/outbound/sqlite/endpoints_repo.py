"""Runtime binding/profile persistence. Every method uses the caller's UoW."""
import json
import sqlite3

from ....errors import ErrorCode, OktoNexusError, db_error_from_exception


class SqliteEndpointRepo:
    def boot_binding(self, uow, endpoint_id):
        row = uow.connection.execute("SELECT * FROM runtime_boot_bindings WHERE endpoint_id=?", (endpoint_id,)).fetchone()
        return dict(row) if row else None

    def boot_candidates(self, uow):
        return [dict(r) for r in uow.connection.execute("SELECT b.*,e.agent_id,e.adapter_id,e.workspace_id,w.root_realpath "
            "FROM runtime_boot_bindings b JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id "
            "JOIN workspaces w ON w.workspace_id=e.workspace_id WHERE b.enabled=1 ORDER BY e.priority DESC,b.endpoint_id")]

    def boot_authorized(self, uow, *, context, endpoint, action, now):
        if action != "open" or context.endpoint_id != endpoint["endpoint_id"] or context.workspace_id != endpoint["workspace_id"]:
            return False
        if context.represented_agent_id != endpoint["agent_id"] or context.authentication_source != "runtime_boot":
            return False
        return uow.connection.execute("SELECT 1 FROM runtime_boot_bindings b JOIN agents a ON a.agent_id=b.issuer_agent_id "
            "JOIN runtime_dispatcher_owner o ON o.owner_key='dispatcher' JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id "
            "WHERE b.endpoint_id=? AND b.enabled=1 AND b.endpoint_revision=e.revision AND a.is_active=1 "
            "AND a.agent_id='operator' AND (b.issuer_credential_binding IS NULL OR b.issuer_credential_binding=a.api_key_hash) "
            "AND (e.profile_id IS NULL OR EXISTS (SELECT 1 FROM runtime_profiles p WHERE p.profile_id=e.profile_id "
            "AND p.revision=b.profile_revision AND p.enabled=1)) AND o.owner_id=? AND o.epoch=? AND o.lease_expires_at>?",
            (endpoint["endpoint_id"], context.runtime_owner_id, context.runtime_owner_epoch, now)).fetchone() is not None

    def configure_boot(self, uow, *, endpoint, profile, context, enabled, now):
        uow.connection.execute("INSERT INTO runtime_boot_bindings(endpoint_id,enabled,endpoint_revision,profile_revision,issuer_agent_id,issuer_credential_binding,updated_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(endpoint_id) DO UPDATE SET enabled=excluded.enabled,endpoint_revision=excluded.endpoint_revision,"
            "profile_revision=excluded.profile_revision,issuer_agent_id=excluded.issuer_agent_id,issuer_credential_binding=excluded.issuer_credential_binding,"
            "revision=runtime_boot_bindings.revision+1,updated_at=excluded.updated_at",
            (endpoint["endpoint_id"], int(enabled), endpoint["revision"], profile["revision"] if profile else None,
             context.actor_agent_id or "operator", context.credential_binding, now))

    def validate_start(self, uow, *, request_id, endpoint_id, now, mark_effects=False):
        from .runtime_requests_repo import SqliteRuntimeRequestRepo
        epoch = SqliteRuntimeRequestRepo().validate_start(uow, request_id=request_id, endpoint_id=endpoint_id, now=now)
        if mark_effects:
            uow.connection.execute("UPDATE runtime_open_requests SET effects_started=1 WHERE request_id=?", (request_id,))
        return epoch

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

    def public_profiles(self, uow):
        # Config paths, commands and secret reference names never enter discovery.
        items = []
        for row in uow.connection.execute("SELECT profile_id,adapter_id,enabled,inherit_ambient,revision,config FROM runtime_profiles ORDER BY profile_id"):
            item = dict(row)
            config = json.loads(item.pop("config"))
            item["config"] = {key: config[key] for key in (
                "provider", "model", "sandbox", "approval_policy", "required_native_requests") if key in config}
            item["enabled"], item["inherit_ambient"] = bool(item["enabled"]), bool(item["inherit_ambient"])
            items.append(item)
        return items

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

    def bind_session(self, uow, *, session_id, endpoint_id, workspace_id, presence_session_id, open_request_id=None, profile_revision=None):
        try:
            uow.connection.execute(
                "UPDATE harness_sessions SET endpoint_id=?,workspace_id=?,presence_session_id=?,open_request_id=?,runtime_profile_revision=?,lifecycle_state='protocol_ready' "
                "WHERE session_id=?",
                (endpoint_id, workspace_id, presence_session_id, open_request_id, profile_revision, session_id))
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

    def session_profile_revision(self, uow, session_id):
        row = uow.connection.execute("SELECT runtime_profile_revision FROM harness_sessions WHERE session_id=?", (session_id,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def _row(row):
        result = dict(row)
        result["public_config"] = json.loads(result["public_config"])
        return result
