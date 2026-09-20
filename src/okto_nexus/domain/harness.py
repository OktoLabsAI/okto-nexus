"""Pure domain types for the harness-integrations shared transport port.

This module is the FROZEN interface every harness connector (pi, codex,
Claude Code) implements (see ``docs/design/0004-harness-integrations.md``,
decision D2). It is deliberately the ONLY place in ``domain/`` that knows a
harness supervisor exists; no connector, adapter or migration is defined
here or anywhere yet (Phase 2 of ``plans/harness-integrations/00-plan.md``
lands this port ALONE, before any adapter is written).

Per-harness native envelopes (Pi's ``{"type":"response",...}``, Codex's
JSON-RPC ``thread/start``/``turn/steer``, Claude Code's stream-json events,
``cc-socks`` NDJSON) are translated at the ADAPTER edge. Nothing in this
module contains a native verb, method name or event name as a constant or
enum member - :class:`HarnessEvent.native_event` and
:class:`HarnessCommand.verb`'s value are opaque strings the domain never
inspects, only carries for traceability (D2; D4; D6; D7).

Four real protocols shape this port and each stresses a different axis:

* **Pi** - one session per child process; steering only lands at the NEXT
  TURN BOUNDARY, never instantly; interrupt is abort-then-reprompt, and the
  reprompt must wait for the aborted turn's own settle event.
* **Codex** - one connector process multiplexes MANY concurrent sessions
  (``threadId`` + ``turnId`` demuxing on one stdio pipe); steering can land
  mid-turn.
* **Claude Code (primary, D7a)** - one long-lived process per session, many
  turns, full request/response duplex.
* **Claude Code (attach, D7b)** - ``cc-socks`` injection into a session
  Nexus did not spawn and cannot observe the end of. Fire-and-forget:
  SEND-ONLY, no synchronous ack, no correlated response on this channel.

The capability fields on :class:`HarnessCapabilities` exist because these
differences change what the SUPERVISOR must do (never await a reply on a
send-only channel; wait for a settle event before reprompting after an
interrupt), not merely to document trivia. Only capabilities that change
control flow are modelled; see the module docstring in
``application/ports.py`` for how :class:`HarnessConnector` consumes them.

Pure module: stdlib only, no ``sqlite3``/``mcp`` (enforced by the import
boundary test).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..errors import ErrorCode, OktoNexusError
from .base import new_id

__all__ = [
    "HARNESS_KINDS",
    "SESSION_STATUSES",
    "TERMINAL_SESSION_STATUSES",
    "STEER_TIMING_IMMEDIATE",
    "STEER_TIMING_NEXT_TURN_BOUNDARY",
    "STEER_TIMINGS",
    "EVENT_KINDS",
    "COMMAND_VERBS",
    "new_harness_session_id",
    "validate_harness_kind",
    "validate_session_status",
    "can_transition_session",
    "HarnessCapabilities",
    "HarnessSession",
    "HarnessEvent",
    "HarnessCommand",
]


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
#: The closed set of harness kinds this port is frozen against. New harnesses
#: extend this set (and get their own connector); the port shape itself does
#: not change.
HARNESS_KINDS: frozenset[str] = frozenset({"pi", "codex", "claude_code"})

STATUS_STARTING = "STARTING"
STATUS_RUNNING = "RUNNING"
STATUS_INTERRUPTING = "INTERRUPTING"
STATUS_ENDED = "ENDED"
STATUS_ERRORED = "ERRORED"

#: Lifecycle vocabulary for :class:`HarnessSession.status`. ``STARTING`` is
#: the pre-first-turn-boundary state; ``INTERRUPTING`` exists because Pi's
#: abort does not settle synchronously (a reprompt issued while
#: ``INTERRUPTING`` must wait, not race, the aborted turn's own settle
#: event - D4). ``ENDED``/``ERRORED`` are terminal.
SESSION_STATUSES: frozenset[str] = frozenset(
    {STATUS_STARTING, STATUS_RUNNING, STATUS_INTERRUPTING, STATUS_ENDED, STATUS_ERRORED}
)
TERMINAL_SESSION_STATUSES: frozenset[str] = frozenset({STATUS_ENDED, STATUS_ERRORED})

#: The V1 transition table. Any pair not listed is an ``INVALID_TRANSITION``.
#: A connector that cannot observe a session's end at all (D7b/``cc-socks``,
#: attached to a session Nexus did not spawn) never drives this table past
#: ``STARTING`` -> ``RUNNING``; it has no producer for ``ENDED`` and must not
#: fabricate one (see the module docstring's cc-socks note).
_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (STATUS_STARTING, STATUS_RUNNING),
        (STATUS_STARTING, STATUS_ERRORED),
        (STATUS_RUNNING, STATUS_INTERRUPTING),
        (STATUS_RUNNING, STATUS_ENDED),
        (STATUS_RUNNING, STATUS_ERRORED),
        (STATUS_INTERRUPTING, STATUS_RUNNING),
        (STATUS_INTERRUPTING, STATUS_ENDED),
        (STATUS_INTERRUPTING, STATUS_ERRORED),
    }
)

STEER_TIMING_IMMEDIATE = "IMMEDIATE"
STEER_TIMING_NEXT_TURN_BOUNDARY = "NEXT_TURN_BOUNDARY"

#: Closed vocabulary for :attr:`HarnessCapabilities.steer_timing`. This is the
#: one Pi-vs-Codex asymmetry the task calls out explicitly: Pi steering is
#: only visible at the next turn boundary; Codex ``turn/steer`` can land
#: mid-turn. The supervisor branches on this value, so it is load-bearing,
#: not documentation.
STEER_TIMINGS: frozenset[str] = frozenset(
    {STEER_TIMING_IMMEDIATE, STEER_TIMING_NEXT_TURN_BOUNDARY}
)

#: The closed set of normalised inbound event kinds. Native per-harness event
#: names (``item/agentMessage/delta``, ``turn.completed``, ...) are carried
#: verbatim in :attr:`HarnessEvent.native_event`, never here.
EVENT_KINDS: frozenset[str] = frozenset(
    {
        "turn_started",
        "output_delta",
        "turn_completed",
        "tool_activity",
        "error",
    }
)

#: The closed set of normalised outbound command verbs. A connector whose
#: capabilities declare ``steer_timing=None`` MUST reject ``steer``; the
#: D7b (``cc-socks``) shape additionally has no interrupt-with-settle
#: semantics and no correlated end signal, so in practice it accepts only
#: ``send_turn`` at the adapter edge - a fact read off
#: :class:`HarnessCapabilities`, never hardcoded per verb here.
COMMAND_VERBS: frozenset[str] = frozenset({"send_turn", "steer", "interrupt", "end"})


def new_harness_session_id() -> str:
    """Return a fresh server-minted session id (``hsess_`` + 32 hex chars).

    Uses the shared :func:`~okto_nexus.domain.base.new_id` minting helper, the
    same one every other slice's id uses. NOT used for D7b (``cc-socks``)
    attach sessions, whose identity is OBSERVED (the peer's own
    ``<pid>.<hash>``), not minted by Nexus - see :class:`HarnessSession`.
    """
    return new_id("hsess")


def validate_harness_kind(kind: Any) -> str:
    """Return ``kind`` if it is one of :data:`HARNESS_KINDS`.

    Raises ``VALIDATION_ERROR`` (canonical catalogue code) otherwise.
    """
    if isinstance(kind, str) and kind in HARNESS_KINDS:
        return kind
    raise OktoNexusError(
        ErrorCode.VALIDATION_ERROR,
        "harness kind must be one of {pi, codex, claude_code}.",
        {"kind": kind, "supported": sorted(HARNESS_KINDS)},
    )


def validate_session_status(status: Any) -> str:
    """Return ``status`` if it is one of :data:`SESSION_STATUSES`.

    Raises ``VALIDATION_ERROR`` (canonical catalogue code) otherwise.
    """
    if isinstance(status, str) and status in SESSION_STATUSES:
        return status
    raise OktoNexusError(
        ErrorCode.VALIDATION_ERROR,
        "harness session status must be one of "
        "{STARTING, RUNNING, INTERRUPTING, ENDED, ERRORED}.",
        {"status": status, "supported": sorted(SESSION_STATUSES)},
    )


def can_transition_session(current: str, target: str) -> bool:
    """Return whether ``current`` -> ``target`` is a legal lifecycle move.

    Mirrors :func:`okto_nexus.domain.handoff.can_transition`'s shape: a pure
    membership check against the explicit V1 table, no side effects. Any pair
    outside the table (including the terminal statuses transitioning
    anywhere) is illegal.
    """
    return (current, target) in _TRANSITIONS


# --------------------------------------------------------------------------- #
# Capability declaration
# --------------------------------------------------------------------------- #
@dataclass(slots=True, frozen=True)
class HarnessCapabilities:
    """What a connector's transport can and cannot do - the control-flow axes.

    Every field here changes what the supervisor must DO, not merely what it
    documents (see the module docstring). A connector that gets one of these
    wrong produces a broken supervisor, not just an inaccurate label:

    * ``send_only=True`` (D7b, ``cc-socks``): the supervisor must NEVER wait
      for a correlated response to a sent command. There is no ack channel;
      inbound replies (if any) arrive later through the session's own
      ordinary event stream, not as a reply to this send.
    * ``steer_timing``: ``NEXT_TURN_BOUNDARY`` (Pi) means a ``steer`` command
      issued mid-turn is buffered by the harness, not applied immediately;
      the supervisor must not assume the very next event reflects it.
      ``IMMEDIATE`` (Codex ``turn/steer``) has no such delay. ``None`` means
      steering is UNSUPPORTED on this transport at all (D7b, ``cc-socks``:
      fire-and-forget has no channel to deliver a mid-session steer over) -
      the supervisor's "may I steer this session?" question is answered
      entirely from this one field, with no out-of-band knowledge of
      ``send_only`` required.
    * ``interrupt_requires_settle_wait``: Pi's ``abort`` does not resolve
      synchronously - a reprompt sent right after MUST wait for the aborted
      turn's own settle event first, or it races the harness's internal
      teardown (D4). Codex's ``turn/interrupt`` has no equivalent hazard.
    * ``multiplexes_sessions``: Codex demuxes many concurrent
      ``threadId``/``turnId`` pairs over ONE connector connection; Pi and
      Claude Code are one session per connector instance. A connector that
      declares ``False`` here owns exactly one :class:`HarnessSession` for
      its lifetime.
    * ``observes_session_end``: ``False`` for D7b - Nexus injects into a
      session it did not spawn and has no channel to learn when it ends.
      Such a connector's :class:`HarnessSession` may never legally reach
      ``ENDED``; it is abandoned by the peer, not transitioned.
    """

    send_only: bool
    steer_timing: str | None
    interrupt_requires_settle_wait: bool
    multiplexes_sessions: bool
    observes_session_end: bool

    def __post_init__(self) -> None:
        if self.steer_timing is not None and self.steer_timing not in STEER_TIMINGS:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "steer_timing must be one of {IMMEDIATE, NEXT_TURN_BOUNDARY} or None "
                "(None = steering unsupported on this transport).",
                {"steer_timing": self.steer_timing, "supported": sorted(STEER_TIMINGS)},
            )


# --------------------------------------------------------------------------- #
# Session / event / command
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class HarnessSession:
    """A live (or ended) harness-connector session - NOT persisted (no table).

    Durability of harness activity is via :class:`HarnessEvent` rows written
    for record-keeping only (D1: the SQLite write is durability, never the
    notification path); ``HarnessSession`` itself is the supervisor's
    in-memory bookkeeping record and is never queried from storage.

    ``session_id`` is normally server-minted (:func:`new_harness_session_id`).
    The one exception is a D7b (``cc-socks``) attach session: its identity is
    OBSERVED from the peer's own registry
    (``~/.claude/sessions/<pid>.<hash>.key``), so the adapter passes that
    discovered id straight through rather than minting a new one - Nexus does
    not own that namespace and must not invent a competing one.
    """

    session_id: str
    harness_kind: str
    owning_agent_id: str
    status: str
    capabilities: HarnessCapabilities
    started_at: str
    ended_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_harness_kind(self.harness_kind)
        validate_session_status(self.status)


@dataclass(slots=True, frozen=True)
class HarnessEvent:
    """A normalised INBOUND event from any harness, translated at the adapter edge.

    ``kind`` is the closed, harness-agnostic vocabulary (:data:`EVENT_KINDS`)
    the domain and application layers reason about. ``native_event`` carries
    the harness's own name for the SAME occurrence verbatim (e.g.
    ``"item/agentMessage/delta"``, ``"turn.completed"``,
    ``"assistant_message"``) purely for traceability/debugging - the domain
    never branches on it, only stores and forwards it (D2: no native
    vocabulary leaks INTO decision logic here).

    ``thread_id``/``turn_id`` are optional because they are meaningful for
    Codex's demuxed-connection shape and largely vestigial for Pi/Claude
    Code's one-session-per-process shape; left ``None`` where the harness has
    no equivalent rather than synthesising one.
    """

    session_id: str
    harness_kind: str
    kind: str
    native_event: str
    occurred_at: str
    payload: dict[str, Any] = field(default_factory=dict)
    thread_id: str | None = None
    turn_id: str | None = None

    def __post_init__(self) -> None:
        validate_harness_kind(self.harness_kind)
        if self.kind not in EVENT_KINDS:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "harness event kind must be one of "
                "{turn_started, output_delta, turn_completed, tool_activity, error}.",
                {"kind": self.kind, "supported": sorted(EVENT_KINDS)},
            )
        if not self.native_event:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "native_event must be a non-empty string (traceability field).",
                {"native_event": self.native_event},
            )


@dataclass(slots=True, frozen=True)
class HarnessCommand:
    """A normalised OUTBOUND command to a harness session.

    ``verb`` is the closed vocabulary (:data:`COMMAND_VERBS`); per-harness
    translation (``{"type":"abort"}`` for Pi, ``turn/interrupt`` for Codex,
    ...) happens entirely at the adapter that consumes this value. A
    send-only connector (D7b) only ever receives ``verb="send_turn"`` - the
    supervisor is responsible for never constructing ``steer``/``interrupt``/
    ``end`` against a session whose :class:`HarnessCapabilities.send_only` is
    ``True``; this dataclass does not itself know which session it targets a
    capability against; callers validate that at the point they hold both.
    """

    session_id: str
    verb: str
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.verb not in COMMAND_VERBS:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "harness command verb must be one of "
                "{send_turn, steer, interrupt, end}.",
                {"verb": self.verb, "supported": sorted(COMMAND_VERBS)},
            )
