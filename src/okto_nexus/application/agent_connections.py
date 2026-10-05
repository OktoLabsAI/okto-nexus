"""Operator-managed connection capabilities and scoped opening credentials."""
from ..errors import ErrorCode, OktoNexusError
from .connection_policy import method_enabled

KEY_PREFIX = "nxsconn_"


class AgentConnectionService:
    def __init__(self, access, *, fresh_publications=None, remote_ready=False):
        self.access = access
        self.fresh = fresh_publications if fresh_publications is not None else {}
        self.remote_ready = remote_ready
        self.cf, self.repo, self.clock = access.cf, access.endpoints, access.clock

    def _global_ttl(self, uow):
        from .settings import SettingsService
        config = self.access.config
        if getattr(config, "_connection_key_ttl_pinned", config.connection_key_ttl_seconds != 86400):
            return config.connection_key_ttl_seconds
        return SettingsService(config, self.clock).load_overrides(uow).get("connection_key_ttl_seconds", config.connection_key_ttl_seconds)

    def _agent(self, uow, agent_id):
        agent = self.access.agents.get(uow, agent_id)
        if not agent:
            raise OktoNexusError(ErrorCode.NOT_FOUND, "Agent does not exist.", {})
        return agent

    def view(self, context, *, agent_id):
        self.access.authorize_maintenance(context)
        with self.cf.unit_of_work(write=False) as uow:
            agent = self._agent(uow, agent_id)
            policy = uow.connection.execute("SELECT * FROM agent_connection_policies WHERE agent_id=?", (agent_id,)).fetchone()
            endpoints = self.repo.list(uow, agent_id=agent_id)
            methods = [{"method": "mcp", "protocol": "MCP", "enabled": method_enabled(uow, agent_id, "mcp")}]
            keys = [dict(r) for r in uow.connection.execute(
                "SELECT key_id,endpoint_id,created_at,expires_at,revoked_at FROM agent_connection_keys WHERE agent_id=? ORDER BY created_at DESC LIMIT 100", (agent_id,))]
            from .execution_connection_discovery import canonical_methods
            methods.extend(canonical_methods(uow, agent_id))
            endpoint_views = []
            for endpoint in endpoints:
                if endpoint["protocol"] != "nxl-r4":
                    continue
                can_issue = False
                try:
                    self.access.authorize(context, action="open", endpoint_id=endpoint['endpoint_id'], uow=uow, audit=False)
                except OktoNexusError as exc:
                    if exc.code != ErrorCode.PERMISSION_DENIED:
                        raise
                    can_issue = False
                endpoint_views.append({**{k: endpoint[k] for k in ('endpoint_id', 'adapter_id', 'enabled', 'activation_state')}, "can_issue": can_issue})
            ttl = policy['key_ttl_seconds'] if policy else None
            return {"agent_id": agent_id, "has_agent_key": bool(agent.api_key_hash), "revision": policy['revision'] if policy else 0,
                "key_ttl_seconds": ttl, "effective_key_ttl_seconds": self._global_ttl(uow) if ttl is None else ttl,
                "methods": methods, "endpoints": endpoint_views, "keys": keys}

    def _self(self, context, uow):
        self.access.authenticate(context, uow=uow, require_feature=False)
        # Even loopback operator trust is not an authenticated agent identity.
        if context.authentication_source != "agent_key" or not context.actor_agent_id:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Authenticate with your agent key for self connection discovery.", {})
        return self._agent(uow, context.actor_agent_id)

    def available(self, context):
        """Self-only, secret-free configuration readiness; never probes a harness."""
        with self.cf.unit_of_work(write=False) as uow:
            actor = self._self(context, uow)
            endpoints = self.repo.list(uow, agent_id=actor.agent_id)
            methods = [{"method": "mcp", "protocol": "MCP", "enabled": method_enabled(uow, actor.agent_id, "mcp"),
                "available": method_enabled(uow, actor.agent_id, "mcp"), "connection_mode": "current_authenticated_transport", "endpoints": []}]
            from .execution_connection_discovery import canonical_available
            methods.extend(canonical_available(uow, access=self.access, context=context,
                endpoints=endpoints, fresh=self.fresh, remote_ready=self.remote_ready))
            return {"contract_version": 1, "agent_id": actor.agent_id, "methods": methods,
                "instructions": "Use a returned connect call with a unique idempotency key. Reuse that key only for the same opening; uncertain outcomes require inspection. Opening does not authorize tasks or adopt your current conversation."}

    def prepare_self_open(self, context, *, endpoint_id, idempotency_key):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Legacy connection setup was removed. Use the agent API key and canonical runtime integration.", {})

    def configure(self, context, *, agent_id, expected_revision, methods, key_ttl_seconds):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Legacy connection setup was removed. Use the agent API key and canonical runtime integration.", {})

    def issue(self, context, *, agent_id, endpoint_id):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Legacy connection setup was removed. Use the agent API key and canonical runtime integration.", {})

    def revoke(self, context, *, agent_id, key_id):
        self.access.authorize_maintenance(context)
        with self.cf.unit_of_work() as uow:
            now = self.clock.now_iso()
            uow.connection.execute("UPDATE agent_connection_keys SET revoked_at=? WHERE key_id=? AND agent_id=? AND revoked_at IS NULL", (now, key_id, agent_id))
            self.repo.audit_configuration(uow, context=context, kind="connection_key", resource_id=key_id,
                old_revision=1, new_revision=2, fields=["revoked"], now=now)
        return {"revoked": True}

    def resolve(self, raw):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Legacy connection keys are no longer accepted. Use the agent API key.", {})
