"""Claude Code PRIMARY connector: ``claude -p`` stream-json (ADR 0004 D7a).

Implements :class:`~okto_nexus.application.ports.HarnessConnector` for the
supported, Nexus-owned Claude Code session:

    claude -p --output-format stream-json --input-format stream-json \\
        --verbose --include-partial-messages

This is the STABLE FLOOR of the Claude Code integration (ADR 0004 D7): if the
undocumented ``cc-socks`` attach substrate (D7b) breaks on a Claude Code
release, this connector must keep working, because it only depends on
documented, supported CLI flags. Robustness is therefore the priority over
feature completeness.

Every behavioural claim below was verified empirically against the real
``claude`` 2.1.278 binary (see the report accompanying this module's
delivery); nothing here is inferred from documentation, because none exists
for this exact input/output wire shape beyond the flag reference.

Verified facts this module encodes
-----------------------------------
* ONE process holds MANY turns on a STABLE ``session_id``: writing a second
  ``{"type":"user",...}`` line after the first turn's ``result`` reuses the
  same session. The process stays alive until stdin is closed.
* ``--include-partial-messages`` is requested UNCONDITIONALLY (not only for
  delta text). It is also the ONLY reliable signal this connector has that a
  turn has begun generating content (``stream_event`` with
  ``event.type in {"message_start","content_block_start"}``), which matters
  for the interrupt safety window below.
* ``{"type":"control_request","request":{"subtype":"interrupt"}}`` on stdin
  IS a real, working mid-session control message (distinct from - and not
  affected by - the MCP ``notifications/claude/*`` path eliminated in
  EV-CC-002). It is answered synchronously with a ``control_response`` and
  this is what makes ``steer_timing=IMMEDIATE`` achievable: ``steer`` is
  implemented as interrupt-then-resend, not as a bare queued user line (a
  bare second ``user`` line while a turn is in flight does NOT interleave -
  it is strictly queued and only runs after the current turn's ``result``,
  i.e. it is NEXT_TURN_BOUNDARY behaviour, not IMMEDIATE. Declaring
  IMMEDIATE while only ever writing a bare queued line would be exactly the
  "capability lie" EV-INF-002 fixed for D7b's ``steer_timing`` - see the
  module docstring note under "Known, deliberate degradation" below).
* **A genuine race window makes ``interrupt`` fatal to the whole process if
  fired too early.** Interrupting a turn that has been submitted but has not
  yet produced its first ``stream_event`` (still in the CLI's internal
  "requesting" phase) crashes the process: it answers the
  ``control_response`` normally, then emits
  ``{"type":"result","subtype":"error_during_execution"}`` and EXITS(1) -
  the session does not survive. Interrupting an IDLE connector (no turn
  submitted at all) is safe. Interrupting AFTER the first
  ``message_start``/``content_block_start`` stream event is also safe: the
  turn ends with the same ``error_during_execution`` result but the process
  and session survive for further turns, and a reprompt sent immediately
  (no artificial delay) is honoured correctly - i.e.
  ``interrupt_requires_settle_wait=False`` holds. This connector therefore
  gates every interrupt it issues on having observed generation start for
  the CURRENT turn (see ``_turn_generating``), which is the only way to
  earn ``steer_timing=IMMEDIATE`` without periodically crashing the peer.
* Malformed input is fatal in a way genuinely unlike a normal harness error:
  a syntactically invalid JSON line, OR valid JSON missing the expected
  ``message`` shape, makes the CLI print to stderr and exit(1) IMMEDIATELY -
  any further already-queued valid lines are never processed. An unknown
  *top-level* ``"type"`` value, by contrast, is silently ignored (exit 0,
  no stderr). This connector never emits the former (it fully controls
  outbound serialisation and validates ``payload["content"]`` before
  writing), and treats the latter as a documented version-drift hazard on
  the SEND side.
* ``system``/``init`` re-fires before EVERY turn (not once at session
  start) and is this connector's ``turn_started`` signal.
* Closing stdin drains any in-flight turn and then the process exits(0)
  cleanly - the natural producer of ``observes_session_end=True``: this
  connector never synthesises an "ended" ``HarnessEvent``; the
  :meth:`events` iterator simply terminating (after any final diagnostic
  ``error`` event on an unexpected/non-zero exit) IS the end signal, exactly
  as D1/EV-INF-002 frame it for a connector that can observe an end at all.

``steer`` verified IMMEDIATE against the real binary (not just inferred)
--------------------------------------------------------------------------
Empirically confirmed against ``claude`` 2.1.278 (manual probe and
``test_real_claude_steer_interrupts_in_flight_turn_and_runs_new_one_
immediately``, both 2026-09-20): sending ``steer`` once a turn is observed
generating lands a real ``control_request``/``interrupt`` in well under
20ms (``control_response:success`` immediately followed by that turn's
``result:error_during_execution``), and the steered content then runs as
the next turn on the SAME process/session with no settle delay. This is
genuine IMMEDIATE redirection (interrupt-then-resend), not a bare queued
line that would only land at the next turn boundary - so
``steer_timing=IMMEDIATE`` is an honest declaration for this (safe-window)
path, not a capability lie. Earlier revisions of this module declared
IMMEDIATE on the strength of the separately-verified ``interrupt`` path
alone; no test ever drove ``send(verb='steer')`` itself against the real
binary until the above.

Known, deliberate degradation
------------------------------
``steer``/``interrupt`` issued while a turn is in the fatal "requesting"
race window (submitted, not yet generating) are NOT forwarded as a real
interrupt - that would risk killing the whole session on a coin flip of
timing. Instead: ``interrupt`` becomes a documented no-op (surfaced as a
``tool_activity`` diagnostic event, never silently dropped) and ``steer``
degrades to a bare queued line (i.e. NEXT_TURN_BOUNDARY-like, only in this
narrow, typically sub-second window) rather than true IMMEDIATE redirection.
This is the single place this connector does not fully honour its declared
``steer_timing=IMMEDIATE`` capability, and it is a deliberate, reported
trade-off (crash avoidance over strict immediacy), not an oversight.

Event-vocabulary port gap (reported, not fixed - the port is FROZEN)
----------------------------------------------------------------------
:data:`~okto_nexus.domain.harness.EVENT_KINDS` has no "informational/system
notice" kind. Real, frequent native events - ``system``/``hook_started``,
``hook_response``, ``informational``, ``status``; ``rate_limit_event``;
``control_response``; the synthetic post-interrupt ``user`` echo; and the
structural (non-text-delta) ``stream_event`` sub-events - have no honest
closed-vocabulary home. Per D2/INT-03 ("unmapped native events are
surfaced, never silently dropped") this connector maps ALL of them to
``tool_activity`` as the least-wrong available bucket, carrying the real
native name in ``native_event`` and the full native envelope in ``payload``
so nothing is lost - but this is a mapping of convenience, not a claim that
these are tool calls. See the accompanying report for detail.

Threading model
----------------
:meth:`start` and :meth:`send` are SYNCHRONOUS per the frozen port (they run
on whatever thread the in-process supervisor calls them from - D1 puts that
supervisor in the same process as ``serve``'s event loop, and this module
must never block it). All child-process I/O therefore happens on two daemon
reader threads (stdout, stderr) started by :meth:`start`, exactly the shape
the port's own docstring calls out ("a thread-fed queue for child-process
stdio"). :meth:`events` hands back a generator that blocks on
``queue.Queue.get()`` - a blocking wait, never a sleep-poll loop - so no
``SleepPollWaiter`` appears anywhere in this path (D1) and the caller is
woken the instant an event is published, not on some fixed interval.
"""

