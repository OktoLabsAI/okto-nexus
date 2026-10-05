"""Canonical endpoint/profile use cases. No subprocess or secret I/O in UoWs."""
from pathlib import Path
import hashlib
import json

from ..domain.base import new_id, check_inline_size
from ..domain.endpoints import AgentEndpoint
from ..domain.ids import resolve_realpath, resolve_workspace_id
from ..domain.messages import validate_target, parse_target, serialize_target
from ..domain.inbox import assert_deliverable_message_target
from ..errors import ErrorCode, OktoNexusError
from .runtime_authorization import authorize_runtime, require_runtime_agent
from .runtime_requirements import validate_native_requirements


class EndpointService:
    def __init__(self, *, connection_factory, agents, workspaces, repo, registry, config, clock, access=None):
        self.cf, self.agents, self.workspaces, self.repo = connection_factory, agents, workspaces, repo
        self.registry, self.config, self.clock = registry, config, clock
        self.access = access

    def authorize(self, context):
        if self.access:
            return self.access.authorize(context)
        authorize_runtime(context, config=self.config, agents=self.agents, connection_factory=self.cf)

    @staticmethod
    def validate_public_config(descriptor, response_policy, public_config):
        if public_config is not None and not isinstance(public_config, dict):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Public configuration must be an object.", {})
        public_config = dict(public_config or {})
        check_inline_size("endpoint public configuration", public_config, 65536)
        allowed = {"relay_results", "notify_target", "nexus_tool_permission", "harness_settings"} | ({"target_pid", "nexus_work_session_id"} if descriptor.substrate == "attach" else set())
        if set(public_config) - allowed:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported public endpoint configuration.", {})
        if public_config.get("nexus_tool_permission", "ask") not in ("ask", "always_allow"):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid Nexus tool permission.", {})
        if 'harness_settings' in public_config:
            from nexus_connector_core import validate_harness_settings, CoreError
            settings = public_config['harness_settings']
            if not isinstance(settings, dict):
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Harness settings must be an object.', {})
            settings = dict(settings)
            model = settings.pop('model', None)
            if model is not None and (not isinstance(model, str) or not 1 <= len(model) <= 200 or any(ord(c)<32 for c in model)):
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid model identifier.', {})
            try:
                validate_harness_settings({'codex':'codex_app_server', 'claude_code':'claude_stream', 'pi':'pi_rpc'}.get(descriptor.kind), settings)
            except CoreError as exc:
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Unsupported harness setting or value.', {}) from exc
        if "relay_results" in public_config and type(public_config["relay_results"]) is not bool:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "relay_results must be a boolean.", {})
        if public_config.get("relay_results") and (response_policy != "conversation" or not descriptor.capabilities.correlated_results):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Result relay requires conversation policy and correlated results.", {})
        target = public_config.get("notify_target")
        if target is None:
            public_config.pop("notify_target", None)  # Removal restores the private reply target.
        else:
            if not isinstance(target, dict):
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "notify_target must be an explicit target object or null.", {})
            validate_target(target)
            assert_deliverable_message_target(target)
            public_config["notify_target"] = parse_target(serialize_target(target))
        if descriptor.substrate == "attach" and (type(public_config.get("target_pid")) is not int or public_config["target_pid"] <= 0):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Attach endpoint requires an explicitly selected process ID.", {})
        work_session = public_config.get("nexus_work_session_id")
        if work_session is None:
            public_config.pop("nexus_work_session_id", None)
        elif not isinstance(work_session, str) or not 1 <= len(work_session) <= 128 or work_session != work_session.strip():
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "nexus_work_session_id must be a session identifier or null.", {})
        return public_config

    @staticmethod
    def validate_work_session_reference(uow, *, public_config, agent_id, workspace_id):
        """Approve a reference, never authentication or a native capability.

        Recheck inside the configuration writer transaction. A harness-owned
        presence record cannot stand in for a separately authenticated Nexus
        client. The secret remains in the canonical sessions repository only.
        Actual work must additionally prove possession and bind the claim.
        """
        session_id = public_config.get("nexus_work_session_id")
        if session_id is None:
            return
        valid = uow.connection.execute(
            "SELECT 1 FROM sessions s WHERE s.session_id=? AND s.agent_id=? AND s.workspace_id=? "
            "AND s.status='active' AND s.closed_at IS NULL AND s.session_secret IS NOT NULL "
            "AND length(s.session_secret)>0 AND NOT EXISTS "
            "(SELECT 1 FROM harness_sessions h WHERE h.presence_session_id=s.session_id)",
            (session_id, agent_id, workspace_id)).fetchone()
        if not valid:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "External Nexus work session is not available for this endpoint.", {})

    def connection_summary(self, context, *, endpoint_id):
        """Public connection identity for reviewing an existing configuration."""
        self.authorize(context)
        with self.cf.unit_of_work(write=False) as uow:
            if self.access:
                self.access.authorize(context, uow=uow, audit=False)
            endpoint = self.repo.get(uow, endpoint_id)
            if not endpoint or endpoint['protocol'] != 'nxl-r4':
                raise OktoNexusError(ErrorCode.NOT_FOUND, 'The canonical connection is unavailable.', {})
            return {'endpoint_id': endpoint_id, 'agent_id': endpoint['agent_id'],
                    'workspace_id': endpoint['workspace_id'],
                    'connection_name': endpoint['public_config'].get('alias', '')}

    def harness_settings(self, context, *, endpoint_id, changes=None):
        """Revisioned native launch settings, independent of Nexus tool policy."""
        from nexus_connector_core import validate_harness_configuration, CoreError
        from .execution_harness_configuration import read_harness_configuration
        self.authorize(context)
        if changes is not None and (not isinstance(changes, dict) or
                set(changes) != {'expected_revision', 'settings'} or
                type(changes['expected_revision']) is not int or not isinstance(changes['settings'], dict)):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Expected revision and settings object.', {})
        with self.cf.unit_of_work(write=changes is not None) as uow:
            if self.access:
                self.access.authorize(context, uow=uow, audit=False)
            endpoint = self.repo.get(uow, endpoint_id)
            if not endpoint or endpoint['protocol'] != 'nxl-r4':
                raise OktoNexusError(ErrorCode.NOT_FOUND, 'The canonical connection is unavailable.', {})
            config = dict(endpoint['public_config'])
            settings = config.get('harness_settings', {})
            schema = read_harness_configuration(uow.connection, endpoint_id=endpoint_id,
                                               adapter_id=endpoint['adapter_id'])
            if changes is not None:
                if changes['expected_revision'] != endpoint['revision']:
                    raise OktoNexusError(ErrorCode.CONFLICT, 'Connection changed. Reload its settings.', {})
                try:
                    validate_harness_configuration(schema, changes['settings'])
                except CoreError as exc:
                    raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Unsupported harness setting or value.', {}) from exc
                if changes['settings'] != settings:
                    if uow.connection.execute("SELECT 1 FROM execution_sessions s JOIN execution_bindings b "
                            "USING(server_id,executor_id,binding_id) WHERE b.endpoint_id=? "
                            "AND s.lifecycle_state NOT IN ('CLOSED','FAILED') LIMIT 1", (endpoint_id,)).fetchone():
                        raise OktoNexusError(ErrorCode.CONFLICT, 'Close existing runtime sessions before changing harness settings.', {})
                    settings = dict(changes['settings'])
                    config['harness_settings'] = settings
                    now = self.clock.now_iso()
                    uow.connection.execute('UPDATE agent_endpoints SET public_config=?,revision=revision+1,updated_at=? WHERE endpoint_id=?',
                        (json.dumps(config), now, endpoint_id))
                    self.repo.invalidate_configuration(uow, endpoint_ids=[endpoint_id], now=now)
                    self.repo.audit_configuration(uow, context=context, kind='endpoint', resource_id=endpoint_id,
                        old_revision=endpoint['revision'], new_revision=endpoint['revision']+1,
                        fields=['harness_settings'], now=now)
                    endpoint = self.repo.get(uow, endpoint_id)
            return dict(endpoint_id=endpoint_id, adapter_id=endpoint['adapter_id'], revision=endpoint['revision'], settings=settings,
                        configuration=schema)

    def tool_permission(self, context, *, endpoint_id, changes=None):
        """Operator policy for the generated Nexus client, applied at session start."""
        self.authorize(context)
        if changes is not None and (not isinstance(changes, dict)
                or set(changes) != {"expected_revision", "mode"}
                or type(changes["expected_revision"]) is not int
                or changes["mode"] not in ("ask", "always_allow")):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Use expected_revision and ask or always_allow mode.", {})
        with self.cf.unit_of_work(write=changes is not None) as uow:
            if self.access:
                self.access.authorize(context, uow=uow, audit=False)
            endpoint = self.repo.get(uow, endpoint_id)
            if not endpoint or endpoint["protocol"] != "nxl-r4":
                raise OktoNexusError(ErrorCode.NOT_FOUND, "The canonical connection is unavailable.", {})
            config = dict(endpoint["public_config"])
            mode = config.get("nexus_tool_permission", "ask")
            if changes is not None:
                if changes["expected_revision"] != endpoint["revision"]:
                    raise OktoNexusError(ErrorCode.CONFLICT, "Connection changed. Reload its tool permission.", {})
                if changes["mode"] != mode:
                    if uow.connection.execute("SELECT 1 FROM execution_sessions s JOIN execution_bindings b "
                            "USING(server_id,executor_id,binding_id) WHERE b.endpoint_id=? "
                            "AND s.lifecycle_state NOT IN ('CLOSED','FAILED') LIMIT 1", (endpoint_id,)).fetchone():
                        raise OktoNexusError(ErrorCode.CONFLICT, "Close existing runtime sessions before changing Nexus tool permission.", {})
                    mode = changes["mode"]
                    config["nexus_tool_permission"] = mode
                    now = self.clock.now_iso()
                    uow.connection.execute("UPDATE agent_endpoints SET public_config=?,revision=revision+1,updated_at=? WHERE endpoint_id=?",
                        (json.dumps(config), now, endpoint_id))
                    self.repo.invalidate_configuration(uow, endpoint_ids=[endpoint_id], now=now)
                    self.repo.audit_configuration(uow, context=context, kind="endpoint", resource_id=endpoint_id,
                        old_revision=endpoint["revision"], new_revision=endpoint["revision"]+1,
                        fields=["nexus_tool_permission"], now=now)
                    endpoint = self.repo.get(uow, endpoint_id)
            return {"endpoint_id": endpoint_id, "agent_id": endpoint["agent_id"], "revision": endpoint["revision"], "mode": mode}

    def conversation_policy(self, context, *, endpoint_id, changes=None):
        """Operator opt-in for canonical conversational delivery; never launch.

        This narrow operation preserves executor-owned configuration and aliases.
        Editing it invalidates existing grants just like other endpoint edits.
        """
        self.authorize(context)
        if isinstance(changes, dict) and changes.get('enabled') is False:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                'Active runtime connections always receive messages. Select MCP only to disable runtime delivery.', {})
        if changes is not None and (not isinstance(changes, dict)
                or not {"expected_revision", "enabled"} <= set(changes)
                or set(changes) - {"expected_revision", "enabled", "session_policy"}
                or type(changes["expected_revision"]) is not int or changes["expected_revision"] < 1
                or type(changes["enabled"]) is not bool
                or "session_policy" in changes and changes["session_policy"] not in ("shared", "per_sender", "per_sender_session")):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                "Use a positive expected_revision, boolean enabled and shared, per_sender or per_sender_session session_policy.", {})
        with self.cf.unit_of_work(write=changes is not None) as uow:
            if self.access:
                self.access.authorize(context, uow=uow, audit=False)
            endpoint = self.repo.get(uow, endpoint_id)
            if not endpoint or endpoint["protocol"] != "nxl-r4":
                raise OktoNexusError(ErrorCode.NOT_FOUND, "The canonical connection is unavailable.", {})
            from .runtime_policy import effective, set_legacy_session_override
            endpoint['session_policy'] = effective(uow.connection, endpoint['agent_id'])['session_policy']
            if changes is not None:
                if endpoint["revision"] != changes["expected_revision"]:
                    raise OktoNexusError(ErrorCode.CONFLICT, "Connection changed. Reload its message policy.", {})
                if changes["enabled"]:
                    from nexus_connector_core import get_runtime_catalog
                    descriptor = next((item for item in get_runtime_catalog().runtimes
                                       if item.adapter_id == endpoint["adapter_id"]), None)
                    if (not descriptor or descriptor.connection_mode != "managed"
                            or not endpoint["enabled"] or endpoint["activation_state"] != "approved"
                            or endpoint["health"] == "quarantined"):
                        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Approve an available managed connection first.", {})
                response_policy = "conversation" if changes["enabled"] else "explicit"
                session_policy = changes.get("session_policy", endpoint["session_policy"])
                if "session_policy" in changes:
                    set_legacy_session_override(uow, agent_id=endpoint['agent_id'], mode=session_policy,
                                                access=self.access, now=self.clock.now_iso())
                if session_policy != endpoint["session_policy"] and uow.connection.execute(
                        "SELECT 1 FROM execution_sessions s JOIN execution_bindings b "
                        "USING(server_id,executor_id,binding_id) WHERE b.endpoint_id=? "
                        "AND s.lifecycle_state NOT IN ('CLOSED','FAILED') LIMIT 1", (endpoint_id,)).fetchone():
                    raise OktoNexusError(ErrorCode.CONFLICT,
                        "Close existing sessions before changing session isolation.", {})
                if (endpoint["response_policy"] != response_policy or endpoint["consumption"] != "exclusive"
                        or session_policy != endpoint["session_policy"]):
                    now = self.clock.now_iso()
                    uow.connection.execute("UPDATE agent_endpoints SET response_policy=?,session_policy=?,consumption='exclusive',"
                        "revision=revision+1,updated_at=? WHERE endpoint_id=? AND revision=?",
                        (response_policy, session_policy, now, endpoint_id, endpoint["revision"]))
                    self.repo.invalidate_configuration(uow, endpoint_ids=[endpoint_id], now=now)
                    self.repo.audit_configuration(uow, context=context, kind="endpoint", resource_id=endpoint_id,
                        old_revision=endpoint["revision"], new_revision=endpoint["revision"] + 1,
                        fields=["response_policy", "consumption", "session_policy"], now=now)
                    endpoint = self.repo.get(uow, endpoint_id)
            return {"endpoint_id": endpoint_id, "agent_id": endpoint["agent_id"],
                    "workspace_id": endpoint["workspace_id"], "revision": endpoint["revision"],
                    "enabled": endpoint["response_policy"] == "conversation" and endpoint["consumption"] == "exclusive",
                    "session_policy": effective(uow.connection, endpoint['agent_id'])['session_policy']}

    def update_endpoint(self, context, *, endpoint_id, expected_revision, **changes):
        self.authorize(context)
        allowed = {"public_config", "enabled", "priority", "selection_group", "response_policy", "consumption", "profile_id"}
        if type(expected_revision) is not int or expected_revision < 1 or not changes or set(changes) - allowed:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Endpoint update requires a positive revision and mutable configuration fields.", {})
        with self.cf.unit_of_work() as uow:
            endpoint = self.repo.get(uow, endpoint_id)
            if not endpoint or endpoint["revision"] != expected_revision:
                raise OktoNexusError(ErrorCode.CONFLICT, "Endpoint revision changed.", {})
            if endpoint["protocol"] != "nxl-r4":
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Legacy connection configuration was removed.", {})
            # Retiring a canonical connection must not look it up in the legacy
            # adapter registry. This does not claim its native process exited.
            if changes == {"enabled": False} and type(changes["enabled"]) is bool:
                now = self.clock.now_iso()
                uow.connection.execute('UPDATE agent_endpoints SET enabled=0,revision=revision+1,updated_at=? '
                    'WHERE endpoint_id=? AND revision=?', (now, endpoint_id, expected_revision))
                self.repo.invalidate_configuration(uow, endpoint_ids=[endpoint_id], now=now)
                self.repo.audit_configuration(uow, context=context, kind='endpoint', resource_id=endpoint_id,
                    old_revision=expected_revision, new_revision=expected_revision+1, fields=changes, now=now)
                return {**endpoint, 'enabled': False, 'revision': expected_revision+1}
            updated = endpoint | changes
            if updated['response_policy'] != 'conversation' or updated['consumption'] != 'exclusive':
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                    'Active runtime connections require automatic message delivery. Select MCP only to disable it.', {})
            if (type(updated["enabled"]) not in {bool, int} or updated["enabled"] not in (0, 1)
                    or "enabled" in changes and type(changes["enabled"]) is not bool
                    or type(updated["priority"]) is not int
                    or updated["selection_group"] is not None and (not isinstance(updated["selection_group"], str) or not 1 <= len(updated["selection_group"]) <= 128)
                    or updated["profile_id"] is not None and (not isinstance(updated["profile_id"], str) or not 1 <= len(updated["profile_id"]) <= 128)
                    or not isinstance(updated["public_config"], dict)):
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid endpoint configuration field.", {})
            descriptor = self.registry.get(endpoint["adapter_id"])
            config = self.validate_public_config(descriptor, updated["response_policy"], updated["public_config"])
            if config.get('harness_settings', {}) != endpoint['public_config'].get('harness_settings', {}):
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Use the harness settings operation to change native configuration.', {})
            if config.get("nexus_tool_permission", "ask") != endpoint["public_config"].get("nexus_tool_permission", "ask"):
                if uow.connection.execute("SELECT 1 FROM execution_sessions s JOIN execution_bindings b "
                        "USING(server_id,executor_id,binding_id) WHERE b.endpoint_id=? "
                        "AND s.lifecycle_state NOT IN ('CLOSED','FAILED') LIMIT 1", (endpoint_id,)).fetchone():
                    raise OktoNexusError(ErrorCode.CONFLICT, "Close existing runtime sessions before changing Nexus tool permission.", {})
            if "public_config" in changes or changes.get("enabled") is True:
                self.validate_work_session_reference(uow, public_config=config,
                    agent_id=endpoint["agent_id"], workspace_id=endpoint["workspace_id"])
            AgentEndpoint(endpoint_id, endpoint["agent_id"], endpoint["adapter_id"], endpoint["workspace_id"], endpoint["protocol"],
                response_policy=updated["response_policy"], delivery_consumption=updated["consumption"])
            if updated["consumption"] == "mirror_only" and not descriptor.capabilities.context_without_execution:
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Adapter cannot mirror without starting execution.", {})
            if changes.get("enabled") and endpoint["health"] == "quarantined":
                raise OktoNexusError(ErrorCode.CONFLICT, "Reconcile the quarantined endpoint before enabling it.", {})
            if updated["profile_id"] != endpoint["profile_id"]:
                if (uow.connection.execute("SELECT 1 FROM harness_sessions WHERE endpoint_id=? AND lifecycle_state NOT IN ('stopped','detached')", (endpoint_id,)).fetchone()
                        or uow.connection.execute("SELECT 1 FROM runtime_open_requests WHERE endpoint_id=? AND status='RESERVED'", (endpoint_id,)).fetchone()):
                    raise OktoNexusError(ErrorCode.CONFLICT, "Close the current runtime and finish pending starts before changing its profile.", {})
                profile = self.repo.profile(uow, updated["profile_id"]) if updated["profile_id"] else None
                if descriptor.substrate == "attach" and updated["profile_id"]:
                    raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Attach cannot acquire a process profile.", {})
                if descriptor.substrate != "attach" and (not profile or not profile["enabled"] or profile["adapter_id"] != endpoint["adapter_id"]):
                    raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Select an enabled compatible runtime profile.", {})
            now = self.clock.now_iso()
            uow.connection.execute("UPDATE agent_endpoints SET public_config=?,enabled=?,priority=?,selection_group=?,response_policy=?,consumption=?,profile_id=?,"
                "activation_state=?,revision=revision+1,updated_at=? WHERE endpoint_id=? AND revision=?",
                (json.dumps(config, sort_keys=True), int(updated["enabled"]), updated["priority"], updated["selection_group"], updated["response_policy"],
                 updated["consumption"], updated["profile_id"], "approved" if updated["enabled"] else endpoint["activation_state"], now, endpoint_id, expected_revision))
            self.repo.invalidate_configuration(uow, endpoint_ids=[endpoint_id], now=now)
            self.repo.audit_configuration(uow, context=context, kind="endpoint", resource_id=endpoint_id,
                old_revision=expected_revision, new_revision=expected_revision + 1, fields=changes, now=now)
        return {"endpoint_id": endpoint_id, "revision": expected_revision + 1, "public_config": config,
                **{key: updated[key] for key in allowed - {"public_config"}}}

    def configure_boot(self, context, *, endpoint_id, enabled, expected_revision):
        self.authorize(context)
        if type(enabled) is not bool or type(expected_revision) is not int:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Boot requires a boolean and endpoint revision.", {})
        with self.cf.unit_of_work() as uow:
            endpoint = self.repo.get(uow, endpoint_id)
            if not endpoint or endpoint["revision"] != expected_revision:
                raise OktoNexusError(ErrorCode.CONFLICT, "Endpoint revision changed.", {})
            if enabled and (not endpoint["enabled"] or endpoint["health"] == "quarantined"):
                raise OktoNexusError(ErrorCode.CONFLICT, "Enable and reconcile the endpoint before configuring boot.", {})
            if enabled and endpoint["protocol"] != "nxl-r4":
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Legacy connection boot was removed.", {})
            if endpoint["protocol"] == "nxl-r4":
                from nexus_connector_core import get_runtime_catalog
                descriptor = next((item for item in get_runtime_catalog().runtimes
                                   if item.adapter_id == endpoint["adapter_id"]), None)
                attach = descriptor is None or descriptor.connection_mode != "managed"
            else:
                attach = enabled and self.registry.get(endpoint["adapter_id"]).substrate == "attach"
            if enabled and attach:
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "External attach targets require explicit selection in the current session; PID alone cannot authorize boot.", {})
            profile = self.repo.profile(uow, endpoint["profile_id"]) if endpoint["profile_id"] else None
            if enabled and (not profile or not profile["enabled"]):
                raise OktoNexusError(ErrorCode.CONFLICT, "Boot requires an enabled approved profile.", {})
            if enabled and uow.connection.execute("SELECT count(*) FROM runtime_boot_bindings WHERE enabled=1 AND endpoint_id<>?", (endpoint_id,)).fetchone()[0] >= 16:
                raise OktoNexusError(ErrorCode.CONFLICT, "At most 16 endpoints can be configured for boot.", {})
            self.repo.configure_boot(uow, endpoint=endpoint, profile=profile, context=context, enabled=enabled, now=self.clock.now_iso())
            binding = self.repo.boot_binding(uow, endpoint_id)
        return {"endpoint_id": endpoint_id, "boot_enabled": enabled, "revision": binding["revision"]}

    def reconcile(self, context, *, endpoint_id, expected_revision, idempotency_key, reason, acknowledge_uncertain_effects=False):
        self.authorize(context)
        if (acknowledge_uncertain_effects is not True or not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000
                or not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Reconciliation requires a reason, idempotency key and explicit acknowledgement of uncertain prior effects.", {})
        digest = hashlib.sha256(json.dumps([endpoint_id, expected_revision, reason], separators=(",", ":")).encode()).hexdigest()
        actor_id = context.actor_agent_id or "operator"
        with self.cf.unit_of_work() as uow:
            prior = uow.connection.execute("SELECT * FROM runtime_endpoint_reconciliations WHERE actor_agent_id=? AND idempotency_key=?",
                (actor_id, idempotency_key)).fetchone()
            if prior:
                if prior["request_hash"] != digest:
                    raise OktoNexusError(ErrorCode.CONFLICT, "Reconciliation key binds different parameters.", {})
                return {"reconciliation_id": prior["reconciliation_id"], "endpoint_id": endpoint_id, "replayed": True}
            endpoint = self.repo.get(uow, endpoint_id)
            if not endpoint or endpoint["revision"] != expected_revision or endpoint["health"] != "quarantined":
                raise OktoNexusError(ErrorCode.CONFLICT, "Endpoint changed or does not require reconciliation.", {})
            if uow.connection.execute("SELECT 1 FROM harness_sessions WHERE endpoint_id=? AND lifecycle_state IN ('protocol_ready','stop_requested')", (endpoint_id,)).fetchone():
                raise OktoNexusError(ErrorCode.CONFLICT, "Close the current runtime before reconciling the endpoint.", {})
            rid, now = new_id("reconcile"), self.clock.now_iso()
            uow.connection.execute("INSERT INTO runtime_endpoint_reconciliations VALUES(?,?,?,?,?,?,?,?,?,?)",
                (rid, endpoint_id, actor_id, idempotency_key, digest, reason, endpoint["health"], endpoint["health_reason"], endpoint["revision"], now))
            uow.connection.execute("UPDATE agent_endpoints SET health='unknown',health_reason='operator_reconciled',revision=revision+1,updated_at=? WHERE endpoint_id=?", (now, endpoint_id))
            # Neither old sessions nor unknown operations are replayed/reclassified.
        return {"reconciliation_id": rid, "endpoint_id": endpoint_id, "replayed": False}

    def create_profile(self, context, *, profile_id, adapter_id, config=None, secret_refs=None,
                       inherit_ambient=False, enabled=False):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Legacy connection setup was removed. Use canonical runtime integration with the agent API key.", {})

    def update_profile(self, context, *, profile_id, expected_revision, **changes):
        self.authorize(context)
        allowed = {"config", "secret_refs", "inherit_ambient", "enabled"}
        if (type(expected_revision) is not int or expected_revision < 1 or not changes
                or set(changes) - allowed or any(value is None for value in changes.values())):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Profile update requires a positive revision and non-null mutable fields.", {})
        with self.cf.unit_of_work(write=False) as uow:
            profile = self.repo.profile(uow, profile_id)
        if not profile or profile["revision"] != expected_revision:
            raise OktoNexusError(ErrorCode.CONFLICT, "Runtime profile revision changed.", {})
        from nexus_connector_core import get_runtime_catalog
        if profile["adapter_id"] not in {item.adapter_id for item in get_runtime_catalog().runtimes}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Legacy runtime profile configuration was removed.", {})
        merged = profile | changes
        config, refs = self.validate_profile(profile["adapter_id"], merged["config"], merged["secret_refs"],
            bool(profile["inherit_ambient"]) if "inherit_ambient" not in changes else changes["inherit_ambient"],
            bool(profile["enabled"]) if "enabled" not in changes else changes["enabled"])
        with self.cf.unit_of_work() as uow:
            now = self.clock.now_iso()
            cur = uow.connection.execute("UPDATE runtime_profiles SET config=?,secret_refs=?,inherit_ambient=?,enabled=?,revision=revision+1,updated_at=? WHERE profile_id=? AND revision=?",
                (json.dumps(config), json.dumps(refs), int(merged["inherit_ambient"]), int(merged["enabled"]), now, profile_id, expected_revision))
            if cur.rowcount != 1:
                raise OktoNexusError(ErrorCode.CONFLICT, "Runtime profile revision changed.", {})
            endpoints = [row[0] for row in uow.connection.execute("SELECT endpoint_id FROM agent_endpoints WHERE profile_id=?", (profile_id,))]
            self.repo.invalidate_configuration(uow, endpoint_ids=endpoints, now=now)
            self.repo.audit_configuration(uow, context=context, kind="profile", resource_id=profile_id,
                old_revision=expected_revision, new_revision=expected_revision + 1, fields=changes, now=now)
        return {"profile_id": profile_id, "adapter_id": profile["adapter_id"], "enabled": bool(merged["enabled"]),
                "inherit_ambient": bool(merged["inherit_ambient"]), "revision": expected_revision + 1}

    def validate_profile(self, adapter_id, config, secret_refs, inherit_ambient, enabled):
        descriptor = self.registry.get(adapter_id)
        if (config is not None and not isinstance(config, dict)) or (secret_refs is not None and not isinstance(secret_refs, dict)):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Profile configuration and secret references must be objects.", {})
        config, secret_refs = dict(config or {}), dict(secret_refs or {})
        check_inline_size("runtime profile", {"config": config, "secret_refs": secret_refs}, 65536)
        if descriptor.substrate == "attach":
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Attach uses an approved external target, not a process profile.", {})
        if not isinstance(inherit_ambient, bool) or not isinstance(enabled, bool):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Profile switches must be booleans.", {})
        allowed = {"command", "provider", "model", "sandbox", "approval_policy", "env", "extra_args", "required_native_requests", "disabled_capabilities"}
        if set(config) - allowed:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported runtime profile configuration.", {})
        if descriptor.kind != "pi" and set(config) & {"provider", "model", "extra_args"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "This adapter selects its backend through its approved environment/configuration.", {})
        if descriptor.kind != "codex" and set(config) & {"sandbox", "approval_policy"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                "These sandbox/approval options are implemented only by the Codex adapter; do not infer them for this runtime.", {})
        command = config.get("command")
        if command is not None and (not isinstance(command, list) or not command or
                                   any(not isinstance(x, str) or not x for x in command) or
                                   not Path(command[0]).is_absolute()):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Profile command requires an absolute executable and string arguments.", {})
        # Native launch arguments are controlled by the adapter. An executable
        # selector must not become a second channel for bypassing its policy.
        expected_args = {"codex": ["app-server"], "pi": ["--mode", "rpc"], "claude_code": []}
        if command is not None and command[1:] != expected_args.get(descriptor.kind, []):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Profile command arguments must match the adapter launch contract.", {})
        extra_args = config.get("extra_args", [])
        if (not isinstance(extra_args, list) or len(extra_args) % 2 or
                any(not isinstance(extra_args[i], str) or extra_args[i] not in {"--provider", "--model"} or
                    not isinstance(extra_args[i + 1], str) or not extra_args[i + 1] or
                    extra_args[i + 1].startswith("-") for i in range(0, len(extra_args), 2))):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Pi profile extra_args supports provider/model pairs only.", {})
        if config.get("sandbox", "read-only") not in {"read-only", "workspace-write"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "This managed profile requires a sandbox.", {})
        if config.get("approval_policy", "on-request") not in {"on-request", "untrusted"}:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "This managed profile requires approvals.", {})
        safe_env = {"CODEX_HOME", "CLAUDE_CONFIG_DIR", "PI_CODING_AGENT_DIR"}
        env = config.get("env", {})
        if (not isinstance(env, dict) or set(env) - safe_env or
                any(not isinstance(v, str) or not Path(v).is_absolute() for v in env.values())):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Use secret references for backend credentials.", {})
        if any(not isinstance(key, str) or not key.isidentifier() or not isinstance(ref, str)
               or not ref.startswith("env:") or not ref[4:].isidentifier() or "NEXUS" in ref.upper()
               or "NEXUS" in key.upper() for key, ref in secret_refs.items()):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Unsupported or privileged secret reference.", {})
        descriptor.config_validator(config)
        validate_native_requirements(config, descriptor)
        return config, secret_refs

    def create_endpoint(self, context, *, endpoint_id, agent_id, adapter_id, project_root,
                        profile_id=None, enabled=False, priority=0, selection_group=None,
                        response_policy="explicit", consumption="exclusive", public_config=None):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Legacy connection setup was removed. Use canonical runtime integration with the agent API key.", {})

    def list(self, context, *, agent_id=None):
        self.authorize(context)
        with self.cf.unit_of_work(write=False) as uow:
            return self.repo.list(uow, agent_id=agent_id)

    def profiles(self, context):
        self.authorize(context)
        with self.cf.unit_of_work(write=False) as uow:
            return self.repo.public_profiles(uow)

    def diagnostics(self, context):
        self.authorize(context)
        with self.cf.unit_of_work(write=False) as uow:
            historical = self.repo.legacy_diagnostics(uow)
            profile_review = self.repo.legacy_profile_review(uow)
            writer = dict(uow.connection.execute("SELECT required_contract,admission_enabled "
                "FROM runtime_writer_contract WHERE singleton=1").fetchone())
            boot = [dict(r) for r in uow.connection.execute("SELECT endpoint_id,enabled,endpoint_revision,profile_revision,revision FROM runtime_boot_bindings ORDER BY endpoint_id LIMIT 100")]
            uncertain = [dict(r) for r in uow.connection.execute("SELECT request_id,endpoint_id,status,owner_epoch,deadline,effects_started FROM runtime_open_requests WHERE status IN ('RESERVED','OUTCOME_UNKNOWN') ORDER BY created_at LIMIT 100")]
            configuration = [dict(r) | {"changed_fields": json.loads(r["changed_fields"])} for r in uow.connection.execute(
                "SELECT audit_id,actor_agent_id,resource_kind,resource_id,old_revision,new_revision,changed_fields,created_at "
                "FROM runtime_access_audit WHERE resource_kind IS NOT NULL ORDER BY audit_id DESC LIMIT 100")]
        return {"legacy_sessions": historical, "live": False,
                "legacy_profile_review": profile_review,
                "writer_contract": writer,
                "boot_bindings": boot, "uncertain_starts": uncertain,
                "configuration_changes": configuration,
                "recovery": "Review legacy bindings and restore damaged agent profiles only from a trusted backup; historical sessions do not prove liveness."}

    def resolve(self, context, *, endpoint_id, agent_id, kind, substrate, project_root):
        workspace_id = resolve_workspace_id(project_root)
        if self.access:
            self.access.authorize(context, action="open" if endpoint_id else "admin", substrate=substrate,
                                  endpoint_id=endpoint_id, represented_agent_id=agent_id, workspace_id=workspace_id)
        else:
            self.authorize(context)
        require_runtime_agent(agents=self.agents, connection_factory=self.cf, agent_id=agent_id)
        with self.cf.unit_of_work(write=False) as uow:
            candidates = [self.repo.get(uow, endpoint_id)] if endpoint_id else self.repo.list(
                uow, agent_id=agent_id, workspace_id=workspace_id)
            candidates = [e for e in candidates if e and e["enabled"] and e["agent_id"] == agent_id
                          and e["workspace_id"] == workspace_id and
                          (self.registry.get(e["adapter_id"]).kind, self.registry.get(e["adapter_id"]).substrate) == (kind, substrate)]
            if len(candidates) != 1:
                raise OktoNexusError(ErrorCode.CONFLICT if candidates else ErrorCode.NOT_FOUND,
                    "AMBIGUOUS_BINDING" if candidates else "Configure an enabled endpoint and approved runtime profile first.", {})
            endpoint = candidates[0]
            profile = self.repo.profile(uow, endpoint["profile_id"]) if endpoint["profile_id"] else None
            if profile is not None and not profile["enabled"]:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime profile is disabled.", {})
        if self.access:
            self.access.authorize(context, action="open", endpoint_id=endpoint["endpoint_id"],
                                  represented_agent_id=agent_id, workspace_id=workspace_id, substrate=substrate)
        return endpoint, profile
