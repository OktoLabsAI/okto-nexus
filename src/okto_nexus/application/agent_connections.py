"""Operator-managed connection capabilities and scoped opening credentials."""
import hashlib
import os
import secrets
import sys

from ..domain.base import iso_plus, new_id
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError
from .connection_policy import method_enabled, valid_connection_key

KEY_PREFIX = "nxsconn_"


class AgentConnectionService:
    def __init__(self, access):
        self.access = access
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
            for descriptor in self.access.registry.descriptors():
                methods.append({"method": descriptor.adapter_id, "protocol": descriptor.protocol,
                    "enabled": method_enabled(uow, agent_id, descriptor.adapter_id),
                    "requires_endpoint": True, "substrate": descriptor.substrate,
                    "platform_compatible": not descriptor.supported_platforms or bool({os.name, sys.platform}.intersection(descriptor.supported_platforms))})
            keys = [dict(r) for r in uow.connection.execute(
                "SELECT key_id,endpoint_id,created_at,expires_at,revoked_at FROM agent_connection_keys WHERE agent_id=? ORDER BY created_at DESC LIMIT 100", (agent_id,))]
            endpoint_views = []
            for endpoint in endpoints:
                can_issue = True
                try:
                    self.access.authorize(context, action="open", endpoint_id=endpoint['endpoint_id'], uow=uow, audit=False)
                except OktoNexusError as exc:
                    if exc.code != ErrorCode.PERMISSION_DENIED:
                        raise
                    can_issue = False
                descriptor = self.access.registry.get(endpoint['adapter_id'])
                can_issue = can_issue and (not descriptor.supported_platforms or bool({os.name, sys.platform}.intersection(descriptor.supported_platforms)))
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
            owner = uow.connection.execute("SELECT lease_expires_at FROM runtime_dispatcher_owner WHERE owner_key='dispatcher'").fetchone()
            owner_ready = bool(owner and owner[0] > self.clock.now_iso())
            methods = [{"method": "mcp", "protocol": "MCP", "enabled": method_enabled(uow, actor.agent_id, "mcp"),
                "available": method_enabled(uow, actor.agent_id, "mcp"), "connection_mode": "current_authenticated_transport", "endpoints": []}]
            for descriptor in self.access.registry.descriptors():
                enabled = method_enabled(uow, actor.agent_id, descriptor.adapter_id)
                blockers = []
                if not self.access.config.feature_harness_integrations:
                    blockers.append("integrations_disabled")
                if descriptor.substrate == "attach" and not self.access.config.feature_harness_attach:
                    blockers.append("attach_disabled")
                if not enabled:
                    blockers.append("agent_method_disabled")
                if descriptor.supported_platforms and not {os.name, sys.platform}.intersection(descriptor.supported_platforms):
                    blockers.append("unsupported_platform")
                if not owner_ready:
                    blockers.append("serve_owner_required")
                rows = []
                for endpoint in endpoints:
                    if endpoint['adapter_id'] != descriptor.adapter_id:
                        continue
                    reasons = list(blockers)
                    try:
                        self.access.authorize(context, action="open", endpoint_id=endpoint['endpoint_id'],
                            represented_agent_id=actor.agent_id, uow=uow, audit=False)
                    except OktoNexusError as exc:
                        if exc.code != ErrorCode.PERMISSION_DENIED:
                            raise
                        reasons.append("open_authorization_or_configuration_required")
                    row = {"endpoint_id": endpoint['endpoint_id'], "available": not reasons, "unavailable_reasons": reasons}
                    if not reasons:
                        row['connect'] = {"tool": "harness_list", "arguments": {"view": "connections", "maintenance": {
                            "action": "connect", "endpoint_id": endpoint['endpoint_id'], "idempotency_key": "<unique-key-for-this-opening>"}}}
                    rows.append(row)
                if not rows:
                    blockers.append("endpoint_required")
                methods.append({"method": descriptor.adapter_id, "protocol": descriptor.protocol, "enabled": enabled,
                    "available": any(row['available'] for row in rows), "unavailable_reasons": blockers,
                    "connection_mode": "approved_external_target" if descriptor.substrate == "attach" else "managed_runtime",
                    "capability_verification": "not_probed", "endpoints": rows})
            return {"contract_version": 1, "agent_id": actor.agent_id, "methods": methods,
                "instructions": "Use a returned connect call with a unique idempotency key. Reuse that key only for the same opening; uncertain outcomes require inspection. Opening does not authorize tasks or adopt your current conversation."}

    def prepare_self_open(self, context, *, endpoint_id, idempotency_key):
        if (not isinstance(endpoint_id, str) or not endpoint_id or len(endpoint_id) > 256
                or not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128
                or idempotency_key == "<unique-key-for-this-opening>"):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Provide endpoint_id and a unique idempotency_key (1..128 characters).", {})
        with self.cf.unit_of_work(write=False) as uow:
            actor = self._self(context, uow)
            endpoint = self.repo.get(uow, endpoint_id)
            if not endpoint or endpoint['agent_id'] != actor.agent_id:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Only your own approved endpoint may be connected here.", {})
            self.access.authorize(context, action="open", endpoint_id=endpoint_id,
                represented_agent_id=actor.agent_id, uow=uow, audit=False)
            descriptor = self.access.registry.get(endpoint['adapter_id'])
            if descriptor.supported_platforms and not {os.name, sys.platform}.intersection(descriptor.supported_platforms):
                raise OktoNexusError(ErrorCode.CONFIG_ERROR, "Connection method is unsupported on this platform.", {})
            root = uow.connection.execute("SELECT root_realpath FROM workspaces WHERE workspace_id=?", (endpoint['workspace_id'],)).fetchone()[0]
            return {"agent_id": actor.agent_id, "endpoint_id": endpoint_id, "kind": descriptor.kind,
                "substrate": descriptor.substrate, "project_root": root, "idempotency_key": idempotency_key}

    def configure(self, context, *, agent_id, expected_revision, methods, key_ttl_seconds):
        self.access.authorize_maintenance(context)
        catalog = {d.adapter_id for d in self.access.registry.descriptors()} | {"mcp"}
        if (type(expected_revision) is not int or expected_revision < 0 or not isinstance(methods, dict)
                or set(methods) - catalog or any(type(v) is not bool for v in methods.values())
                or key_ttl_seconds is not None and (type(key_ttl_seconds) is not int or not 0 <= key_ttl_seconds <= 315360000)):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid connection policy.", {})
        with self.cf.unit_of_work() as uow:
            self._agent(uow, agent_id)
            row = uow.connection.execute("SELECT revision FROM agent_connection_policies WHERE agent_id=?", (agent_id,)).fetchone()
            if (row[0] if row else 0) != expected_revision:
                raise OktoNexusError(ErrorCode.CONFLICT, "Connection policy changed; reload before saving.", {})
            uow.connection.execute("INSERT INTO agent_connection_policies VALUES(?,?,?) ON CONFLICT(agent_id) DO UPDATE SET key_ttl_seconds=excluded.key_ttl_seconds,revision=excluded.revision",
                (agent_id, key_ttl_seconds, expected_revision + 1))
            now = self.clock.now_iso()
            for method, enabled in methods.items():
                uow.connection.execute("INSERT INTO agent_connection_methods VALUES(?,?,?) ON CONFLICT(agent_id,method) DO UPDATE SET enabled=excluded.enabled", (agent_id, method, int(enabled)))
                if not enabled:
                    uow.connection.execute("UPDATE agent_connection_keys SET revoked_at=? WHERE agent_id=? AND revoked_at IS NULL AND endpoint_id IN (SELECT endpoint_id FROM agent_endpoints WHERE adapter_id=?)", (now, agent_id, method))
            self.repo.audit_configuration(uow, context=context, kind="connection_policy", resource_id=agent_id,
                old_revision=expected_revision, new_revision=expected_revision + 1, fields=["methods", "key_ttl_seconds"], now=now)
        return self.view(context, agent_id=agent_id)

    def issue(self, context, *, agent_id, endpoint_id):
        # An authenticated agent may bootstrap only its own explicitly granted
        # endpoint. Operator issuance is the explicit delegation for non-MCP peers.
        with self.cf.unit_of_work(write=False) as uow:
            operator = self.access.authenticate(context, uow=uow)
        source_grant = None
        if not operator:
            if context.actor_agent_id != agent_id:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Connection issuance denied.", {})
            source_grant = self.access.authorize(context, action="open", endpoint_id=endpoint_id, represented_agent_id=agent_id)
        else:
            self.access.authorize(context, action="open", endpoint_id=endpoint_id, represented_agent_id=agent_id)
        raw = KEY_PREFIX + secrets.token_urlsafe(32)
        with self.cf.unit_of_work() as uow:
            agent = self._agent(uow, agent_id)
            endpoint = self.repo.get(uow, endpoint_id)
            if not agent.is_active or not endpoint or endpoint['agent_id'] != agent_id or not method_enabled(uow, agent_id, endpoint['adapter_id']):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Connection issuance denied.", {})
            self.access.authorize(context, action="open", endpoint_id=endpoint_id, uow=uow)
            profile = self.repo.profile(uow, endpoint['profile_id']) if endpoint['profile_id'] else None
            row = uow.connection.execute("SELECT key_ttl_seconds FROM agent_connection_policies WHERE agent_id=?", (agent_id,)).fetchone()
            ttl = row[0] if row and row[0] is not None else self._global_ttl(uow)
            now, key_id = self.clock.now_iso(), new_id('conn')
            expires = iso_plus(now, ttl) if ttl else None
            if source_grant and (expires is None or expires > source_grant["expires_at"]):
                expires = source_grant["expires_at"]
            uow.connection.execute("INSERT INTO agent_connection_keys VALUES(?,?,?,?,?,?,?,?,NULL,?)",
                (key_id, hashlib.sha256(raw.encode()).hexdigest(), agent_id, endpoint_id, endpoint['revision'], profile['revision'] if profile else None, now, expires, source_grant['grant_id'] if source_grant else None))
            self.repo.audit_configuration(uow, context=context, kind="connection_key", resource_id=key_id,
                old_revision=None, new_revision=1, fields=["issued"], now=now)
        return {"key_id": key_id, "connection_key": raw, "expires_at": expires,
            "request": {"method": "POST", "path": "/api/v1/connections/open", "headers": {"Authorization": "Bearer " + raw}, "body": {}},
            "semantics": "Open the approved managed endpoint; does not adopt the caller's current conversation."}

    def revoke(self, context, *, agent_id, key_id):
        self.access.authorize_maintenance(context)
        with self.cf.unit_of_work() as uow:
            now = self.clock.now_iso()
            uow.connection.execute("UPDATE agent_connection_keys SET revoked_at=? WHERE key_id=? AND agent_id=? AND revoked_at IS NULL", (now, key_id, agent_id))
            self.repo.audit_configuration(uow, context=context, kind="connection_key", resource_id=key_id,
                old_revision=1, new_revision=2, fields=["revoked"], now=now)
        return {"revoked": True}

    def resolve(self, raw):
        if not isinstance(raw, str) or not raw.startswith(KEY_PREFIX) or len(raw) > 128:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Invalid connection credential.", {})
        digest = hashlib.sha256(raw.encode()).hexdigest()
        with self.cf.unit_of_work(write=False) as uow:
            row = valid_connection_key(uow, digest, self.clock.now_iso(), agents=self.access.agents)
            if not row:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Invalid connection credential.", {})
            endpoint = self.repo.get(uow, row['endpoint_id'])
            root = uow.connection.execute("SELECT root_realpath FROM workspaces WHERE workspace_id=?", (endpoint['workspace_id'],)).fetchone()[0]
        descriptor = self.access.registry.get(endpoint['adapter_id'])
        context = RuntimeRequestContext(row['agent_id'], 'connection_key', credential_binding=digest, endpoint_id=row['endpoint_id'])
        return context, {'agent_id': row['agent_id'], 'endpoint_id': row['endpoint_id'], 'kind': descriptor.kind,
            'substrate': descriptor.substrate, 'project_root': root, 'idempotency_key': 'connection:' + row['key_id']}
