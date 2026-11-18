"""Processless scripts for session tests. These signals are fixture inputs only."""

from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from okto_nexus.domain.execution.keys import SessionKey, SessionOwnerGeneration


@dataclass(frozen=True, slots=True)
class PeerSession:
    key: SessionKey
    generation: SessionOwnerGeneration


@dataclass(frozen=True, slots=True)
class PeerTurn:
    session: PeerSession
    operation_id: str
    turn_id: str


class PeerReply(StrEnum):
    BUSY = "busy"
    ACK = "ack"
    WAITING_FOR_ANSWER = "waiting_for_answer"


@dataclass(frozen=True, slots=True)
class PeerSignal:
    turn: PeerTurn
    kind: Literal["model_end", "settled"]


@dataclass(frozen=True, slots=True)
class PeerQuestion:
    turn: PeerTurn
    request_id: str
    kind: Literal["tool_approval", "human_input"]
    prompt: str


@dataclass(frozen=True, slots=True)
class PeerText:
    """A fragment from one exact session's stream, with its turn and item references."""

    operation_id: str
    turn_id: str
    event_id: str
    item_id: str
    kind: Literal["user_echo", "delta", "snapshot"]
    text: str


@dataclass
class _ScriptState:
    pending: tuple[PeerTurn, Future[PeerReply]] | None = None
    active: PeerTurn | None = None
    question: PeerQuestion | None = None
    signals: list[PeerSignal | PeerQuestion | PeerText] = field(default_factory=list)


class ScriptedPeer:
    """Advance writes and observe boundaries explicitly, without clocks or subprocesses."""

    def __init__(self, *sessions: PeerSession):
        if len({session.key for session in sessions}) != len(sessions):
            raise ValueError("a session key may have only one scripted generation")
        self._sessions = {session: _ScriptState() for session in sessions}
        self._accepted: list[PeerTurn] = []

    @property
    def accepted(self) -> tuple[PeerTurn, ...]:
        """Fixture instrumentation. Never pass this history in as a remote receipt."""
        return tuple(self._accepted)

    def dispatch(self, turn: PeerTurn, *, defer_ack: bool = False) -> Future[PeerReply]:
        state = self._sessions[turn.session]
        reply: Future[PeerReply] = Future()
        if state.question is not None:
            reply.set_result(PeerReply.WAITING_FOR_ANSWER)
            return reply
        if state.pending is not None or state.active is not None:
            reply.set_result(PeerReply.BUSY)
            return reply
        reply.set_running_or_notify_cancel()
        state.pending = (turn, reply)
        if not defer_ack:
            self.release_ack(turn)
        return reply

    def release_ack(self, turn: PeerTurn, *, lose_reply: bool = False) -> None:
        """Accept the scripted write, then release its ACK or simulate losing the response."""
        state = self._sessions[turn.session]
        if state.pending is None or state.pending[0] != turn:
            raise ValueError("no deferred reply for this exact turn")
        _, reply = state.pending
        state.pending = None
        state.active = turn
        self._accepted.append(turn)
        if lose_reply:
            reply.set_exception(ConnectionError("scripted peer reply lost"))
        else:
            reply.set_result(PeerReply.ACK)

    def note_model_end(self, turn: PeerTurn) -> None:
        """Emit an intermediate signal while the peer is still processing."""
        self._active_state(turn).signals.append(PeerSignal(turn, "model_end"))

    def note_question(self, question: PeerQuestion) -> None:
        state = self._active_state(question.turn)
        if state.question is not None:
            raise ValueError("a scripted question is already pending")
        state.question = question
        state.signals.append(question)

    def confirm_answer(self, question: PeerQuestion) -> None:
        """Advance a synthetic question after external confirmation by the test."""
        state = self._active_state(question.turn)
        if state.question != question:
            raise ValueError("no matching pending question")
        state.question = None

    def note_text(self, turn: PeerTurn, *, event_id: str, item_id: str,
                  kind: Literal["user_echo", "delta", "snapshot"], text: str) -> None:
        self._active_state(turn).signals.append(
            PeerText(turn.operation_id, turn.turn_id, event_id, item_id, kind, text)
        )

    def settle(self, turn: PeerTurn) -> None:
        state = self._active_state(turn)
        if state.question is not None:
            raise ValueError("a scripted question is still pending")
        state.active = None
        state.signals.append(PeerSignal(turn, "settled"))

    def drain_signals(self, session: PeerSession) -> tuple[PeerSignal | PeerQuestion | PeerText, ...]:
        signals = self._sessions[session].signals
        observed = tuple(signals)
        signals.clear()
        return observed

    def _active_state(self, turn: PeerTurn) -> _ScriptState:
        state = self._sessions[turn.session]
        if state.active != turn:
            raise ValueError("no active write for this exact turn")
        return state