from __future__ import annotations

from .environment import child_environment

import json
import queue
import subprocess
import threading
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from ....domain.base import utc_now_iso
from ....domain.harness import (
    COMMAND_VERBS,
    STEER_TIMING_IMMEDIATE,
    STEER_TIMING_NEXT_TURN_BOUNDARY,
    HarnessCapabilities,
    HarnessCommand,
    HarnessEvent,
    HarnessSession,
    new_harness_session_id,
)
from ....errors import ErrorCode, OktoNexusError

__all__ = ["ClaudeCodeStreamConnector"]

#: Flags proven live against claude 2.1.278 (module docstring). Order
#: matches how the CLI's own ``--help`` groups them; ``--include-partial-
#: messages`` is requested unconditionally - see the module docstring for
#: why it is load-bearing for interrupt safety, not merely for deltas.
_DEFAULT_ARGV: tuple[str, ...] = (
    "-p",
    "--output-format",
    "stream-json",
    "--input-format",
    "stream-json",
    "--verbose",
    "--include-partial-messages",
)

#: Bound on how many trailing stderr lines are retained for a diagnostic
#: payload on abnormal exit. Stderr is always fully drained regardless (the
#: quality bar: a full pipe buffer must never deadlock the child); this only
#: bounds how much of it this connector chooses to remember.
_STDERR_TAIL_MAX_LINES = 50

#: How long :meth:`_finish` waits for the child's exit code once its stdout
#: has already hit EOF (which, empirically, coincides with process exit).
#: A backstop against a pathological hang, not a value expected to matter in
#: practice.
_EXIT_WAIT_TIMEOUT_S = 10.0

#: Bounded wake-up period for the shutdown liveness check in :meth:`events`
#: (mirrors ``harness/pi.py``'s ``_EVENTS_POLL_S`` - the house pattern for
#: this exact defect class, see that module's "Known protocol-to-port
#: mismatches" note 9). This is NOT event polling: a real event still wakes
#: ``Queue.get(timeout=...)`` the instant it is pushed, exactly like an
#: unbounded ``get()`` would. The timeout only bounds how long an IDLE wait
#: blocks before re-checking :attr:`ClaudeCodeStreamConnector._closed_event`,
#: so :meth:`events` - called any number of times, from any thread, even
#: after having already returned once - always terminates within one poll
#: period of the child exiting, never later. Fixes the single-consumption
#: ``None`` sentinel this module used to push exactly once: only ONE
#: `events()` caller could ever observe it, and every other live caller
#: (a second call, or the same caller invoking it twice) blocked forever on
#: an unbounded ``get()`` with nothing left to receive.
_EVENTS_POLL_S = 1.0

