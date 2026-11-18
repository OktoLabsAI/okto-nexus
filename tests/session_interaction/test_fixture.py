"""Exercise the script's identity and boundary gates in isolation."""

from dataclasses import replace

import pytest
from nexus_connector_core.native.event_buffers import (
    NativeEventOverflow,
    NativeEventQueue,
    event_bytes,
)

from okto_nexus.domain.execution.keys import SessionKey, SessionOwnerGeneration
from tests.session_interaction.fixtures import (
    PeerQuestion,
    PeerReply,
    PeerSession,
    PeerSignal,
    PeerText,
    PeerTurn,
    ScriptedPeer,
)


@pytest.fixture
def peer_turns():
    left = PeerSession(SessionKey("fixture-server", "left-host", "shared-session"), SessionOwnerGeneration(2))
    right = PeerSession(SessionKey("fixture-server", "right-host", "shared-session"), SessionOwnerGeneration(1))
    first = PeerTurn(left, "operation-left", "shared-turn")
    other = PeerTurn(right, "operation-right", "shared-turn")
    return ScriptedPeer(left, right), first, other


def test_acknowledgement_and_model_end_leave_the_exact_session_busy(peer_turns):
    peer, first, other = peer_turns
    left, right = first.session, other.session
    following = PeerTurn(left, "operation-next", "next-turn")

    deferred = peer.dispatch(first, defer_ack=True)
    assert not deferred.done()
    assert peer.accepted == ()
    assert peer.dispatch(following).result(timeout=0) is PeerReply.BUSY
    lost = peer.dispatch(other, defer_ack=True)
    peer.release_ack(other, lose_reply=True)
    with pytest.raises(ConnectionError, match="scripted peer reply lost"):
        lost.result(timeout=0)
    assert peer.accepted == (other,)
    assert peer.dispatch(other).result(timeout=0) is PeerReply.BUSY

    peer.release_ack(first)
    assert deferred.result(timeout=0) is PeerReply.ACK
    peer.note_model_end(first)
    assert peer.drain_signals(left) == (PeerSignal(first, "model_end"),)
    assert peer.drain_signals(right) == ()
    assert peer.dispatch(following).result(timeout=0) is PeerReply.BUSY

    with pytest.raises(ValueError, match="exact turn"):
        peer.settle(replace(first, session=right))
    stale = replace(left, generation=SessionOwnerGeneration(1))
    with pytest.raises(KeyError):
        peer.settle(replace(first, session=stale))
    peer.settle(other)
    assert peer.drain_signals(right) == (PeerSignal(other, "settled"),)
    assert peer.dispatch(following).result(timeout=0) is PeerReply.BUSY

    peer.settle(first)
    assert peer.drain_signals(left) == (PeerSignal(first, "settled"),)
    assert peer.dispatch(following).result(timeout=0) is PeerReply.ACK
    assert peer.accepted == (other, first, following)


def test_answers_clear_only_the_exact_pending_question(peer_turns):
    peer, first, other = peer_turns
    following = replace(first, operation_id="operation-next", turn_id="next-turn")
    for turn in (first, other):
        assert peer.dispatch(turn).result(timeout=0) is PeerReply.ACK
    approval = PeerQuestion(first, "shared-request", "tool_approval", "Approve the fixture tool?")
    question = PeerQuestion(other, "shared-request", "human_input", "Supply the fixture value.")
    peer.note_question(approval)
    peer.note_question(question)

    assert peer.drain_signals(first.session) == (approval,)
    assert peer.drain_signals(other.session) == (question,)
    peer.confirm_answer(question)
    with pytest.raises(ValueError, match="no matching pending question"):
        peer.confirm_answer(replace(approval, request_id="other-request"))
    assert peer.dispatch(following).result(timeout=0) is PeerReply.WAITING_FOR_ANSWER
    with pytest.raises(ValueError, match="still pending"):
        peer.settle(first)

    peer.confirm_answer(approval)
    assert peer.dispatch(following).result(timeout=0) is PeerReply.BUSY
    peer.settle(first)
    assert peer.dispatch(following).result(timeout=0) is PeerReply.ACK


def test_transcript_keeps_both_event_and_item_identity(peer_turns):
    peer, first, other = peer_turns
    for turn in (first, other):
        assert peer.dispatch(turn).result(timeout=0) is PeerReply.ACK
        peer.note_text(turn, event_id="event-1", item_id="user-item", kind="user_echo", text="Check status")
    peer.note_text(first, event_id="event-2", item_id="answer-item", kind="delta", text="All ")
    peer.note_text(first, event_id="event-3", item_id="answer-item", kind="snapshot", text="All clear")
    peer.note_text(first, event_id="event-4", item_id="answer-item", kind="delta", text=".")

    assert peer.drain_signals(first.session) == (
        PeerText(first.operation_id, first.turn_id, "event-1", "user-item", "user_echo", "Check status"),
        PeerText(first.operation_id, first.turn_id, "event-2", "answer-item", "delta", "All "),
        PeerText(first.operation_id, first.turn_id, "event-3", "answer-item", "snapshot", "All clear"),
        PeerText(first.operation_id, first.turn_id, "event-4", "answer-item", "delta", "."),
    )
    assert peer.drain_signals(other.session) == (
        PeerText(other.operation_id, other.turn_id, "event-1", "user-item", "user_echo", "Check status"),
    )


def test_slow_subscriber_hits_core_byte_bound_while_fixture_keeps_producing(peer_turns):
    peer, first, _ = peer_turns
    assert peer.dispatch(first).result(timeout=0) is PeerReply.ACK
    text = "é" * 16384
    example = PeerText(first.operation_id, first.turn_id, "0", "answer-item", "delta", text)
    slow = NativeEventQueue(max_events=16, max_bytes=2 * event_bytes(example))
    delivered = []
    for seq in range(8):
        peer.note_text(first, event_id=str(seq), item_id="answer-item", kind="delta", text=text)
        fragment, = peer.drain_signals(first.session)
        delivered.append(slow.put(fragment))
    peer.settle(first)

    assert delivered == [True, True, False, False, False, False, False, False]
    assert slow.get(timeout=0) == example
    assert slow.get(timeout=0) == replace(example, event_id="1")
    with pytest.raises(NativeEventOverflow):
        slow.get(timeout=0)
    assert peer.drain_signals(first.session) == (PeerSignal(first, "settled"),)
