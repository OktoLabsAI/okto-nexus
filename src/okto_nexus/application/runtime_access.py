"""Authenticated runtime delegation. Grants restrict canonical policy."""
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timezone
from ..domain.base import iso_to_epoch, new_id
from ..errors import ErrorCode, OktoNexusError
from .connection_policy import method_enabled, valid_connection_key

ACTIONS = frozenset({"open", "send", "steer", "interrupt", "close", "read", "events", "discover", "execute_work"})


def denied():
    return OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime action is not authorized.", {})


class RuntimeAccessService:
    def __init__(self, *, connection_factory, agents, endpoints, grants, config, clock, registry=None, admission_fence=None):
        self.cf, self.agents, self.endpoints, self.grants = connection_factory, agents, endpoints, grants
        self.config, self.clock = config, clock
        self.registry = registry
        self.admission_fence = admission_fence

    def require_admission(self, action, *, returning_external_work=False):
        if self.admission_fence is not None:
            self.admission_fence.require(action, returning_external_work=returning_external_work)

    @staticmethod
    def _operator(context, actor):
        from .execution_native_facts import runtime_operator
        return runtime_operator(context, actor)

    def authenticate(self, context, *, uow, require_feature=True):
        """Authenticate a discovery caller without granting resource authority."""
        actor = self.agents.get(uow, context.actor_agent_id) if context.actor_agent_id else None
        from .execution_native_facts import authenticate_runtime_facts
        return authenticate_runtime_facts(context, actor, feature_enabled=self.config.feature_harness_integrations,
            require_feature=require_feature)

    def authorize_maintenance(self, context, *, uow=None):
        """Operator recovery remains available while new admission is disabled."""
        with (nullcontext(uow) if uow is not None else self.cf.unit_of_work()) as uow:
            if not self.authenticate(context, uow=uow, require_feature=False):
                raise denied()
            self.grants.audit(uow, context=context, action="operation_maintenance", endpoint_id=None,
                session_id=None, grant=None, allowed=True, now=self.clock.now_iso())

    def authorize(self, context, *, action="admin", endpoint_id=None, session_id=None,
                  represented_agent_id=None, workspace_id=None, substrate=None, consume=False, uow=None, check_budget=True,
                  audit=True, _returning_external_work=False, _continuation_action=None):
        if (_continuation_action not in {None, 'approval.decide', 'input.provide', 'lease.renew', 'session.authority'} or
                (_continuation_action in {'approval.decide', 'input.provide'} and action not in {'open', 'send'}) or
                (_continuation_action == 'session.authority' and action != 'open') or
                (_continuation_action == 'lease.renew' and action not in ACTIONS)):
            raise ValueError('Invalid existing-session authority continuation.')
        # Only validated native-request, existing capability and lease callers
        # select these internal continuations. Grant, identity, policy and lease
        # checks remain unchanged; new work and new credentials remain fenced.
        self.require_admission(_continuation_action or action,
                               returning_external_work=_returning_external_work)
        now, allowed, selected = self.clock.now_iso(), False, None
        with (nullcontext(uow) if uow is not None else self.cf.unit_of_work()) as uow:
            actor = self.agents.get(uow, context.actor_agent_id) if context.actor_agent_id else None
            automated = context.authentication_source == 'handoff_automation'
            if automated:
                from .handoff_automation import require_context
                require_context(uow, context, action=action, endpoint_id=endpoint_id,
                    agent_id=represented_agent_id, workspace_id=workspace_id)
            if session_id:
                endpoint_id = self.grants.runtime_endpoint(uow, session_id)
            endpoint = self.endpoints.get(uow, endpoint_id) if endpoint_id else None
            if endpoint and endpoint['protocol'] != 'nxl-r4' and action not in {'read', 'events'}:
                raise denied()
            adapter_available = True
            if endpoint and endpoint["protocol"] == "nxl-r4":
                from nexus_connector_core import get_runtime_catalog
                descriptor = next((item for item in get_runtime_catalog().runtimes
                                   if item.adapter_id == endpoint["adapter_id"]), None)
                adapter_available = descriptor is not None
                substrate = descriptor.connection_mode if descriptor else None
            elif endpoint and self.registry:
                try:
                    substrate = self.registry.get(endpoint["adapter_id"]).substrate
                except OktoNexusError:
                    adapter_available = False
            # Historical inspection must survive disabled execution or removed
            # providers during cutover/restore. Authentication, grants and audit
            # below still apply; this does not authorize a native effect.
            enabled = action in {"read", "events"} or (
                adapter_available and self.config.feature_harness_integrations
                and substrate != "attach")
            if endpoint and action in {"open", "send", "steer", "execute_work"}:
                if endpoint['protocol'] != 'nxl-r4':
                    raise denied()
                from .agent_execution_policy import require_execution_location
                binding = uow.connection.execute('SELECT b.executor_id FROM execution_bindings b '
                    'JOIN execution_installation i ON i.server_id=b.server_id AND i.singleton=1 '
                    'WHERE b.endpoint_id=? LIMIT 2', (endpoint_id,)).fetchall()
                if len(binding) != 1:
                    raise denied()
                require_execution_location(uow, agent_id=endpoint['agent_id'], executor_id=binding[0]['executor_id'], adapter_id=endpoint['adapter_id'])
                # Deactivation revokes execution for the represented identity,
                # including operator/boot paths and cached idempotent requests.
                # Read, interrupt and close remain available for recovery.
                represented = self.agents.get(uow, endpoint["agent_id"])
                profile = self.endpoints.profile(uow, endpoint['profile_id']) if endpoint['profile_id'] else None
                from .execution_native_facts import native_runtime_enabled
                enabled = native_runtime_enabled(enabled=enabled, endpoint=endpoint, represented=represented,
                    method_enabled=method_enabled(uow, endpoint['agent_id'], endpoint['adapter_id']),
                    profile=profile, descriptor=descriptor, hitl_enabled=self.config.feature_hitl, action=action,
                    session_id=session_id, session_profile_revision=self.endpoints.session_profile_revision(uow, session_id)
                        if session_id and profile else None)
            if enabled and context.authentication_source == "connection_key":
                key = valid_connection_key(uow, context.credential_binding, now, endpoint_id, agents=self.agents)
                allowed = bool(key and key["agent_id"] == context.actor_agent_id and action in {"access", "open"}
                    and (not represented_agent_id or represented_agent_id == key["agent_id"]))
                if allowed and key["source_grant_id"]:
                    try:
                        self.authorize(replace(context, authentication_source="agent_key",
                            credential_binding=actor.api_key_hash if actor else None,
                            execution_grant_id=key["source_grant_id"]), action="open",
                            endpoint_id=key["endpoint_id"], represented_agent_id=key["agent_id"], uow=uow, audit=False)
                    except OktoNexusError:
                        allowed = False
            elif enabled and endpoint and context.authentication_source == "runtime_boot":
                allowed = self.endpoints.boot_authorized(uow, context=context, endpoint=endpoint, action=action, now=now)
            elif enabled and self._operator(context, actor) and not context.execution_grant_id:
                allowed = True
            elif (enabled and actor and actor.is_active and (automated or (
                  context.authentication_source == "agent_key" and context.credential_binding
                  and context.credential_binding == actor.api_key_hash))):
                candidates = self.grants.candidates(uow, actor_id=actor.agent_id, endpoint_id=endpoint_id)
                if action == 'open' and not context.execution_grant_id:
                    # A fresh opening prefers a grant that can carry productive
                    # work. Existing leases keep their exact source grant.
                    candidates.sort(key=lambda g: not set(g['actions']) & {'send', 'steer', 'execute_work'} or
                        not g['unlimited_actions'] and g['used_executions'] >= g['max_executions'])
                for grant in candidates:
                    from .execution_native_facts import grant_candidate_matches, grant_candidate_authorized
                    if not grant_candidate_matches(grant, context=context, actor=actor, action=action,
                            endpoint_id=endpoint_id, now=now, automated=automated):
                        continue
                    represented = self.agents.get(uow, grant["represented_agent_id"])
                    profile = self.endpoints.profile(uow, endpoint['profile_id']) if endpoint and endpoint['profile_id'] else None
                    if not grant_candidate_authorized(grant, actor=actor, represented=represented, endpoint=endpoint,
                            profile=profile, action=action, represented_agent_id=represented_agent_id,
                            workspace_id=workspace_id, check_budget=check_budget, consume=consume):
                        continue
                    allowed, selected = True, grant
                    if consume and action in {"send", "steer", "execute_work"}:
                        self.grants.consume(uow, grant_id=grant["grant_id"])
                    break
            if audit:
                self.grants.audit(uow, context=context, action=action, endpoint_id=endpoint_id,
                                  session_id=session_id, grant=selected, allowed=allowed, now=now)
        if not allowed:
            raise denied()
        return selected

    def issue(self, context, *, actor_agent_id, endpoint_id, actions, expires_at, max_executions=1):
        self.authorize(context)
        if not isinstance(actions, list) or not actions or any(not isinstance(a, str) or a not in ACTIONS for a in actions):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Grant actions must be supported runtime actions.", {})
        now = self.clock.now_iso()
        try:
            # API/browser timestamps may have millisecond precision. Normalize
            # external input before persisting the fixed-width lease format.
            if expires_at is not None:
                expires_at = datetime.fromtimestamp(iso_to_epoch(expires_at), timezone.utc).isoformat(
                    timespec="microseconds").replace("+00:00", "Z")
                remaining = iso_to_epoch(expires_at) - iso_to_epoch(now)
        except (ValueError, TypeError, OverflowError):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Grant expiry must be a valid timestamp.", {}) from None
        if ((expires_at is not None and not 0 < remaining <= 86400) or
                (max_executions is not None and (type(max_executions) is not int or not 1 <= max_executions <= 1000))):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Grant expiry must be within 24 hours and budget within 1..1000.", {})
        with self.cf.unit_of_work() as uow:
            actor = self.agents.get(uow, actor_agent_id)
            endpoint = self.endpoints.get(uow, endpoint_id)
            if not actor or not actor.is_active or not actor.api_key_hash or not endpoint or not endpoint["enabled"]:
                raise denied()
            if endpoint["protocol"] != "nxl-r4":
                raise denied()
            if expires_at is None or max_executions is None:
                local = uow.connection.execute(
                    "SELECT e.kind FROM execution_bindings b JOIN execution_installation i "
                    "ON i.server_id=b.server_id AND i.singleton=1 JOIN execution_executors e "
                    "ON e.server_id=b.server_id AND e.executor_id=b.executor_id "
                    "WHERE b.endpoint_id=? LIMIT 2", (endpoint_id,)).fetchall()
                if len(local) != 1 or local[0]['kind'] not in ('embedded', 'remote'):
                    raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                        "Unbounded permissions require a uniquely bound execution host.", {})
            if set(actions) & {"open", "send", "steer", "execute_work"}:
                binding = uow.connection.execute(
                    "SELECT b.executor_id FROM execution_bindings b JOIN execution_installation i "
                    "ON i.server_id=b.server_id AND i.singleton=1 WHERE b.endpoint_id=? LIMIT 2",
                    (endpoint_id,)).fetchall()
                if len(binding) != 1:
                    raise denied()
                from .agent_execution_policy import require_execution_location
                require_execution_location(uow, agent_id=endpoint["agent_id"],
                    executor_id=binding[0]["executor_id"], adapter_id=endpoint["adapter_id"])
            represented = self.agents.get(uow, endpoint["agent_id"])
            if not represented or not represented.is_active:
                raise denied()
            profile = self.endpoints.profile(uow, endpoint["profile_id"]) if endpoint["profile_id"] else None
            grant = dict(grant_id=new_id("grant"), issuer_agent_id=context.actor_agent_id or "operator",
                         actor_agent_id=actor_agent_id, credential_binding=actor.api_key_hash,
                         represented_agent_id=endpoint["agent_id"], endpoint_id=endpoint_id,
                         workspace_id=endpoint["workspace_id"], profile_revision=profile["revision"] if profile else None,
                         actions=actions, expires_at=expires_at, max_executions=max_executions, created_at=now)
            self.grants.insert(uow, grant=grant)
        return {k: v for k, v in grant.items() if k != "credential_binding"}

    def revoke(self, context, *, grant_id):
        self.authorize(context)
        with self.cf.unit_of_work() as uow:
            self.grants.revoke(uow, grant_id=grant_id, now=self.clock.now_iso())
            from .execution_revocation import invalidate_sessions
            invalidate_sessions(uow.connection, grant_id=grant_id, now=self.clock.now_iso())
        return {"revoked": True}
