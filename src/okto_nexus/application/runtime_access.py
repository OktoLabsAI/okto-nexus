"""Authenticated runtime delegation. Grants restrict canonical policy."""
from ..domain.base import iso_to_epoch, iso_plus, new_id
from ..domain.permissions import PermissionSet
from ..domain.tag_selector import reachable
from ..errors import ErrorCode, OktoNexusError

ACTIONS = frozenset({"open", "send", "steer", "interrupt", "close", "read", "events", "discover"})


def denied():
    return OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime action is not authorized.", {})


class RuntimeAccessService:
    def __init__(self, *, connection_factory, agents, endpoints, grants, config, clock, registry=None):
        self.cf, self.agents, self.endpoints, self.grants = connection_factory, agents, endpoints, grants
        self.config, self.clock = config, clock
        self.registry = registry

    @staticmethod
    def _operator(context, actor):
        local = context.trusted_local_operator and context.authentication_source == "http_loopback"
        keyed = (context.authentication_source == "agent_key" and actor and actor.is_active
                 and actor.agent_id == "operator" and context.credential_binding
                 and context.credential_binding == actor.api_key_hash)
        return bool(local or keyed)

    def authorize(self, context, *, action="admin", endpoint_id=None, session_id=None,
                  represented_agent_id=None, workspace_id=None, substrate=None, consume=False):
        now, allowed, selected = self.clock.now_iso(), False, None
        with self.cf.unit_of_work() as uow:
            actor = self.agents.get(uow, context.actor_agent_id) if context.actor_agent_id else None
            if session_id:
                endpoint_id = self.grants.runtime_endpoint(uow, session_id)
            endpoint = self.endpoints.get(uow, endpoint_id) if endpoint_id else None
            adapter_available = True
            if endpoint and self.registry:
                try:
                    substrate = self.registry.get(endpoint["adapter_id"]).substrate
                except OktoNexusError:
                    adapter_available = False
            enabled = adapter_available and self.config.feature_harness_integrations and (
                substrate != "attach" or self.config.feature_harness_attach)
            if enabled and self._operator(context, actor):
                allowed = True
            elif (enabled and actor and actor.is_active and context.authentication_source == "agent_key"
                  and context.credential_binding and context.credential_binding == actor.api_key_hash):
                for grant in self.grants.candidates(uow, actor_id=actor.agent_id):
                    if context.execution_grant_id and context.execution_grant_id != grant["grant_id"]:
                        continue
                    if endpoint_id and endpoint_id != grant["endpoint_id"]:
                        continue
                    if grant["credential_binding"] != actor.api_key_hash or grant["expires_at"] <= now:
                        continue
                    if action != "access" and action not in grant["actions"]:
                        continue
                    if action != "access" and (not endpoint or not endpoint["enabled"] or
                            endpoint["activation_state"] != "approved" or grant["endpoint_id"] != endpoint_id):
                        continue
                    represented = self.agents.get(uow, grant["represented_agent_id"])
                    if not represented or not represented.is_active or not reachable(actor, represented):
                        continue
                    if represented_agent_id and represented_agent_id != grant["represented_agent_id"]:
                        continue
                    if workspace_id and workspace_id != grant["workspace_id"]:
                        continue
                    if endpoint and (endpoint["agent_id"] != grant["represented_agent_id"] or
                                     endpoint["workspace_id"] != grant["workspace_id"]):
                        continue
                    if endpoint and endpoint["profile_id"]:
                        profile = self.endpoints.profile(uow, endpoint["profile_id"])
                        if not profile or not profile["enabled"] or profile["revision"] != grant["profile_revision"]:
                            continue
                    permission = ("events", "read") if action in {"read", "events", "discover"} else ("messages", "send_direct")
                    if not PermissionSet(actor.permissions).allows(*permission):
                        continue
                    if action in {"send", "steer"} and grant["used_executions"] >= grant["max_executions"]:
                        continue
                    allowed, selected = True, grant
                    if consume and action in {"send", "steer"}:
                        self.grants.consume(uow, grant_id=grant["grant_id"])
                    break
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
            expires_at = iso_plus(expires_at, 0)
            remaining = iso_to_epoch(expires_at) - iso_to_epoch(now)
        except (ValueError, TypeError, OverflowError):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Grant expiry must be a valid timestamp.", {}) from None
        if not 0 < remaining <= 86400 or type(max_executions) is not int or not 1 <= max_executions <= 1000:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Grant expiry must be within 24 hours and budget within 1..1000.", {})
        with self.cf.unit_of_work() as uow:
            actor = self.agents.get(uow, actor_agent_id)
            endpoint = self.endpoints.get(uow, endpoint_id)
            if not actor or not actor.is_active or not actor.api_key_hash or not endpoint or not endpoint["enabled"]:
                raise denied()
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
        return {"revoked": True}
