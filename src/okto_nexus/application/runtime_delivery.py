"""Pure transactional selection/planning; never calls transports or secrets."""
from ..domain.base import new_id
from ..domain.delivery import DeliveryEnvelope
from ..domain.tag_selector import reachable
from ..errors import ErrorCode, OktoNexusError


class RuntimeDeliveryPlanner:
    def __init__(self, *, endpoints, outbox, agents):
        self.endpoints, self.outbox, self.agents = endpoints, outbox, agents

    def enqueue(self, uow, *, context, message, delivery, now, authorization_revision):
        # Legacy cooperative-trust messages still reach the logical inbox, but
        # cannot acquire execution authority from a sender ID in the payload.
        if not context or context.authentication_source != "agent_key" or not context.credential_binding:
            return None
        actor = self.agents.get(uow, context.actor_agent_id)
        if not actor or not actor.is_active or actor.api_key_hash != context.credential_binding:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Authenticated delivery actor is unavailable.", {})
        if actor.agent_id != message.from_agent_id and actor.agent_id != "operator":
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Payload sender is not the authenticated actor.", {})
        candidates = []
        for endpoint in self.endpoints.list(uow, agent_id=delivery.recipient_agent_id, workspace_id=message.workspace_id):
            if not endpoint["enabled"] or endpoint["activation_state"] != "approved" or endpoint["consumption"] != "exclusive":
                continue
            if endpoint["health"] == "quarantined":
                continue
            # Explicit operator approval to respond conversationally. This
            # conveys no authority to claim or complete executable handoffs.
            if endpoint["response_policy"] != "conversation":
                continue
            profile = self.endpoints.profile(uow, endpoint["profile_id"]) if endpoint["profile_id"] else None
            if endpoint["profile_id"] and (not profile or not profile["enabled"]):
                continue
            live = self.outbox.live_sessions(uow, endpoint_id=endpoint["endpoint_id"])
            if len(live) > 1:
                raise OktoNexusError(ErrorCode.CONFLICT, "AMBIGUOUS_BINDING", {})
            candidates.append((endpoint, profile, live[0]["session_id"] if live else None))
        if not candidates:
            return None
        ready = [c for c in candidates if c[2]]
        candidates = ready or candidates
        priority = max(c[0]["priority"] for c in candidates)
        candidates = [c for c in candidates if c[0]["priority"] == priority]
        groups = {c[0]["selection_group"] for c in candidates}
        if len(candidates) > 1 and (len(groups) != 1 or None in groups):
            raise OktoNexusError(ErrorCode.CONFLICT, "AMBIGUOUS_BINDING", {})
        endpoint, profile, session = min(candidates, key=lambda c: c[0]["endpoint_id"])
        operation_id = new_id("op")
        envelope = DeliveryEnvelope(operation_id, message.from_agent_id, delivery.recipient_agent_id,
            message.workspace_id, "conversation", ({"type": "text", "text": message.body or ""},), operation_id,
            message_id=message.message_id, delivery_id=delivery.delivery_id, context_id=message.parent_message_id or message.message_id,
            subject=message.subject, causation_id=message.parent_message_id, response_requested=True,
            artifact_refs=tuple(message.artifacts or ()))
        self.outbox.enqueue(uow, envelope=envelope, context=context, endpoint=endpoint, profile=profile,
                           session_id=session, now=now, authorization_revision=authorization_revision)
        return operation_id

    def revalidate(self, uow, *, operation, config):
        actor = self.agents.get(uow, operation["actor_agent_id"])
        recipient = self.agents.get(uow, operation["recipient_agent_id"])
        endpoint = self.endpoints.get(uow, operation["endpoint_id"])
        if (not config.feature_harness_integrations or not actor or not actor.is_active or
                actor.api_key_hash != operation["credential_binding"] or not recipient or not recipient.is_active or
                not reachable(actor, recipient) or
                not endpoint or not endpoint["enabled"] or endpoint["revision"] != operation["endpoint_revision"] or
                endpoint["health"] == "quarantined" or
                endpoint["agent_id"] != recipient.agent_id or endpoint["workspace_id"] != operation["workspace_id"] or
                endpoint["response_policy"] != "conversation" or endpoint["consumption"] != "exclusive"):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Transport authorization changed before dispatch.", {})
        profile = self.endpoints.profile(uow, endpoint["profile_id"]) if endpoint["profile_id"] else None
        if endpoint["profile_id"] and (not profile or not profile["enabled"] or profile["revision"] != operation["profile_revision"]):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime profile changed before dispatch.", {})
        if profile and operation["runtime_session_id"] and self.endpoints.session_profile_revision(uow, operation["runtime_session_id"]) != profile["revision"]:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime must be reopened with the current approved profile.", {})
        return endpoint, profile
