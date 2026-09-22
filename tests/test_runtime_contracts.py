"""P02 contracts: honest outcomes, no privilege/capability escalation."""
from dataclasses import replace

import pytest

from okto_nexus.application.adapter_registry import AdapterDescriptor, AdapterRegistry
from okto_nexus.domain.delivery import DeliveryEnvelope, DispatchResult, validate_operation_transition
from okto_nexus.domain.endpoints import AgentEndpoint, EndpointCapabilities
from okto_nexus.errors import OktoNexusError
from okto_nexus.adapters.outbound.harness.envelope import EnvelopeConnector
from okto_nexus.domain.harness import HarnessCommand
from test_harness_tools import FakeConnector


def envelope(**kwargs):
    return DeliveryEnvelope(operation_id="op1", sender_agent_id="sender", recipient_agent_id="recipient",
        workspace_id="workspace", root_operation_id="root", intent="conversation",
        content=({"type": "text", "text": "untrusted text"},), **kwargs)


def test_envelope_serialization_keeps_identity_and_stable_hash():
    value = envelope(subject="subject", message_id="message")
    assert value.to_dict()["sender_agent_id"] == "sender"
    assert value.to_dict()["trust"] == "untrusted_content"
    assert value.request_hash() == replace(value).request_hash()
    assert replace(value, subject="changed").request_hash() != value.request_hash()


def test_work_requires_claim_and_cannot_upgrade_content_trust():
    with pytest.raises(OktoNexusError):
        replace(envelope(), intent="handoff_execute")
    with pytest.raises(OktoNexusError):
        replace(envelope(), trust="system")


@pytest.mark.parametrize("outcome", ["UNKNOWN", "SENT_UNCONFIRMED", "ACCEPTED"])
def test_transport_uncertainty_does_not_allow_automatic_retry(outcome):
    with pytest.raises(OktoNexusError):
        DispatchResult(outcome, safe_to_retry=True, retry_basis="timeout")


def test_write_is_not_acceptance_and_no_unsafe_state_retry():
    with pytest.raises(OktoNexusError):
        DispatchResult("ACCEPTED", ack_level="TRANSPORT_WRITE")
    with pytest.raises(OktoNexusError):
        validate_operation_transition("OUTCOME_UNKNOWN", "PENDING")
    result = DispatchResult("NOT_SENT", safe_to_retry=True, retry_basis="BEFORE_WRITE")
    assert result.safe_to_retry


def test_capability_intersection_never_removes_settle_requirement():
    native = EndpointCapabilities(conversation=True, interrupt=True, interrupt_requires_settle=True)
    profile = EndpointCapabilities(conversation=True, native_deduplication=True, interrupt=True)
    effective = native.restrict(profile)
    assert effective.interrupt_requires_settle
    assert not effective.native_deduplication
    assert effective.conversation


def test_endpoint_has_exact_scope_and_does_not_default_enabled():
    endpoint = AgentEndpoint("endpoint", "agent", "test.peer", "ws", "fixture")
    assert not endpoint.enabled
    with pytest.raises(OktoNexusError):
        replace(endpoint, workspace_id="*")


def test_registry_uses_local_factory_and_rejects_duplicates_and_versions():
    registry = AdapterRegistry()
    descriptor = AdapterDescriptor("additional", "additional", None, "fixture", lambda: None,
                                   lambda _: None, EndpointCapabilities(), FakeConnector().capabilities)
    registry.register(descriptor)
    assert registry.resolve("additional") is descriptor
    with pytest.raises(OktoNexusError):
        registry.register(descriptor)
    with pytest.raises(OktoNexusError):
        registry.register(replace(descriptor, adapter_id="next", kind="next", contract_version=2))


@pytest.mark.parametrize("key", ["text", "content"])
def test_adapter_owns_native_envelope_translation(key):
    native = FakeConnector()
    adapter = EnvelopeConnector(native, payload_key=key)
    session = adapter.start(owning_agent_id="recipient")
    adapter.send(session, HarnessCommand(session_id=session.session_id, verb="send_turn",
                                        payload={"envelope": envelope().to_dict()}))
    assert list(native.sent[0].payload) == [key]
    assert '"sender_agent_id": "sender"' in native.sent[0].payload[key]
    assert "untrusted" in native.sent[0].payload[key]
    adapter.close()
