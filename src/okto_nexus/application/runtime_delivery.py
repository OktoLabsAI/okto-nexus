"""Pure transactional selection/planning; never calls transports or secrets."""
import json
from dataclasses import replace
from ..domain.base import new_id
from ..domain.delivery import DeliveryEnvelope
from ..domain.tag_selector import reachable
from ..errors import ErrorCode, OktoNexusError
from .runtime_bootstrap import delivery_context
from .runtime_requirements import validate_native_requirements
from .runtime_causality import RuntimeCausalityService


class RuntimeDeliveryPlanner:
    def __init__(self, *, endpoints, outbox, agents, registry, config, observations=None):
        self.endpoints, self.outbox, self.agents = endpoints, outbox, agents
        self.registry, self.config = registry, config
        self.observations = observations
        self.causality = RuntimeCausalityService(config=config, agents=agents)

    def observer_candidates(self, uow, *, agent_id, workspace_id):
        candidates = []
        if not self.config.feature_harness_integrations:
            return candidates
        for endpoint in self.endpoints.list(uow, agent_id=agent_id, workspace_id=workspace_id):
            descriptor = self.registry.get(endpoint["adapter_id"])
            if (not endpoint["enabled"] or endpoint["activation_state"] != "approved"
                    or endpoint["health"] == "quarantined" or endpoint["consumption"] != "mirror_only"
                    or endpoint["response_policy"] != "none"
                    or not descriptor.capabilities.context_without_execution
                    or descriptor.input_schema.get("context_observation_contract") != 1
                    or descriptor.substrate == "attach" and not self.config.feature_harness_attach):
                continue
            profile = self.endpoints.profile(uow, endpoint["profile_id"]) if endpoint["profile_id"] else None
            if endpoint["profile_id"] and (not profile or not profile["enabled"]
                    or "context_without_execution" in profile["config"].get("disabled_capabilities", ())):
                continue
            live = [row for row in self.outbox.live_sessions(uow, endpoint_id=endpoint["endpoint_id"])
                if row["compatibility_report"].get("effective_capability_contract") == 1
                and row["compatibility_report"].get("effective_capabilities", {}).get("context_without_execution") is True
                and (not profile or self.endpoints.session_profile_revision(uow, row["session_id"]) == profile["revision"])]
            if len(live) > 1:
                raise OktoNexusError(ErrorCode.CONFLICT, "AMBIGUOUS_BINDING", {})
            if live:
                candidates.append((endpoint, profile, live[0]))
        return candidates

    def candidates(self, uow, *, agent_id, workspace_id):
        candidates = []
        for endpoint in self.endpoints.list(uow, agent_id=agent_id, workspace_id=workspace_id):
            descriptor = self.registry.get(endpoint["adapter_id"])
            if not descriptor.capabilities.conversation or (descriptor.substrate == "attach" and not self.config.feature_harness_attach):
                continue
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
            if profile:
                if "conversation" in profile["config"].get("disabled_capabilities", ()):
                    continue
                try:
                    validate_native_requirements(profile["config"], self.registry.get(endpoint["adapter_id"]),
                                                 hitl_enabled=self.config.feature_hitl)
                except OktoNexusError:
                    continue
            live = self.outbox.live_sessions(uow, endpoint_id=endpoint["endpoint_id"])
            if live:
                live = [session for session in live if session["compatibility_report"].get("effective_capability_contract") == 1
                        and session["compatibility_report"].get("effective_capabilities", {}).get("conversation") is True]
                if not live:
                    continue
            if len(live) > 1:
                raise OktoNexusError(ErrorCode.CONFLICT, "AMBIGUOUS_BINDING", {})
            candidates.append((endpoint, profile, live[0]["session_id"] if live else None))
        return candidates

    def enqueue(self, uow, *, context, message, delivery, now, authorization_revision, result_source=None):
        # Legacy cooperative-trust messages still reach the logical inbox, but
        # cannot acquire execution authority from a sender ID in the payload.
        source_kind = "captured_result" if result_source else "agent_key"
        if not context or context.authentication_source != source_kind or not context.credential_binding:
            return None
        actor = self.agents.get(uow, context.actor_agent_id)
        if not actor or not actor.is_active or actor.api_key_hash != context.credential_binding:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Authenticated delivery actor is unavailable.", {})
        if result_source:
            if (result_source["recipient_agent_id"] != message.from_agent_id or result_source["actor_agent_id"] != actor.agent_id
                    or result_source["parent_id"] != message.parent_message_id or result_source["workspace_id"] != message.workspace_id):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Captured result source does not match this delivery.", {})
        elif actor.agent_id != message.from_agent_id and actor.agent_id != "operator":
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Payload sender is not the authenticated actor.", {})
        candidates = self.candidates(uow, agent_id=delivery.recipient_agent_id, workspace_id=message.workspace_id)
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
        if result_source:
            self.causality.admit_result_relay(uow, message_id=message.message_id,
                source_result_id=result_source["result_id"], now=now)
        cause = self.causality.reserve_execution(uow, message_id=message.message_id, now=now)
        operation_id = new_id("op")
        bootstrap = delivery_context(uow, agents=self.agents, endpoint=endpoint, profile=profile, intent="conversation")
        bootstrap["causality"] = self.causality.context(cause)
        envelope = DeliveryEnvelope(operation_id, message.from_agent_id, delivery.recipient_agent_id,
            message.workspace_id, "conversation", ({"type": "text", "text": message.body or ""},), cause["root_operation_id"],
            message_id=message.message_id, delivery_id=delivery.delivery_id, context_id=message.parent_message_id or message.message_id,
            subject=message.subject, causation_id=message.parent_message_id, hop_count=cause["hop_count"], response_requested=True,
            artifact_refs=tuple(message.artifacts or ()),
            runtime_context=bootstrap)
        self.outbox.enqueue(uow, envelope=envelope, context=context, endpoint=endpoint, profile=profile,
                           session_id=session, now=now, authorization_revision=authorization_revision)
        if result_source:
            uow.connection.execute("UPDATE delivery_outbox SET source_result_id=? WHERE operation_id=?",
                                  (result_source["result_id"], operation_id))
        if self.observations:
            for observer, observer_profile, observer_session in self.observer_candidates(uow,
                    agent_id=delivery.recipient_agent_id, workspace_id=message.workspace_id):
                context_envelope = replace(envelope, operation_id=new_id("obs"), intent="information",
                    response_requested=False, runtime_context=None)
                self.observations.enqueue(uow, source_operation_id=operation_id, envelope=context_envelope,
                    endpoint=observer, profile=observer_profile, session=observer_session, now=now)
        return operation_id

    def revalidate(self, uow, *, operation, config):
        if operation.get("reconciliation_id"):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Transport attempt was administratively reconciled.", {})
        if operation.get("admission_binding"):
            admission = json.loads(operation["admission_binding"])
            original = self.endpoints.get(uow, admission["endpoint_id"])
            if (not original or original["revision"] != admission["revision"]
                    or not original["enabled"] or original["activation_state"] != "approved"
                    or original["selection_group"] != admission["selection_group"]):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Original fallback approval changed.", {})
            original_profile = self.endpoints.profile(uow, admission["profile_id"]) if admission["profile_id"] else None
            if admission["profile_id"] and (not original_profile or not original_profile["enabled"]
                    or original_profile["revision"] != admission["profile_revision"]):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Original fallback profile approval changed.", {})
        actor = self.agents.get(uow, operation["actor_agent_id"])
        recipient = self.agents.get(uow, operation["recipient_agent_id"])
        endpoint = self.endpoints.get(uow, operation["endpoint_id"])
        if operation.get("admission_binding") and endpoint and endpoint["selection_group"] != admission["selection_group"]:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Fallback equivalence approval changed.", {})
        if (not config.feature_harness_integrations or not actor or not actor.is_active or
                actor.api_key_hash != operation["credential_binding"] or not recipient or not recipient.is_active or
                not reachable(actor, recipient) or
                not endpoint or not endpoint["enabled"] or endpoint["activation_state"] != "approved" or endpoint["revision"] != operation["endpoint_revision"] or
                endpoint["health"] == "quarantined" or
                endpoint["agent_id"] != recipient.agent_id or endpoint["workspace_id"] != operation["workspace_id"] or
                endpoint["response_policy"] != "conversation" or endpoint["consumption"] != "exclusive"):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Transport authorization changed before dispatch.", {})
        profile = self.endpoints.profile(uow, endpoint["profile_id"]) if endpoint["profile_id"] else None
        if endpoint["profile_id"] and (not profile or not profile["enabled"] or profile["revision"] != operation["profile_revision"]):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime profile changed before dispatch.", {})
        if profile and operation["runtime_session_id"] and self.endpoints.session_profile_revision(uow, operation["runtime_session_id"]) != profile["revision"]:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime must be reopened with the current approved profile.", {})
        if profile:
            validate_native_requirements(profile["config"], self.registry.get(endpoint["adapter_id"]),
                                         hitl_enabled=config.feature_hitl)
            if "conversation" in profile["config"].get("disabled_capabilities", ()):
                raise OktoNexusError(ErrorCode.CONFIG_ERROR, "Profile disables conversation transport.", {})
        if not self.registry.get(endpoint["adapter_id"]).capabilities.conversation:
            raise OktoNexusError(ErrorCode.CONFIG_ERROR, "adapter_capability_unsupported: conversation is unavailable.",
                {"reason": "adapter_capability_unsupported", "capability": "conversation"})
        return endpoint, profile

    def fallback(self, uow, *, operation):
        """Select only a new conversational operation's approved alternative.

        The caller has typed pre-write proof. This never transfers a handoff,
        relay/continuation, control or possibly accepted operation.
        """
        envelope = self.outbox.decode(operation)
        if (envelope.get("intent") != "conversation" or envelope.get("causation_id")
                or envelope.get("handoff_id") or operation.get("source_result_id")
                or operation["attempt_count"] >= 3):
            return None
        source, source_profile = self.revalidate(uow, operation=operation, config=self.config)
        if not source["selection_group"]:
            return None
        admission = (json.loads(operation["admission_binding"]) if operation.get("admission_binding") else
            {"endpoint_id": source["endpoint_id"], "revision": source["revision"], "selection_group": source["selection_group"],
             "profile_id": source["profile_id"], "profile_revision": source_profile["revision"] if source_profile else None})
        tried = self.outbox.attempted_endpoints(uow, operation_id=operation["operation_id"])
        candidates = [candidate for candidate in self.candidates(uow,
            agent_id=operation["recipient_agent_id"], workspace_id=operation["workspace_id"])
            if candidate[0]["selection_group"] == admission["selection_group"]
            and self.registry.get(candidate[0]["adapter_id"]).input_schema.get("transport_binding_contract") == 1
            and candidate[0]["endpoint_id"] not in tried]
        if not candidates:
            return None
        ready = [candidate for candidate in candidates if candidate[2]]
        candidates = ready or candidates
        priority = max(candidate[0]["priority"] for candidate in candidates)
        endpoint, profile, session = min((candidate for candidate in candidates if candidate[0]["priority"] == priority),
            key=lambda candidate: candidate[0]["endpoint_id"])
        return {"endpoint_id": endpoint["endpoint_id"], "endpoint_revision": endpoint["revision"],
            "profile_revision": profile["revision"] if profile else None, "runtime_session_id": session,
            "admission": admission}