#: How long a write-path caller (``_write_json``/``_end``) waits to acquire
#: :attr:`ClaudeCodeStreamConnector._write_lock` before giving up loudly.
#: The lock itself is only ever held for the duration of a `stdin.write`` +
#: ``flush`` (a single JSON line, always far under the OS pipe buffer's
#: atomic-write threshold - see :meth:`_write_json`'s docstring for why the
#: write syscall itself is not, in turn, bounded), so contention this long
#: means another caller's write is itself stuck on a full pipe because the
#: child stopped reading - a real hang, not a transient race - and this
#: connector must say so rather than silently join the wait.
_WRITE_LOCK_TIMEOUT_S = 10.0


class ClaudeCodeStreamConnector:
    """:class:`~okto_nexus.application.ports.HarnessConnector` for D7a.

    One instance owns exactly one ``claude -p`` child process for its whole
    lifetime (``multiplexes_sessions=False``) - construct a new instance per
    session. Capabilities are fixed at construction (ADR 0004 D7a mapping):

    * ``send_only=False`` - turns are answered, via the normal event stream.
    * ``steer_timing=IMMEDIATE`` - earned via interrupt-then-resend; see the
      module docstring's "Known, deliberate degradation" for the one
      documented exception.
    * ``interrupt_requires_settle_wait=False`` - verified empirically: a
      reprompt sent immediately after a (safe) interrupt is honoured with no
      race, unlike Pi's abort/settle ordering.
    * ``multiplexes_sessions=False`` - one child, one session, one connector
      instance.
    * ``observes_session_end=True`` - the child's own exit (stdin closed by
      :meth:`send`'s ``end`` verb, or the child dying) is directly
      observable and terminates :meth:`events`.
    """

    def __init__(
        self,
        *,
        binary: str = "claude",
        argv: Sequence[str] | None = None,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        """Construct an unstarted connector.

        Parameters
        ----------
        binary:
            Executable to spawn. Overridable so tests point this at a fake
            script (e.g. ``sys.executable``) instead of requiring the real
            ``claude`` CLI to be installed.
        argv:
            Full argument list passed after ``binary`` (default
            :data:`_DEFAULT_ARGV`). Overridable for the same reason.
        cwd, env:
            Passed straight through to :class:`subprocess.Popen`. ``env``
            entries are MERGED over a copy of the current process
            environment (never replace it outright - the child needs the
            inherited ``PATH``/auth state to run at all).
        """
        self._binary = binary
        self._argv: tuple[str, ...] = tuple(argv) if argv is not None else _DEFAULT_ARGV
        self._cwd = cwd
        self._env = dict(env) if env is not None else None

        self.capabilities = HarnessCapabilities(
            send_only=False,
            steer_timing=STEER_TIMING_IMMEDIATE,
            interrupt_requires_settle_wait=False,
            multiplexes_sessions=False,
            observes_session_end=True,
        )

        self._proc: subprocess.Popen[str] | None = None
        self._session: HarnessSession | None = None
        # RES-A2 fix (mirrors harness/pi.py's C2 fix): the pre-fix design
        # shared exactly ONE queue.Queue across every events() call, so two
        # concurrent consumers (or two calls from different threads) raced
        # for each item and SPLIT the stream between them rather than each
        # independently seeing the whole thing - see EV-CC-004-res-a2-probe.py
        # for the reproduction. Fan-out instead: _event_history is the
        # append-only record of every event ever emitted (never trimmed - a
        # session's event count is bounded by its own lifetime), and each
        # events() call gets its OWN subscriber queue, seeded with a
        # snapshot of the history taken under _history_lock at subscribe
        # time (so a LATE subscriber still gets everything from the start)
        # and then fed live by _emit(). _history_lock also serialises
        # history-append against backlog-snapshot so an emit can never land
        # in the gap between a new subscriber's snapshot and its
        # registration - see _emit()/events().
        self._event_history: list[HarnessEvent] = []
        self._history_lock = threading.Lock()
        self._subscribers: list[queue.Queue[HarnessEvent]] = []
        # Set once by _finish() (the stdout reader thread, on child exit) or
        # by a failed start() (RES-A4 fix, see that method). events()
        # rechecks this on every queue.Empty from a BOUNDED
        # get(timeout=_EVENTS_POLL_S) rather than relying on a single
        # push-once sentinel value travelling through the queue - a
        # sentinel can only ever be consumed by ONE caller, so any second
        # events() call (or the same caller invoking it twice) would
        # otherwise block forever on an unbounded get() with nothing left
        # to receive. threading.Event is safe to read from any thread.
        self._closed_event = threading.Event()
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None

        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        # Guarded by _state_lock. ``_pending_turns`` is a FIFO of one entry
        # per queued-but-not-yet-resulted turn (each entry: was THIS turn
        # interrupted by us). A plain "the current turn" boolean is not
        # enough here: ``steer`` can interrupt an in-flight turn and queue
        # its replacement in the SAME call, before the interrupted turn's
        # own belated ``result`` has been read off stdout by the reader
        # thread - two turns are simultaneously unresolved from this
        # connector's point of view. The child processes queued turns
        # strictly in the order they were written (verified: it is a
        # single-threaded reader loop), so incoming ``result`` events are
        # guaranteed to resolve ``_pending_turns`` in the same FIFO order
        # they were appended, with no id correlation needed. An interrupt
        # therefore always marks index 0 (the HEAD - the turn currently
        # generating), never index -1 (the TAIL - a not-yet-started turn
        # queued behind it): ``_handle_result`` always pops the head, so
        # the two ends must agree on which end "the turn being
        # interrupted" lives at.
        self._turn_in_flight = False
        self._pending_turns: deque[bool] = deque()
        self._interrupt_request_counter = 0
        # Set by the stdout reader thread the moment the HEAD turn's
        # (`_pending_turns[0]`) generation is observed to have started;
        # cleared by `_send_turn`/`_steer` ONLY when the turn being queued
        # becomes the new head (i.e. `_pending_turns` was empty just
        # before), and by the reader on that head turn's result. This flag
        # represents "is the HEAD turn generating", not "is ANY turn
        # generating" - a single boolean is sufficient because only the
        # head is ever actually running at once (the child processes
        # queued turns strictly FIFO, single-threaded), so nothing else
        # needs its own generating state. Clearing it unconditionally on
        # every ordinary send_turn used to be a real bug: an ordinary
        # SECOND send_turn issued while the head turn was still generating
        # would desync this flag from reality (a TAIL turn joining the
        # queue has nothing to do with whether the HEAD is generating),
        # silently defeating a subsequent interrupt - see
        # test_ordinary_send_turn_while_generating_does_not_desync_the_generating_flag.
        # threading.Event is the cross-thread-safe primitive for this
        # single boolean flag (no separate lock needed for it).
        self._turn_generating = threading.Event()

        self._stderr_tail: list[str] = []

    # ------------------------------------------------------------------ #
    # HarnessConnector port
    # ------------------------------------------------------------------ #
    def start(self, *, owning_agent_id: str) -> HarnessSession:
        if self._proc is not None:
            raise OktoNexusError(
                ErrorCode.CONFLICT,
                "connector already started; one HarnessSession per connector "
                "instance (multiplexes_sessions=False) - construct a new "
                "ClaudeCodeStreamConnector for another session.",
                {},
            )

        # RES-A4 fix: clear any shutdown signal left by a PREVIOUS failed
        # start() attempt on this same instance (see the except clauses
        # below) - the CONFLICT guard above only blocks a retry after a
        # SUCCESSFUL start (self._proc stays None on every failure path),
        # so without this a successful retry's events() would see
        # _closed_event already set and return prematurely the next time
        # its queue happens to run momentarily dry, even though this
        # session is healthy and still has real events coming.
        self._closed_event.clear()

        argv = [self._binary, *self._argv]
        spawn_env = child_environment(self._env)
        try:
            proc = subprocess.Popen(  # noqa: S603 - argv is fixed/injected by the caller, not user input
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self._cwd,
                env=spawn_env,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
            )
            self._proc = proc
            session = HarnessSession(
                session_id=new_harness_session_id(),
                harness_kind="claude_code",
                owning_agent_id=owning_agent_id,
                status="STARTING",
                capabilities=self.capabilities,
                started_at=utc_now_iso(),
            )
            self._session = session

            self._stdout_thread = threading.Thread(
                target=self._pump_stdout, name="cc-connector-stdout", daemon=True
            )
            self._stderr_thread = threading.Thread(
                target=self._pump_stderr, name="cc-connector-stderr", daemon=True
            )
            self._stdout_thread.start()
            self._stderr_thread.start()
        except OSError as exc:
            # RES-A4 fix: this path never used to set _closed_event, so a
            # subsequent events() call looped forever (get(timeout=...) ->
            # queue.Empty -> _closed_event.is_set() False -> continue,
            # indefinitely) - see EV-CC-004-res-a4-probe.py. Mirrors
            # harness/pi.py's C3 fix.
            self._closed_event.set()
            raise OktoNexusError(
                ErrorCode.CONFIG_ERROR,
                f"failed to spawn Claude Code binary {self._binary!r}: {exc}",
                {"binary": self._binary, "argv": list(self._argv)},
            ) from exc
        except BaseException:
            # Backstop for any OTHER way this block can fail (e.g. a
            # thread-start RuntimeError) - not just the one OSError path
            # this connector itself anticipates. Caught broadly, same as
            # harness/pi.py's C3 fix, so every way start() can fail still
            # leaves events() terminable.
            self._closed_event.set()
            raise
        return session

    def send(self, session: HarnessSession, command: HarnessCommand) -> None:
        if self._proc is None or self._session is None:
            raise OktoNexusError(
                ErrorCode.CONFLICT, "connector has not been started; call start() first.", {}
            )
        if session.session_id != self._session.session_id:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "command targets a session this connector instance did not start.",
                {"session_id": session.session_id, "connector_session_id": self._session.session_id},
            )
        if command.verb not in COMMAND_VERBS:  # backstop; HarnessCommand already validates this
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"unsupported harness command verb {command.verb!r}.",
                {"verb": command.verb},
            )

        if command.verb == "send_turn":
            self._send_turn(command)
        elif command.verb == "steer":
            self._steer(command)
        elif command.verb == "interrupt":
            self._interrupt()
        elif command.verb == "end":
            self._end()

    def events(self) -> Iterator[HarnessEvent]:
        """Blocking generator over inbound events; ends when the child exits.

        RES-A2 fix (mirrors ``harness/pi.py``'s C2 fix): this call has its
        OWN independent fan-out subscription - calling this a second time,
        or from a second thread, no longer SPLITS the stream with the first
        caller (the pre-fix defect: one shared ``queue.Queue`` meant two
        concurrent consumers each got roughly half the events,
        unpredictably, with no way to tell which half - see
        ``EV-CC-004-res-a2-probe.py``). Each call registers a fresh
        per-consumer queue, seeded with every event emitted since the
        connector started (:attr:`_event_history`) so a LATE subscriber - a
        supervisor that reconnects, or simply calls this after the turn
        already started - still gets the full stream from the beginning,
        not just what happens to be emitted after it subscribes.

        Real events are still delivered the instant they are emitted - a
        ``Queue.get(timeout=_EVENTS_POLL_S)`` returns immediately once an
        item exists, exactly like an unbounded ``get()`` would (no sleep, no
        poll interval for events themselves - D1 is not violated). The
        timeout only bounds how long an IDLE wait can run before
        re-checking :attr:`_closed_event`, so this call - EVEN A SECOND OR
        LATER CALL, EVEN FROM ANOTHER THREAD - always terminates within one
        poll period of the child exiting, never later, and never returns
        while events remain queued (the ``queue.Empty`` branch only fires
        once the queue is genuinely drained). Per the module docstring, that
        termination IS this connector's ``observes_session_end=True``
        signal - no separate "ended" ``HarnessEvent`` kind exists in the
        port to synthesise.

        This also still carries the earlier single-consumption ``None``
        sentinel fix: shutdown is a ``threading.Event`` (:attr:`_closed_event`)
        checked on every ``queue.Empty``, not a value travelling through the
        queue that only one generator could ever consume.
        """
        my_queue: queue.Queue[HarnessEvent] = queue.Queue()
        with self._history_lock:
            backlog = list(self._event_history)
            self._subscribers.append(my_queue)
        try:
            for item in backlog:
                yield item
            while True:
                try:
                    item = my_queue.get(timeout=_EVENTS_POLL_S)
                except queue.Empty:
                    if self._closed_event.is_set():
                        return
                    continue
                yield item
        finally:
            with self._history_lock:
                try:
                    self._subscribers.remove(my_queue)
                except ValueError:
                    pass

    # ------------------------------------------------------------------ #
    # Outbound command handling
    # ------------------------------------------------------------------ #
    def _send_turn(self, command: HarnessCommand) -> None:
        content = self._require_content(command)
        with self._state_lock:
            becomes_head = not self._pending_turns
            self._turn_in_flight = True
            self._pending_turns.append(False)
        # `_turn_generating` tracks whether the HEAD turn (the one actually
        # running right now, `_pending_turns[0]`) has started producing
        # output - it is what `_interrupt()`/`_steer()` read to decide
        # whether a real `control_request` is safe to forward. Only clear
        # it when THIS turn becomes the new head (the queue was empty, so
        # nothing was generating before it): an ORDINARY second `send_turn`
        # issued while turn 1 is still generating merely appends a TAIL
        # entry behind it and must never touch the head's own generating
        # signal - doing so unconditionally used to silently desync it and
        # defeat a subsequent interrupt (see
        # test_ordinary_send_turn_while_generating_does_not_desync_the_generating_flag).
        if becomes_head:
            self._turn_generating.clear()
        self._write_json({"type": "user", "message": {"role": "user", "content": content}})

    def _steer(self, command: HarnessCommand) -> None:
        """Redirect the session, earning ``steer_timing=IMMEDIATE``.

        Interrupts the in-flight turn (if any and if it is SAFE to - see the
        module docstring) and immediately queues the new content as the next
        turn. On a connector with no turn in flight this is identical to
        :meth:`_send_turn`.
        """
        content = self._require_content(command)
        with self._state_lock:
            in_flight = self._turn_in_flight
        if in_flight:
            if self._turn_generating.is_set():
                self._request_interrupt()
            else:
                # Known, deliberate degradation - see module docstring.
                # EVENT_KINDS has no dedicated closed-vocabulary kind for
                # "declared capability degraded" and the port is FROZEN
                # (cannot add one - reported, not fixed, per the module
                # docstring's "Event-vocabulary port gap" note). What IS
                # port-legal is a stable, always-present PAYLOAD flag a
                # supervisor can branch on directly, instead of having to
                # string-match native_event - this is that flag.
                self._emit(
                    "tool_activity",
                    "steer_interrupt_deferred_unsafe_window",
                    {
                        "reason": (
                            "turn submitted but generation not yet observed; "
                            "interrupting now is empirically fatal to the "
                            "process, so this steer degrades to a queued "
                            "next turn instead of an immediate redirect."
                        ),
                        "steer_timing_degraded": True,
                        "declared_steer_timing": STEER_TIMING_IMMEDIATE,
                        "effective_steer_timing": STEER_TIMING_NEXT_TURN_BOUNDARY,
                    },
                )
        with self._state_lock:
            # `in_flight` (captured above, BEFORE this append) tells us
            # whether a head entry already existed: if it did, this new
            # entry becomes a TAIL entry and must never touch
            # `_turn_generating` (which tracks the HEAD's own generating
            # state - see `_send_turn`'s docstring for the desync this
            # unconditional-clear bug used to cause). If nothing was in
            # flight, this new entry becomes the head itself, so clearing
            # is correct.
            becomes_head = not in_flight
            self._turn_in_flight = True
            # A fresh, un-interrupted entry for the NEW turn being queued
            # here, appended at the TAIL - never touch the interrupted
            # turn's own entry (at the HEAD, index 0) the `_request_
            # interrupt()` call above may have just marked; that entry is
            # still waiting for its own belated `result` and must keep its
            # `True` flag until `_handle_result` pops it from the front (see
            # `_pending_turns`'s docstring in `__init__`).
            self._pending_turns.append(False)
        if becomes_head:
            self._turn_generating.clear()
        self._write_json({"type": "user", "message": {"role": "user", "content": content}})

    def _interrupt(self) -> None:
        with self._state_lock:
            in_flight = self._turn_in_flight
        if not in_flight:
            return  # nothing to interrupt; verified safe as a no-op empirically.
        if not self._turn_generating.is_set():
            # Known, deliberate degradation - see module docstring, and the
            # steer-path sibling emit above for why this payload flag
            # exists (port-legal substitute for a closed-vocabulary kind).
            self._emit(
                "tool_activity",
                "interrupt_deferred_unsafe_window",
                {
                    "reason": (
                        "turn submitted but generation not yet observed; "
                        "interrupting now is empirically fatal to the "
                        "process, so this interrupt is dropped as a no-op "
                        "rather than risking the whole session."
                    ),
                    "interrupt_degraded": True,
                },
            )
            return
        self._request_interrupt()

    def _request_interrupt(self) -> None:
        with self._state_lock:
            self._interrupt_request_counter += 1
            request_id = f"nexus-interrupt-{self._interrupt_request_counter}"
            # Mark the turn CURRENTLY in flight - the HEAD of the FIFO, i.e.
            # `_pending_turns[0]` - as interrupted-by-us, so the belated
            # `result` it produces is classified `turn_completed`, not
            # `error`, by `_handle_result`. This must be the head, not the
            # tail: `_handle_result` always resolves oldest-first via
            # `popleft()` (the child processes queued turns strictly FIFO),
            # and the entry actually being interrupted right now is
            # whichever one is currently generating - always the oldest
            # still-unresolved entry, never a not-yet-started one queued
            # behind it. `steer()` calls this BEFORE appending its own new
            # turn's entry, so index 0 here is always the in-flight turn,
            # never the steer's own not-yet-submitted replacement (fixed
            # 2026-09-20: previously marked `[-1]`, which silently swapped
            # this classification with an unrelated queued turn whenever
            # more than one turn was outstanding - see
            # test_request_interrupt_marks_the_head_pending_turn_not_the_tail).
            if self._pending_turns:
                self._pending_turns[0] = True
        self._write_json(
            {"type": "control_request", "request_id": request_id, "request": {"subtype": "interrupt"}}
        )

    def _end(self) -> None:
        """Close stdin. Verified empirically: this drains any in-flight turn
        and the process then exits(0) cleanly; no SIGTERM/SIGKILL needed for
        the graceful path. :meth:`_finish` (run by the stdout reader thread
        once it observes EOF) does the actual teardown bookkeeping.
        """
        self._acquire_write_lock()
        try:
            proc = self._proc
            if proc is not None and proc.stdin is not None:
                try:
                    proc.stdin.close()
                except OSError:
                    pass  # already closed / child gone - nothing left to do.
        finally:
            self._write_lock.release()

    def _require_content(self, command: HarnessCommand) -> str:
        content = command.payload.get("content")
        if not isinstance(content, str) or not content:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"{command.verb} requires a non-empty string payload['content'].",
                {"verb": command.verb, "payload": command.payload},
            )
        return content

    def _write_json(self, obj: dict[str, Any]) -> None:
        """Serialise and write one line to the child's stdin.

        The write syscall itself (``proc.stdin.write`` + ``flush``) is NOT,
        in turn, individually timeout-bounded: it writes a single JSON line
        that this connector controls end-to-end, always far under the OS
        pipe buffer's atomic-write threshold (``PIPE_BUF``, typically 4-64
        KiB), so in practice it either completes immediately or the pipe is
        already broken (``BrokenPipeError``/``OSError``, handled below) -
        documented residual, not an oversight. What IS bounded is the LOCK
        ACQUIRE: see :attr:`_acquire_write_lock` / ``_WRITE_LOCK_TIMEOUT_S``
        for why unbounded contention on this lock is its own hazard,
        independent of the write itself.
        """
        line = json.dumps(obj, ensure_ascii=False)
        self._acquire_write_lock()
        try:
            proc = self._proc
            if proc is None or proc.stdin is None:
                raise OktoNexusError(
                    ErrorCode.CONFLICT,
                    "connector has no active stdin (not started, or already ended).",
                    {},
                )
            try:
                proc.stdin.write(line + "\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise OktoNexusError(
                    ErrorCode.CONFLICT,
                    f"failed to write to Claude Code stdin (child likely exited): {exc}",
                    {},
                ) from exc
        finally:
            self._write_lock.release()

    def _acquire_write_lock(self) -> None:
        """Bounded acquire of :attr:`_write_lock` (audit finding: every
        blocking wait must have a timeout and raise a clear error on
        expiry). Contention this long past ``_WRITE_LOCK_TIMEOUT_S`` means
        ANOTHER caller's write/close is itself stuck - a real hang, not a
        transient race - so this connector says so loudly rather than
        silently joining an unbounded wait.
        """
        acquired = self._write_lock.acquire(timeout=_WRITE_LOCK_TIMEOUT_S)
        if not acquired:
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                f"could not acquire Claude Code stdin write lock within "
                f"{_WRITE_LOCK_TIMEOUT_S}s; another write is likely stuck.",
                {},
            )

    # ------------------------------------------------------------------ #
    # Inbound reader threads
    # ------------------------------------------------------------------ #
    def _pump_stdout(self) -> None:
        """Read and dispatch every stdout line; NEVER let dispatch kill this
        thread.

        ``_handle_stdout_line`` and everything it calls assume the shape the
        module docstring documents as verified against real ``claude``
        2.1.278 output - but a shape-drifted line that is still
        syntactically valid JSON and still has a recognised top-level
        ``"type"`` (e.g. ``{"type":"stream_event","event":"oops"}`` - a
        string where a dict is expected) is not caught by
        :meth:`_handle_stdout_line`'s own JSON/dict guard and can raise
        deep inside a handler (``AttributeError`` on the string's missing
        ``.get``). Found in review: with no guard here, that exception
        silently killed this thread (a bare thread target swallows it), so
        :meth:`_finish` then ran with the child STILL GENUINELY ALIVE -
        fabricating a session-end signal this connector never actually
        observed and losing every further event including the turn's real
        result. A per-line guard is the fix: one malformed/unexpected line
        is surfaced as a diagnostic ``error`` event (per D2/INT-03 - never
        silently dropped) and dispatch simply continues with the next line,
        so this reader keeps running for as long as the child's stdout
        does - exactly what ``observes_session_end=True`` requires it to.
        """
        assert self._proc is not None and self._proc.stdout is not None
        try:
            for raw_line in self._proc.stdout:
                line = raw_line.rstrip("\n")
                if not line:
                    continue
                try:
                    self._handle_stdout_line(line)
                except Exception as exc:  # noqa: BLE001 - must never abort this loop; see docstring above
                    self._emit(
                        "error",
                        "stdout_dispatch_error",
                        {"raw": line[:2000], "error": repr(exc)},
                    )
        finally:
            self._finish()

    def _pump_stderr(self) -> None:
        """Fully drain stderr on a dedicated thread.

        This is NOT best-effort: an undrained stderr pipe filling up is a
        real deadlock hazard for the child (quality bar) even though this
        connector has no JSON to parse from it in the happy path - stderr is
        prose, not the protocol.
        """
        assert self._proc is not None and self._proc.stderr is not None
        for raw_line in self._proc.stderr:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            self._stderr_tail.append(line)
            if len(self._stderr_tail) > _STDERR_TAIL_MAX_LINES:
                del self._stderr_tail[: len(self._stderr_tail) - _STDERR_TAIL_MAX_LINES]

    def _finish(self) -> None:
        """Reap the child and signal shutdown to every :meth:`events` caller.

        Runs on the stdout reader thread once its ``for line in stdout``
        loop hits EOF (the child closed stdout - empirically this coincides
        with process exit; per-line dispatch errors are caught in
        :meth:`_pump_stdout` and never abort this loop early - see that
        method's docstring). Joins the stderr thread first so a diagnostic
        payload on abnormal exit has the FULL captured tail, not a partial
        one racing the pipe's own EOF.
        """
        proc = self._proc
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=_EXIT_WAIT_TIMEOUT_S)

        exit_code: int | None = None
        wait_timed_out = False
        if proc is not None:
            try:
                exit_code = proc.wait(timeout=_EXIT_WAIT_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                wait_timed_out = True

        if wait_timed_out:
            # stdout hit EOF but the child never confirmed its own exit
            # within the backstop window - verify with proc.poll() rather
            # than assume. Claiming `process_exit` (this connector's only
            # session-end signal, per observes_session_end=True) here would
            # be FABRICATING an end-of-session the connector never actually
            # observed, exactly the dishonesty this module exists to avoid
            # (module docstring: robustness is the whole point). Kill the
            # still-alive child rather than silently leaking it, and say
            # plainly that this happened.
            still_running = proc is not None and proc.poll() is None
            if proc is not None and still_running:
                try:
                    proc.kill()
                    proc.wait(timeout=_EXIT_WAIT_TIMEOUT_S)
                except (OSError, subprocess.TimeoutExpired):
                    pass  # best-effort reap; the sentinel below still fires.
            self._emit(
                "error",
                "reader_eof_without_confirmed_exit",
                {
                    "was_still_running_before_kill": still_running,
                    "stderr_tail": list(self._stderr_tail),
                },
            )
        elif exit_code != 0:
            self._emit(
                "error",
                "process_exit",
                {
                    "exit_code": exit_code,
                    "stderr_tail": list(self._stderr_tail),
                },
            )
        # Signal shutdown to every current AND future events() caller - see
        # that method's docstring for why this is a threading.Event checked
        # on a bounded get(), not a single push-once queue sentinel.
        self._closed_event.set()

    def _handle_stdout_line(self, line: str) -> None:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            self._emit("error", "unparseable_stdout_line", {"raw": line[:2000]})
            return
        if not isinstance(obj, dict):
            self._emit("error", "unparseable_stdout_line", {"raw": line[:2000]})
            return

        native_type = obj.get("type")
        if native_type == "system":
            self._handle_system(obj)
        elif native_type == "stream_event":
            self._handle_stream_event(obj)
        elif native_type == "assistant":
            self._handle_assistant(obj)
        elif native_type == "result":
            self._handle_result(obj)
        elif native_type == "control_response":
            subtype = (obj.get("response") or {}).get("subtype")
            self._emit("tool_activity", f"control_response:{subtype}", obj)
        elif native_type == "rate_limit_event":
            self._emit("tool_activity", "rate_limit_event", obj)
        elif native_type == "user":
            # Observed only as the CLI's own synthetic echo after an
            # interrupt cuts a turn; not a peer message.
            self._emit("tool_activity", "user_echo", obj)
        else:
            # Unmapped native event: surfaced, never silently dropped (D2 /
            # the port's INT-03 requirement) - see the module docstring's
            # event-vocabulary port-gap note for why this is tool_activity.
            self._emit("tool_activity", f"unknown:{native_type}", obj)

    def _handle_system(self, obj: dict[str, Any]) -> None:
        subtype = obj.get("subtype")
        if subtype == "init":
            # Re-fires before EVERY turn (verified), not just once at
            # session start - this connector's turn_started signal.
            self._emit("turn_started", "system:init", obj)
        else:
            self._emit("tool_activity", f"system:{subtype}", obj)

    def _handle_stream_event(self, obj: dict[str, Any]) -> None:
        event = obj.get("event") or {}
        etype = event.get("type")
        if etype in ("message_start", "content_block_start"):
            self._turn_generating.set()
            self._emit("tool_activity", f"stream_event:{etype}", obj)
        elif etype == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta":
                self._emit(
                    "output_delta",
                    "stream_event:content_block_delta",
                    {"text": delta.get("text", ""), "index": event.get("index")},
                )
            else:
                self._emit("tool_activity", "stream_event:content_block_delta", obj)
        else:
            self._emit("tool_activity", f"stream_event:{etype}", obj)

    def _handle_assistant(self, obj: dict[str, Any]) -> None:
        # Defensive: proves generation happened even if a stream_event was
        # somehow missed, so a later interrupt is never gated open forever.
        self._turn_generating.set()
        message = obj.get("message") or {}
        text = "".join(
            block.get("text", "")
            for block in message.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        self._emit("output_delta", "assistant", {"final": True, "text": text, "raw": obj})

    def _handle_result(self, obj: dict[str, Any]) -> None:
        subtype = obj.get("subtype")
        is_success = subtype == "success"
        with self._state_lock:
            # Pop the OLDEST unresolved turn - the child processes queued
            # turns strictly FIFO (single-threaded reader loop), so this
            # `result` always resolves whichever turn was queued first,
            # even when `steer()` has since queued a second, still-pending
            # one behind it (see `_pending_turns`'s docstring in `__init__`).
            interrupted = self._pending_turns.popleft() if self._pending_turns else False
            self._turn_in_flight = bool(self._pending_turns)
        self._turn_generating.clear()
        payload = {**obj, "interrupted_by_connector": interrupted}
        if is_success or interrupted:
            # A result caused by THIS connector's own interrupt is a
            # successful steer/interrupt outcome, not a harness failure -
            # see the module docstring.
            self._emit("turn_completed", f"result:{subtype}", payload)
        else:
            # Unprompted, non-success completion: a genuine turn error.
            self._emit("error", f"result:{subtype}", payload)

    def _emit(self, kind: str, native_event: str, payload: dict[str, Any]) -> None:
        assert self._session is not None
        event = HarnessEvent(
            session_id=self._session.session_id,
            harness_kind="claude_code",
            kind=kind,
            native_event=native_event,
            occurred_at=utc_now_iso(),
            payload=payload,
        )
        # RES-A2 fix (mirrors harness/pi.py's C2 fix): append to the
        # durable history and snapshot the subscriber list under the SAME
        # lock a new events() call uses to take its own backlog snapshot -
        # this is what makes the snapshot-then-subscribe in events()
        # race-free: whichever of {this emit, a concurrent subscribe} takes
        # the lock first fully happens before the other, so a new
        # subscriber can never miss an event that raced its own
        # registration, and never sees it twice. The actual queue.put()
        # calls happen OUTSIDE the lock (subscribers is only read here, not
        # mutated) so a slow/blocked consumer can never hold up _emit().
        with self._history_lock:
            self._event_history.append(event)
            subscribers = list(self._subscribers)
        for subscriber_queue in subscribers:
            subscriber_queue.put(event)
