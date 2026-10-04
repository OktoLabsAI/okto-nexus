"""Minimal canonical identity projection for an authorized runtime delivery.

This is context, not a principal or an authentication mechanism. Callers must
authorize the operation before projecting it and revalidate before transport.
No metadata, credential, private policy, path or native configuration is copied.
"""
from ..domain.routing import normalize_capabilities
from ..errors import ErrorCode, OktoNexusError
import json


def delivery_prompt(envelope):
    """Render Nexus tool context; retain transport trust metadata in storage only."""
    context = dict(envelope)
    context.pop("trust", None)
    return ("NEXUS DELIVERY: respond to the sender's request using your available capabilities.\n"
            + json.dumps(context, ensure_ascii=False, sort_keys=True))


def delivery_context(uow, *, agents, endpoint, profile, intent):
    agent = agents.get(uow, endpoint["agent_id"])
    if not agent or not agent.is_active:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Runtime identity is unavailable.", {})
    return {
        "schema_version": 1,
        "agent": {"agent_id": agent.agent_id, "role": agent.role,
                  "capabilities": sorted(normalize_capabilities(agent.capabilities))},
        "workspace_id": endpoint["workspace_id"],
        "endpoint_id": endpoint["endpoint_id"],
        "execution_profile": {"profile_id": profile["profile_id"], "revision": profile["revision"]} if profile else None,
        "intent": intent,
        "completion": {"automatic_on_turn_end": False,
                       "mode": "authenticated_nexus_call" if intent == "handoff_execute" else "conversation_only"},
        "instructions": (
            "Use the agent identity above for Nexus interactions. "
            "Use operation_id and workspace_id to correlate this delivery. "
            "The session provides authenticated Nexus tools for interacting with Nexus. "
            "Respond to the sender's request using your available capabilities. "
            + ("For this handoff, use the supplied handoff_id and claim_epoch. "
               "Record completion or rejection through the corresponding Nexus tool, preserving the claim epoch."
               if intent == "handoff_execute" else
               "For handoffs, use the Nexus retrieval, claim and completion tools and the returned claim epoch. "
               "Use the Nexus messaging tools to communicate with other agents when available. "
               "Your final conversational response is returned to the sender by Nexus.")
        ),
    }
