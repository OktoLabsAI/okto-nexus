"""Phase 2 (harness-integrations) - pure domain tests for the frozen transport port.

Exercises the vocabulary/validators in ``okto_nexus.domain.harness`` and, most
importantly, proves that each of the four real protocols characterised in
``docs/design/0004-harness-integrations.md`` (D4, D6, D7a, D7b) is EXPRESSIBLE
as a :class:`~okto_nexus.domain.harness.HarnessCapabilities` declaration and a
:class:`~okto_nexus.domain.harness.HarnessSession`/``HarnessEvent``/
``HarnessCommand`` shape. Fake native event/verb strings are used throughout
(``"harness/native_thing"``) - this module never asserts a real Pi/Codex/
Claude Code wire string, matching D2 (no native vocabulary in the domain).

Pure stdlib: no bootstrap, no sqlite, no mcp.
"""

from __future__ import annotations

import pytest

from okto_nexus.domain.harness import (
    COMMAND_VERBS,
    EVENT_KINDS,
    HARNESS_KINDS,
    SESSION_STATUSES,
    STEER_TIMING_IMMEDIATE,
    STEER_TIMING_NEXT_TURN_BOUNDARY,
    HarnessCapabilities,
    HarnessCommand,
    HarnessEvent,
    HarnessSession,
    can_transition_session,
    new_harness_session_id,
    validate_harness_kind,
    validate_session_status,
)
from okto_nexus.errors import ErrorCode, OktoNexusError


# --------------------------------------------------------------------------- #
# Vocabulary / validators
# --------------------------------------------------------------------------- #
def test_harness_kinds_closed_set() -> None:
    assert HARNESS_KINDS == {"pi", "codex", "claude_code"}


def test_validate_harness_kind_accepts_known() -> None:
    for kind in HARNESS_KINDS:
        assert validate_harness_kind(kind) == kind


def test_validate_harness_kind_rejects_unknown() -> None:
    with pytest.raises(OktoNexusError) as exc:
        validate_harness_kind("gemini_cli")
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_validate_session_status_accepts_known() -> None:
    for status in SESSION_STATUSES:
        assert validate_session_status(status) == status


def test_validate_session_status_rejects_unknown() -> None:
    with pytest.raises(OktoNexusError) as exc:
        validate_session_status("PAUSED")
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_session_transition_table_is_explicit() -> None:
    assert can_transition_session("STARTING", "RUNNING") is True
    assert can_transition_session("RUNNING", "INTERRUPTING") is True
    assert can_transition_session("INTERRUPTING", "RUNNING") is True
    assert can_transition_session("RUNNING", "ENDED") is True
    # Terminal statuses never transition anywhere.
    assert can_transition_session("ENDED", "RUNNING") is False
    assert can_transition_session("ERRORED", "RUNNING") is False
    # No skipping straight from STARTING to ENDED/INTERRUPTING.
    assert can_transition_session("STARTING", "ENDED") is False
    assert can_transition_session("STARTING", "INTERRUPTING") is False


def test_new_harness_session_id_is_prefixed_and_unique() -> None:
    a = new_harness_session_id()
    b = new_harness_session_id()
    assert a.startswith("hsess_")
    assert a != b


# --------------------------------------------------------------------------- #
# HarnessCapabilities - the control-flow-changing declaration
# --------------------------------------------------------------------------- #
def test_capabilities_send_only_requires_next_turn_boundary_steer_timing() -> None:
    """A send-only connector cannot claim IMMEDIATE steer - no channel to
    observe immediacy on. The port refuses the contradiction at construction."""
    with pytest.raises(OktoNexusError) as exc:
        HarnessCapabilities(
            send_only=True,
            steer_timing=STEER_TIMING_IMMEDIATE,
            interrupt_requires_settle_wait=False,
            multiplexes_sessions=False,
            observes_session_end=True,
        )
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_capabilities_rejects_unknown_steer_timing() -> None:
    with pytest.raises(OktoNexusError) as exc:
        HarnessCapabilities(
            send_only=False,
            steer_timing="EVENTUALLY",
            interrupt_requires_settle_wait=False,
            multiplexes_sessions=False,
            observes_session_end=True,
        )
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_capabilities_pi_shape() -> None:
    """Pi: one session per process, steer buffered to next turn boundary,
    abort->reprompt MUST wait for the aborted turn's own settle event."""
    caps = HarnessCapabilities(
        send_only=False,
        steer_timing=STEER_TIMING_NEXT_TURN_BOUNDARY,
        interrupt_requires_settle_wait=True,
        multiplexes_sessions=False,
        observes_session_end=True,
    )
    assert caps.interrupt_requires_settle_wait is True
    assert caps.multiplexes_sessions is False


def test_capabilities_codex_shape() -> None:
    """Codex: one connector connection demuxes many threadId/turnId sessions,
    turn/steer lands immediately, no settle-wait hazard on interrupt."""
    caps = HarnessCapabilities(
        send_only=False,
        steer_timing=STEER_TIMING_IMMEDIATE,
        interrupt_requires_settle_wait=False,
        multiplexes_sessions=True,
        observes_session_end=True,
    )
    assert caps.multiplexes_sessions is True
    assert caps.interrupt_requires_settle_wait is False


def test_capabilities_claude_code_primary_shape() -> None:
    """Claude Code D7a: Nexus owns the process, full duplex, one session per
    connector, no settle-wait hazard (nothing analogous to Pi's abort race)."""
    caps = HarnessCapabilities(
        send_only=False,
        steer_timing=STEER_TIMING_IMMEDIATE,
        interrupt_requires_settle_wait=False,
        multiplexes_sessions=False,
        observes_session_end=True,
    )
    assert caps.send_only is False
    assert caps.observes_session_end is True


