"""Contract tests. A valid document does not authorize runtime execution."""

import pytest
from pydantic import ValidationError

from okto_nexus.adapters.inbound.http.session_interaction_contract import (
    EnqueueInput,
    InputReceipt,
    InterruptInput,
    PrepareAttachment,
    PromoteInput,
    SteerInput,
)
from okto_nexus.domain.session_interaction import (
    InputDeliveryState,
    may_cancel,
    may_dispatch,
    may_promote,
)


@pytest.fixture
def wire():
    return {
        "scope": {
            "server_id": "server", "executor_id": "executor", "binding_id": "binding",
            "workspace_id": "workspace", "workspace_binding_id": "workspace-binding",
            "agent_id": "recipient", "session_id": "session",
        },
        "expected_session_generation": 17,
        "capability_revision": "revision-1",
    }


def test_input_requires_exact_fence_and_preserves_content(wire):
    body = dict(wire, client_intent_id="ui-1", content=[{"type": "text", "text": "  Preserve whitespace.  "}])
    request = EnqueueInput.model_validate(body)
    assert request.mode == "next_turn"
    assert request.scope.session_key().executor_id == "executor"
    assert request.owner_generation().value == 17
    assert request.content[0].text == "  Preserve whitespace.  "
    for name in type(request.scope).model_fields:
        other = dict(body, scope={k: v for k, v in body["scope"].items() if k != name})
        with pytest.raises(ValidationError):
            EnqueueInput.model_validate(other)


@pytest.mark.parametrize("patch", [
    {"actor_agent_id": "operator"},
    {"surface": "native_terminal"},
    {"expected_session_generation": True},
    {"mode": "steer"},
    {"content": [{"type": "text", "text": " "}]},
    {"content": [{"type": "text", "text": "é" * 32769}]},
    {"content": [{"type": "text", "text": "\ud800"}]},
    {"content": [{"type": "shell", "text": "echo kept as data"}]},
])
def test_enqueue_rejects_authority_spoofing_or_ambiguous_content(wire, patch):
    body = dict(wire, client_intent_id="ui-1", content=[{"type": "text", "text": "Hello"}])
    body.update(patch)
    with pytest.raises(ValidationError):
        EnqueueInput.model_validate(body)


def test_interrupt_and_promote_require_exact_target_and_cas(wire):
    target = {"kind": "native_turn", "turn_id": "turn-1"}
    with pytest.raises(ValidationError):
        InterruptInput.model_validate(dict(wire, client_intent_id="control-1", expected_queue_revision=1))
    with pytest.raises(ValidationError):
        PromoteInput.model_validate(dict(wire, expected_queue_revision=1, target=target,
                                         confirmed_effect_revision="review-1"))
    request = PromoteInput.model_validate(dict(wire, expected_queue_revision=1, expected_input_revision=2,
                                               target=target, confirmed_effect_revision="review-1"))
    assert request.target.turn_id == "turn-1"
    assert request.expected_input_revision == 2


def test_steer_is_separate_and_requires_a_reviewed_effect(wire):
    body = dict(wire, client_intent_id="control-2", content=[{"type": "text", "text": "Check the race."}],
                target={"kind": "observed_run", "run_ref": "run-1"})
    with pytest.raises(ValidationError):
        SteerInput.model_validate(body)
    with pytest.raises(ValidationError):
        EnqueueInput.model_validate(body)
    reviewed = SteerInput.model_validate(dict(body, confirmed_effect_revision="review"))
    assert reviewed.target.run_ref == "run-1"
    with pytest.raises(ValidationError):
        SteerInput.model_validate(dict(body, confirmed_effect_revision="review", target={"kind": "current_run"}))


def test_attachment_intent_cannot_pick_latest_or_override_host_or_token(wire):
    body = dict(wire, client_intent_id="attach-1", intent="attach_live", access="write")
    assert PrepareAttachment.model_validate(body).intent == "attach_live"
    for patch in ({"intent": "resume_latest"}, {"bearer": "client-token"}, {"host": "override"}):
        with pytest.raises(ValidationError):
            PrepareAttachment.model_validate(dict(body, **patch))


def test_unknown_receipt_requires_exact_link_and_retains_possible_effect(wire):
    body = {
        "scope": wire["scope"], "session_owner_generation": 17, "input_id": "input-1", "enqueue_sequence": 1,
        "input_revision": 2, "queue_revision": 3, "status": InputDeliveryState.DELIVERY_UNKNOWN,
        "operation_id": "operation-1", "possible_effect": True,
    }
    assert InputReceipt.model_validate(body).operation_id == "operation-1"
    for patch in ({"operation_id": None}, {"possible_effect": False}, {"status": InputDeliveryState.CANCELLED}):
        with pytest.raises(ValidationError):
            InputReceipt.model_validate(dict(body, **patch))


@pytest.mark.parametrize("state", [
    InputDeliveryState.DISPATCHING,
    InputDeliveryState.ACCEPTED_NATIVE,
    InputDeliveryState.DELIVERY_UNKNOWN,
    InputDeliveryState.REFUSED_BEFORE_SEND,
])
def test_an_admitted_or_uncertain_entry_is_not_ordinary_queue_work(state):
    assert not may_dispatch(state)
    assert not may_cancel(state)
    assert not may_promote(state)