def test_capabilities_claude_code_attach_shape() -> None:
    """Claude Code D7b (cc-socks): fire-and-forget, send-only, Nexus attaches
    to a session it did not spawn and cannot observe the end of."""
    caps = HarnessCapabilities(
        send_only=True,
        steer_timing=STEER_TIMING_NEXT_TURN_BOUNDARY,
        interrupt_requires_settle_wait=False,
        multiplexes_sessions=False,
        observes_session_end=False,
    )
    assert caps.send_only is True
    assert caps.observes_session_end is False


# --------------------------------------------------------------------------- #
# HarnessSession
# --------------------------------------------------------------------------- #
def test_harness_session_construction_valid() -> None:
    caps = HarnessCapabilities(
        send_only=False,
        steer_timing=STEER_TIMING_NEXT_TURN_BOUNDARY,
        interrupt_requires_settle_wait=True,
        multiplexes_sessions=False,
        observes_session_end=True,
    )
    session = HarnessSession(
        session_id=new_harness_session_id(),
        harness_kind="pi",
        owning_agent_id="agt_abc123",
        status="STARTING",
        capabilities=caps,
        started_at="2026-09-20T00:00:00.000000Z",
    )
    assert session.harness_kind == "pi"
    assert session.ended_at is None
    assert session.metadata == {}


def test_harness_session_rejects_unknown_kind() -> None:
    caps = HarnessCapabilities(
        send_only=False,
        steer_timing=STEER_TIMING_IMMEDIATE,
        interrupt_requires_settle_wait=False,
        multiplexes_sessions=False,
        observes_session_end=True,
    )
    with pytest.raises(OktoNexusError):
        HarnessSession(
            session_id="hsess_x",
            harness_kind="not_a_harness",
            owning_agent_id="agt_abc123",
            status="STARTING",
            capabilities=caps,
            started_at="2026-09-20T00:00:00.000000Z",
        )


def test_harness_session_observed_id_for_attach_is_not_server_minted() -> None:
    """D7b identity is OBSERVED (the peer's own pid/hash), not minted here -
    the domain must accept an externally supplied id verbatim."""
    caps = HarnessCapabilities(
        send_only=True,
        steer_timing=STEER_TIMING_NEXT_TURN_BOUNDARY,
        interrupt_requires_settle_wait=False,
        multiplexes_sessions=False,
        observes_session_end=False,
    )
    observed_id = "42.9f1c2e"  # shape of <pid>.<hash>, not our hsess_ prefix
    session = HarnessSession(
        session_id=observed_id,
        harness_kind="claude_code",
        owning_agent_id="agt_abc123",
        status="STARTING",
        capabilities=caps,
        started_at="2026-09-20T00:00:00.000000Z",
    )
    assert session.session_id == observed_id
    assert not session.session_id.startswith("hsess_")


# --------------------------------------------------------------------------- #
# HarnessEvent
# --------------------------------------------------------------------------- #
def test_event_kinds_closed_set() -> None:
    assert EVENT_KINDS == {
        "turn_started",
        "output_delta",
        "turn_completed",
        "tool_activity",
        "error",
    }


def test_harness_event_valid_construction_carries_native_name() -> None:
    event = HarnessEvent(
        session_id="hsess_x",
        harness_kind="codex",
        kind="output_delta",
        native_event="harness/native_thing",
        occurred_at="2026-09-20T00:00:00.000000Z",
        payload={"text": "hi"},
        thread_id="thr_1",
        turn_id="turn_1",
    )
    assert event.kind == "output_delta"
    assert event.native_event == "harness/native_thing"
    assert event.thread_id == "thr_1"


def test_harness_event_rejects_unknown_kind() -> None:
    with pytest.raises(OktoNexusError) as exc:
        HarnessEvent(
            session_id="hsess_x",
            harness_kind="pi",
            kind="not_a_kind",
            native_event="harness/native_thing",
            occurred_at="2026-09-20T00:00:00.000000Z",
        )
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_harness_event_requires_native_event() -> None:
    with pytest.raises(OktoNexusError):
        HarnessEvent(
            session_id="hsess_x",
            harness_kind="pi",
            kind="turn_started",
            native_event="",
            occurred_at="2026-09-20T00:00:00.000000Z",
        )


def test_harness_event_thread_turn_ids_optional_for_single_session_harnesses() -> None:
    """Pi/Claude Code have no thread/turn demux concept; None is legal."""
    event = HarnessEvent(
        session_id="hsess_x",
        harness_kind="pi",
        kind="turn_completed",
        native_event="harness/native_thing",
        occurred_at="2026-09-20T00:00:00.000000Z",
    )
    assert event.thread_id is None
    assert event.turn_id is None


# --------------------------------------------------------------------------- #
# HarnessCommand
# --------------------------------------------------------------------------- #
def test_command_verbs_closed_set() -> None:
    assert COMMAND_VERBS == {"send_turn", "steer", "interrupt", "end"}


def test_harness_command_valid_construction() -> None:
    command = HarnessCommand(session_id="hsess_x", verb="send_turn", payload={"text": "go"})
    assert command.verb == "send_turn"
    assert command.payload == {"text": "go"}


def test_harness_command_rejects_unknown_verb() -> None:
    with pytest.raises(OktoNexusError) as exc:
        HarnessCommand(session_id="hsess_x", verb="teleport")
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_harness_command_default_payload_is_empty_dict() -> None:
    command = HarnessCommand(session_id="hsess_x", verb="end")
    assert command.payload == {}
