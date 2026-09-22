"""Pi ``--mode rpc`` connector - the D4 leg of the harness transport port.

Implements :class:`okto_nexus.application.ports.HarnessConnector` against
``pi --mode rpc`` (pi 0.85.1, strict LF-framed JSON lines over child stdio;
see ``docs/design/0004-harness-integrations.md`` D4 and
``docs/harness-integrations/research/pi-rpc-protocol-reference.md`` /
``docs/harness-integrations/evidence/EV-PI-001-protocol-verified.md`` for the
protocol facts this module was written against - all backed by raw captured
JSONL, not re-derived from the ``pi-delegate`` plugin's docs where the two
disagree). This is the ADAPTER edge D2 calls for: every pi verb, event
``type`` and field name below is native vocabulary that stops here - the
domain (``domain/harness.py``) never sees ``"agent_settled"`` or
``"queue_update"`` except carried opaquely in
:attr:`~okto_nexus.domain.harness.HarnessEvent.native_event`.

Wire shape (verified live, not assumed from the plugin's own docs):

* Command: ``{"type": "<verb>", ...fields}`` - ``id`` is accepted but never
  required and, load-bearingly, NEVER ECHOED BACK on any response observed
  across three raw capture files. Correlation is therefore ONLY possible via
  the response's ``command`` field, matched against the verb of the command
  most recently written - see mismatch note 3 below for why this connector
  serialises every correlated request behind one lock rather than attempting
  id-based correlation the wire does not support.
* Response: ``{"type":"response","command":"<verb>","success":bool,"data"?,
  "error"?}``.
* Framing: strict LF, one JSON object per line, no length-prefixing.
* There is NO ready/hello event. On spawn pi emits 0-7+ unsolicited
  ``extension_ui_request`` lines (UI noise from loaded extensions) before
  anything else. Readiness is "stdin accepted a write and a matching
  ``response`` envelope came back" - this connector proves that with a
  throwaway ``get_state`` probe in :meth:`PiRpcConnector.start`, never by
  waiting for the first bytes to arrive.
* It is a genuine PUSH protocol: after ``prompt``/``steer``, dozens to
  hundreds of unsolicited event lines stream on stdout with ZERO further
  client writes, until ``agent_settled`` (confirmed: 13 events for a plain
  turn, 300+ for a tool-using one with a mid-turn steer - see the protocol
  reference §4). ``events()`` below is a blocking generator fed by a
  dedicated reader thread; nothing in this module polls.
* Steering (``steer_timing=NEXT_TURN_BOUNDARY``): the internal
  ``queue_update`` fires immediately, but delivery to the model is deferred
  until the in-flight tool call's turn boundary (protocol reference §5).
* Abort/settle (``interrupt_requires_settle_wait=True``): ``agent_settled``
  for the ABORTED turn - not the ``response(abort,...)`` ack, which happens
  to arrive in the same batch but is not the semantically correct gate - is
  the only safe signal to send the next command. Getting this backwards is
  documented as "the classic hang" (protocol reference §6). Measured abort
  latency is ~2-30ms; this connector's timeouts are NOT sized to that figure
  (see the constructor's ``command_timeout_s``), only the *shape* of the
  gate (wait for ``agent_settled``, not a fixed sleep) is taken from it.
* Sessions persist across a full process kill when respawned with the same
  ``--session-id`` (protocol reference §7); see mismatch note 2 on why
  ``end`` therefore never deletes the on-disk session file.
* Malformed JSON and an unknown verb both come back as a clean
  ``{"success":false,"error":"..."}`` and the process stays alive (protocol
  reference §8); this connector treats ``success:false`` uniformly as the
  error-handling path for ``prompt``/``steer``/``abort`` (surfaced as a
  ``HarnessEvent(kind="error")``, never raised synchronously from
  :meth:`send`, which the port's own docstring says never blocks for a
  reply).

Threading model (no asyncio, matching the sibling connectors in this
package): :class:`HarnessConnector` is a synchronous Protocol, so a private
event loop thread buys nothing. This module uses ``subprocess.Popen`` plus
two daemon reader threads (stdout, stderr) - ``readline()`` blocking on a
pipe is not polling, and every correlated wait (``_PiTransport.request``)
blocks on a single bounded ``queue.Queue.get(timeout=...)``, never a sleep
loop, so ``SleepPollWaiter`` (D1) has no reason to appear and does not (see
``tests/test_harness_pi_connector.py`` for a structural check mirroring the
codex connector's own). :meth:`PiRpcConnector.events` is the one exception
worth calling out explicitly: it blocks on a BOUNDED
``Queue.get(timeout=_EVENTS_POLL_S)`` and re-checks a shutdown flag on each
timeout, rather than an unbounded ``get()`` - this is a periodic liveness
check for SHUTDOWN, never a poll for the events themselves (a real event
still satisfies ``get()`` immediately, exactly as an unbounded wait would).
See that method's docstring and mismatch note 9 for the defect this fixed:
an earlier unbounded-``get()`` design hung for real, for 17 minutes, in
review.

One connector instance owns exactly ONE pi child process for its lifetime
(``capabilities.multiplexes_sessions=False`` - pi is one session per
process, unlike codex): :meth:`start` may be called once; a second call
raises rather than silently spawning a second child the connector has no
slot to track.

Domain-level command payload convention (not part of the frozen port, but
kept consistent with ``codex.py``'s own choice so a supervisor can
build one ``HarnessCommand`` shape for both): ``send_turn``/``steer``
read their text from ``command.payload["text"]``, translated to pi's native
``{"message": ...}`` field at the wire edge.

See the module's "Known protocol-to-port mismatches" section (bottom of this
file) for every place pi's real shape does not fit the frozen port cleanly -
reported instead of smoothed over, per instructions.
"""

from __future__ import annotations

from .environment import child_environment

import itertools
import json
import os
import queue
import signal
import subprocess
import threading
from collections import deque
from typing import Any, Callable, Iterator, Mapping, Sequence

from ....domain.base import utc_now_iso
from ....domain.harness import (
    STATUS_STARTING,
    STEER_TIMING_NEXT_TURN_BOUNDARY,
    HarnessCapabilities,
    HarnessCommand,
    HarnessEvent,
    HarnessSession,
    new_harness_session_id,
)
from ....errors import ErrorCode, OktoNexusError

__all__ = ["PiRpcConnector"]

# --------------------------------------------------------------------------- #
# Native wire vocabulary (adapter-only; D2 forbids this crossing into domain)
# --------------------------------------------------------------------------- #
_VERB_PROMPT = "prompt"
_VERB_STEER = "steer"
_VERB_ABORT = "abort"
_VERB_GET_STATE = "get_state"

_TYPE_RESPONSE = "response"
_TYPE_EXTENSION_UI_REQUEST = "extension_ui_request"
_TYPE_EXTENSION_UI_RESPONSE = "extension_ui_response"
_TYPE_AGENT_SETTLED = "agent_settled"

#: Native top-level ``"type"`` -> normalised :data:`~okto_nexus.domain.harness.EVENT_KINDS`.
#: EVENT_KINDS has 5 members against pi's real top-level vocabulary
#: (``agent_start``, ``turn_start``, ``message_start``, ``message_update``,
#: ``message_end``, ``turn_end``, ``tool_execution_start/update/end``,
#: ``queue_update``, ``agent_end``, ``agent_settled``,
#: ``extension_ui_request``) - deliberately lossy, same shape as
#: ``codex.py``'s own mapping. Every native type not named here
#: (and every one that IS) is preserved verbatim in
#: :attr:`HarnessEvent.native_event`, so nothing is silently dropped, only
#: coarsened (INT-03's requirement). See mismatch note 1 for why
#: ``agent_settled`` -> ``turn_completed`` is not a complete answer.
_EVENT_KIND_BY_TYPE: dict[str, str] = {
    "turn_start": "turn_started",
    "turn_end": "turn_completed",
    _TYPE_AGENT_SETTLED: "turn_completed",
    "message_update": "output_delta",
}
#: Fallback bucket for every other real line (agent lifecycle bookkeeping,
#: message/tool-call lifecycle, queue_update, extension_ui_request noise):
#: still forwarded, just coarsely classified. Read ``native_event`` for the
#: real occurrence.
_DEFAULT_EVENT_KIND = "tool_activity"

#: Bounded wake-up period for the shutdown liveness check in
#: :meth:`PiRpcConnector.events` (see that method's docstring and the
#: defect note in the "Known protocol-to-port mismatches" section at the
#: bottom of this file). This is NOT polling for events - real events are
#: still delivered the instant they are pushed, since ``Queue.get(timeout=)``
#: returns immediately once an item is available; this only bounds how long
#: an IDLE call can block before it re-checks whether the connector closed.
_EVENTS_POLL_S = 1.0

#: RES-A3/B1/B3 fix: bound for `_PiTransport._read_stdout`'s cleanup wait on
#: the child (`_wait_for_exit_bounded`). This used to be a bare
#: `self._proc.wait()` with NO timeout at all - safe only under the
#: (false) assumption that the reader loop can exit ONLY via clean EOF,
#: i.e. the child is always already dying by the time this runs. It is
#: not: an uncaught exception escaping the loop (see RES-B1 - a
#: syntactically valid but pathologically deep JSON line makes
#: `json.loads` raise `RecursionError`, which `except json.JSONDecodeError`
#: does not catch) reaches the SAME wait against a child that is still
#: perfectly healthy, and it hung forever, confirmed by direct
#: instrumentation. Mirrors `close()`'s own `grace_s` default so the two
#: escalation ladders (this one and `close()`'s) behave consistently.
_READER_EXIT_WAIT_S = 5.0


# --------------------------------------------------------------------------- #
# Internal bookkeeping helpers
# --------------------------------------------------------------------------- #
class _StderrTail:
    """Bounded tail of the child's stderr, for attaching to a death report.

    Unbounded accumulation from a long-lived interactive-agent binary is a
    real memory-shaped failure; this caps it at the last 200 lines.
    """

    def __init__(self, maxlen: int = 200) -> None:
        self._lines: deque[str] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add(self, line: str) -> None:
        with self._lock:
            self._lines.append(line)

    def tail(self) -> str:
        with self._lock:
            return "\n".join(self._lines)


class _PiTransport:
    """Owns the child process and the strict-LF JSON-lines framing.

    Classifies every inbound line two ways: a ``{"type":"response",
    "command":...}`` envelope (a reply to a command we sent, correlated
    PURELY by the ``command`` field - see mismatch note 3), or anything else
    (a genuine push line, including ``extension_ui_request`` noise, which
    this transport auto-replies to on the spot - see mismatch note 5).
    Contains no pi-specific SEMANTICS (event-kind mapping, settle tracking)
    beyond that split; that is the connector's job.
    """

    def __init__(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None,
        env: Mapping[str, str] | None,
        on_push_event: Callable[[dict[str, Any]], None],
        on_unmatched_response: Callable[[dict[str, Any]], None],
        on_child_exit: Callable[[int | None, str], None],
        on_malformed_line: Callable[[str, str], None],
        on_line_processing_error: Callable[[str, str], None],
        on_reader_exit: Callable[[], None],
    ) -> None:
        self._argv = list(argv)
        self._cwd = cwd
        self._env = dict(env) if env is not None else None
        self._on_push_event = on_push_event
        self._on_unmatched_response = on_unmatched_response
        self._on_child_exit = on_child_exit
        self._on_malformed_line = on_malformed_line
        # RES-B1 fix: the ORIGINAL, narrower guard (`on_malformed_line`)
        # only ever covered `json.JSONDecodeError`. This is the broad
        # backstop - anything else a single line's parse or dispatch can
        # raise (RecursionError being the confirmed, reproduced case) -
        # kept as its own callback rather than folded into
        # `on_malformed_line` so the two remain distinguishable downstream.
        self._on_line_processing_error = on_line_processing_error
        # RES-B1/B2 fix: fired UNCONDITIONALLY, as the very last act of
        # `_read_stdout`, regardless of why or how it is exiting - even if
        # `_wait_for_exit_bounded`, `_fail_all_pending` or `_on_child_exit`
        # above it themselves raise. `on_child_exit` already signals
        # shutdown on the expected (unexpected-death) path; this is the
        # unconditional backstop underneath it so "a reader thread exiting
        # for ANY reason signals shutdown to EVERY consumer" holds even for
        # exit paths nobody has thought of yet, not only the ones this
        # module's own callbacks handle today.
        self._on_reader_exit = on_reader_exit

        self._proc: subprocess.Popen[str] | None = None
        self._write_lock = threading.Lock()
        self._request_lock = threading.Lock()  # one correlated command in flight (mismatch note 3)
        self._pending: dict[str, "queue.Queue[dict[str, Any]]"] = {}
        self._pending_lock = threading.Lock()
        self._stderr_tail = _StderrTail()
        self._closed = threading.Event()

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        full_env = child_environment(self._env)
        popen_kwargs: dict[str, Any] = dict(
            cwd=self._cwd,
            env=full_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,  # line-buffered - no framing beyond LF is expected
        )
        if os.name == "posix":
            # New process group so close() can kill the whole tree, not just
            # the immediate child (quality bar: leave no orphans).
            popen_kwargs["start_new_session"] = True
        self._proc = subprocess.Popen(self._argv, **popen_kwargs)
        threading.Thread(target=self._read_stdout, daemon=True, name="pi-stdout").start()
        threading.Thread(target=self._read_stderr, daemon=True, name="pi-stderr").start()

    def _fail_all_pending(self, reason: str) -> None:
        """Unblock EVERY caller parked in :meth:`request` immediately, with a
        synthetic failure response. Used both by an intentional :meth:`close`
        and (M2 fix) by an UNEXPECTED child exit: without this, a caller
        blocked in ``request()`` for a dead child sits out the full
        ``timeout_s`` even though the reader thread already knows the child
        is gone - up to the full 30s default, violating the port's "never
        blocks for a reply" contract far beyond what mismatch note 8
        discloses.
        """
        with self._pending_lock:
            pending = list(self._pending.items())
            self._pending.clear()
        for verb, reply_q in pending:
            reply_q.put({"type": _TYPE_RESPONSE, "command": verb, "success": False, "error": reason})

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stderr_tail(self) -> str:
        return self._stderr_tail.tail()

    # ------------------------------------------------------------------ #
    # Outbound
    # ------------------------------------------------------------------ #
    def _write(self, payload: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "pi rpc transport is not started.",
                {},
            )
        line = json.dumps(payload) + "\n"
        with self._write_lock:
            try:
                self._proc.stdin.write(line)
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise OktoNexusError(
                    ErrorCode.INTERNAL_ERROR,
                    "pi rpc stdin is closed (child likely died).",
                    {"stderr_tail": self.stderr_tail()},
                ) from exc

    def request(self, verb: str, fields: Mapping[str, Any], *, timeout_s: float) -> dict[str, Any]:
        """Correlated call - used for EVERY command this connector sends
        (``get_state`` as the readiness probe; ``prompt``/``steer``/
        ``abort`` for turn control). Serialised behind ``_request_lock`` so
        at most one command is ever awaiting a reply at a time: the wire has
        no ``id`` echo (see mismatch note 3), so ``command``-field
        correlation is only unambiguous when writes are strictly sequential.
        Blocks on a single ``Queue.get(timeout=...)``, never a poll loop.
        The lock acquire itself is ALSO bounded (not a bare ``with``): a
        caller waiting behind another already-in-flight ``request()`` is
        bounded by that call's own ``timeout_s`` transitively, but this
        makes the bound explicit rather than implicit, per the "every
        blocking wait has a timeout" rule this module holds itself to
        after the review that found :meth:`PiRpcConnector.events`'s
        unbounded wait (mismatch note 9).
        """
        acquired = self._request_lock.acquire(timeout=timeout_s)
        if not acquired:
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                f"pi transport was busy with another in-flight command; "
                f"could not send {verb!r} within {timeout_s}s.",
                {"verb": verb},
            )
        try:
            reply_q: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=1)
            with self._pending_lock:
                self._pending[verb] = reply_q
            self._write({"type": verb, **fields})
            try:
                return reply_q.get(timeout=timeout_s)
            except queue.Empty as exc:
                with self._pending_lock:
                    self._pending.pop(verb, None)
                raise OktoNexusError(
                    ErrorCode.INTERNAL_ERROR,
                    f"pi did not answer {verb!r} within {timeout_s}s.",
                    {"verb": verb, "stderr_tail": self.stderr_tail()},
                ) from exc
        finally:
            self._request_lock.release()

    def _reply_ui_request(self, request_id: Any) -> None:
        """Auto-cancel an ``extension_ui_request`` - bypasses
        ``_request_lock``/``_pending`` entirely (mismatch note 5): it is not
        a command this connector issued and expects no reply of its own, so
        routing it through the one-command-in-flight discipline would
        deadlock against a ``prompt``/``steer``/``abort`` request already
        holding that lock while its turn runs.
        """
        if request_id is None:
            return
        self._write({"type": _TYPE_EXTENSION_UI_RESPONSE, "id": request_id, "cancelled": True})

    # ------------------------------------------------------------------ #
    # Inbound
    # ------------------------------------------------------------------ #
    def _read_stdout(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            for raw_line in self._proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                self._process_line(line)
        finally:
            # RES-B1/B2 fix: everything below used to be a single flat
            # block, conditionally executed - if the (formerly unbounded)
            # `proc.wait()` never returned, NOTHING here ever ran, including
            # the shutdown signal. Split into an inner `finally` so the
            # unconditional shutdown signal (`_on_reader_exit`) fires no
            # matter what happens above it, and an outer one so a bounded
            # wait plus the existing death-reporting path still runs first
            # in the common case.
            try:
                if self._proc.stdout:
                    self._proc.stdout.close()
                returncode = self._wait_for_exit_bounded()
                if not self._closed.is_set():
                    # M2 fix: fail every in-flight request FIRST, before the
                    # (potentially slow, app-level) on_child_exit callback -
                    # a caller blocked in request() must not wait out its
                    # timeout just because the reader thread noticed the
                    # death first.
                    self._fail_all_pending("pi process exited unexpectedly (child death).")
                    self._on_child_exit(returncode, self.stderr_tail())
            finally:
                self._on_reader_exit()

    def _process_line(self, line: str) -> None:
        """Parse-and-dispatch ONE line, never letting it kill the reader
        thread (RES-B1). A single bad line - malformed JSON, syntactically
        VALID JSON that is still pathological (a pathologically deep,
        balanced array makes ``json.loads`` raise ``RecursionError``, NOT
        ``json.JSONDecodeError`` - confirmed live, see the RES-B1 evidence),
        or a future push-event shape ``_dispatch`` does not yet handle -
        must be surfaced as an ``error`` event and the loop must CONTINUE,
        never die silently. ``except Exception`` (not a bare
        ``except BaseException``) deliberately: ``RecursionError`` IS an
        ``Exception`` subclass (``RecursionError`` -> ``RuntimeError`` ->
        ``Exception``), so this already covers it, while still letting a
        genuine ``KeyboardInterrupt``/``SystemExit`` propagate rather than
        being swallowed by a background daemon thread.
        """
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            # Unchanged from before this fix - the narrow, original guard.
            self._safe_call(self._on_malformed_line, line, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - RES-B1's actual failure class
            # The broad backstop this fix adds: `json.loads` can raise
            # something that is NOT `json.JSONDecodeError` for a line that
            # IS syntactically valid JSON (`RecursionError` on a
            # pathologically deep balanced array, confirmed live). Routed
            # through a SEPARATE callback (not `on_malformed_line`) so the
            # two failure classes stay distinguishable in the event stream
            # rather than conflating "the JSON was bad" with "the JSON was
            # fine but something else about this line broke us".
            self._safe_call(self._on_line_processing_error, line, f"{type(exc).__name__}: {exc}")
            return
        try:
            self._dispatch(msg)
        except Exception as exc:  # noqa: BLE001 - a future dispatch bug must not repeat RES-B1
            self._safe_call(self._on_line_processing_error, line, f"dispatch failed: {type(exc).__name__}: {exc}")

    @staticmethod
    def _safe_call(callback: Callable[[str, str], None], line: str, error: str) -> None:
        # The callback itself (ultimately `_push_event`) must not be able to
        # put us back in the exact hole this method exists to climb out of -
        # if IT raises, swallow that here rather than let it escape back
        # into `_read_stdout`'s main loop and kill the reader thread anyway.
        try:
            callback(line, error)
        except Exception:  # noqa: BLE001 - see comment above; this is the backstop itself
            pass

    def _wait_for_exit_bounded(self, timeout_s: float = _READER_EXIT_WAIT_S) -> int | None:
        """RES-A3/B3 fix: the reader thread's cleanup used to call
        ``self._proc.wait()`` with NO timeout at all, reached from the
        SAME ``finally`` for two very different exits - a clean EOF (child
        already exiting; this normally returns near-instantly) and an
        exception escaping the loop above (the child may still be perfectly
        healthy, simply idle on stdin) - and treated the two identically,
        which is backwards: only the second case can hang forever, and it
        is also the one where nothing has yet told the child to go away.
        Escalates exactly like :meth:`close` (SIGTERM, then SIGKILL) rather
        than inventing a second unbounded wait for the same problem - every
        blocking wait in this module now carries a timeout.
        """
        if self._proc is None:
            return None
        try:
            return self._proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            pass
        self._terminate_group()
        try:
            return self._proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            pass
        self._kill_group()
        try:
            return self._proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            # Truly stuck even past SIGKILL (e.g. an uninterruptible D-state
            # child). Do not block the one thread whose job is to notice
            # this over it any further - report what we can (`poll()` is
            # non-blocking) and let the death-report event carry the
            # ambiguity forward instead.
            return self._proc.poll()

    def _read_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        for raw_line in self._proc.stderr:
            self._stderr_tail.add(raw_line.rstrip("\n"))

    def _dispatch(self, msg: dict[str, Any]) -> None:
        if not isinstance(msg, dict):
            # Valid JSON but not an object (e.g. a bare string/number) - not
            # a shape either the response or push-event paths can use.
            self._on_malformed_line(json.dumps(msg), "top-level JSON value is not an object")
            return
        if msg.get("type") == _TYPE_RESPONSE:
            verb = msg.get("command")
            with self._pending_lock:
                reply_q = self._pending.pop(verb, None) if isinstance(verb, str) else None
            if reply_q is not None:
                reply_q.put(msg)
            else:
                # A response with no matching in-flight request - anomalous
                # (this connector never fires two commands without waiting
                # for the first's reply) but must not be silently dropped.
                self._on_unmatched_response(msg)
            return
        if msg.get("type") == _TYPE_EXTENSION_UI_REQUEST:
            self._reply_ui_request(msg.get("id"))
        self._on_push_event(msg)

    def close(self, *, grace_s: float = 5.0) -> None:
        self._closed.set()
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._terminate_group()
            try:
                self._proc.wait(timeout=grace_s)
            except subprocess.TimeoutExpired:
                self._kill_group()
                try:
                    self._proc.wait(timeout=grace_s)
                except subprocess.TimeoutExpired:
                    pass  # gave it every reasonable chance; move on
        # Unblock anyone parked in request(): fail every still-pending call.
        self._fail_all_pending("connector closed")

    def _terminate_group(self) -> None:
        if self._proc is None:
            return
        if os.name == "posix":
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
                return
            except (ProcessLookupError, PermissionError, OSError):
                pass
        try:
            self._proc.terminate()
        except OSError:
            pass

    def _kill_group(self) -> None:
        if self._proc is None:
            return
        if os.name == "posix":
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
                return
            except (ProcessLookupError, PermissionError, OSError):
                pass
        try:
            self._proc.kill()
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# The connector
# --------------------------------------------------------------------------- #
class PiRpcConnector:
    """``pi --mode rpc`` connector - implements ``HarnessConnector`` (D4).

    ONE instance owns ONE ``pi`` child process for its whole lifetime
    (``capabilities.multiplexes_sessions=False``): :meth:`start` mints a
    session id, spawns ``pi --mode rpc --session-id <id> [...]``, and blocks
    on a throwaway ``get_state`` probe as the readiness signal (protocol
    reference §1 - there is no ready event; the first response envelope IS
    readiness). A second :meth:`start` call on the same instance raises
    rather than silently orphaning or replacing the first child.
    """

    def __init__(
        self,
        *,
        command: Sequence[str] = ("pi", "--mode", "rpc"),
        provider: str | None = None,
        model: str | None = None,
        extra_args: Sequence[str] = (),
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        handshake_timeout_s: float = 30.0,
        command_timeout_s: float = 30.0,
    ) -> None:
        self.capabilities = HarnessCapabilities(
            send_only=False,
            steer_timing=STEER_TIMING_NEXT_TURN_BOUNDARY,
            interrupt_requires_settle_wait=True,
            multiplexes_sessions=False,
            observes_session_end=True,
        )
        self._command = list(command)
        self._provider = provider
        self._model = model
        self._extra_args = list(extra_args)
        self._cwd = cwd
        self._env = env
        self._handshake_timeout_s = handshake_timeout_s
        self._command_timeout_s = command_timeout_s

        self._start_lock = threading.Lock()
        self._transport: _PiTransport | None = None

        self._session_lock = threading.Lock()
        self._session_id: str | None = None
        self._owning_agent_id: str | None = None
        self._ended = False
        # Non-None from the moment `interrupt` is issued until this
        # session's ABORTED turn reports its own `agent_settled` (protocol
        # reference §6) - the internal expression of
        # `interrupt_requires_settle_wait` the port's `send()` signature has
        # no vocabulary for (mismatch 4). Tracked as a GENERATION token (an
        # int minted per `interrupt()` call), not a bare bool (C1 fix): pi's
        # wire carries no per-turn id on `agent_settled` at all (verified
        # against every raw capture - see mismatch note 3's correlation
        # discussion), so this cannot do true cross-turn correlation: what
        # it DOES buy is (a) a single, named place the "is one owed" check
        # and the "clear it" write both go through instead of a bare
        # true/false flip, and (b) `_interrupt` can now roll its OWN
        # generation back on failure (M1 fix) without racing a concurrent
        # `agent_settled` that legitimately cleared a *different* pending
        # generation. `_second_interrupt_while_awaiting_settle` still
        # forbids two live generations at once, so at most one is ever
        # outstanding - reported honestly, not oversold as full turn
        # correlation the wire does not support.
        self._awaiting_settle_generation: int | None = None
        self._next_settle_generation = itertools.count(1)

        # C2 fix: a SINGLE shared `queue.Queue` (the pre-fix design) means
        # every consumer of `events()` competes for the SAME items - two
        # concurrent callers (or two calls from different threads) SPLIT the
        # stream between them rather than each independently seeing the
        # whole thing, directly contradicting this module's own note 9 claim
        # that a second/later `events()` call is a safe, independent
        # consumer. Fan-out instead: `_event_history` is the append-only
        # record of every event ever pushed (never trimmed - a session's
        # event count is bounded by its own lifetime, not unbounded), and
        # each `events()` call gets its OWN subscriber queue, seeded with a
        # snapshot of the history taken under `_history_lock` at subscribe
        # time (so a LATE subscriber still gets everything from the start,
        # not just what is pushed after it subscribes) and then fed live by
        # `_push_event`. `_history_lock` also serialises history-append
        # against backlog-snapshot so a push can never land in the gap
        # between a new subscriber's snapshot and its registration (see
        # `_push_event`/`events()`).
        self._event_history: list[HarnessEvent] = []
        self._history_lock = threading.Lock()
        self._subscribers: list["queue.Queue[HarnessEvent]"] = []
        # Set exactly once, by close() or an unexpected child exit. events()
        # polls this (bounded by _EVENTS_POLL_S) instead of relying on a
        # single-consumption sentinel object in the queue - see that
        # method's docstring and mismatch note 9 for why: a sentinel can
        # only ever be seen by ONE generator instance, silently stranding
        # any OTHER caller of events() (or a second call by the same
        # caller) on an unbounded Queue.get() forever.
        self._closed_event = threading.Event()

    # ------------------------------------------------------------------ #
    # HarnessConnector protocol
    # ------------------------------------------------------------------ #
    def start(self, *, owning_agent_id: str) -> HarnessSession:
        with self._start_lock:
            if self._transport is not None:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    "this connector already owns a live pi session "
                    "(multiplexes_sessions=False); start a new connector "
                    "instance per session.",
                    {},
                )
            session_id = new_harness_session_id()
            with self._session_lock:
                self._session_id = session_id
                self._owning_agent_id = owning_agent_id
                self._ended = False
                self._awaiting_settle_generation = None

            argv = self._build_argv(session_id)
            transport = _PiTransport(
                argv,
                cwd=self._cwd,
                env=self._env,
                on_push_event=self._on_push_event,
                on_unmatched_response=self._on_unmatched_response,
                on_child_exit=self._on_child_exit,
                on_malformed_line=self._on_malformed_line,
                on_line_processing_error=self._on_line_processing_error,
                on_reader_exit=self._on_reader_exit,
            )
            try:
                # transport.start() is INSIDE this try too (C3 audit): a
                # Popen failure (e.g. the binary is not on PATH) raises
                # before any OktoNexusError-only except could ever catch it,
                # which is precisely the kind of second, untested exit path
                # this audit is meant to find.
                transport.start()
                # Readiness probe (protocol reference §1): a cheap, harmless,
                # idempotent verb that works even before any turn has ever
                # run. Its CONTENT is ignored - only the fact that a
                # `response` envelope with `command == "get_state"` arrived
                # matters (regardless of `success`).
                transport.request(_VERB_GET_STATE, {}, timeout_s=self._handshake_timeout_s)
            except BaseException:
                transport.close()
                with self._session_lock:
                    self._ended = True
                # C3 fix: transport.close() only sets the TRANSPORT's own
                # `_closed` Event (suppresses ITS on_child_exit callback) -
                # it has no way to reach the CONNECTOR's separate
                # `_closed_event`, which is what events() actually checks on
                # every queue.Empty. Without this, a failed start() leaves
                # events() looping forever: a real reproduction found in
                # review of the SAME unbounded-wait class mismatch note 9
                # claims was eliminated module-wide, reintroduced here via a
                # second, untested path that never went through close().
                # Caught as BaseException (not just OktoNexusError) so every
                # way start() can fail - not only the one this connector
                # itself raises - still leaves events() terminable.
                self._closed_event.set()
                raise

            self._transport = transport

        return HarnessSession(
            session_id=session_id,
            harness_kind="pi",
            owning_agent_id=owning_agent_id,
            status=STATUS_STARTING,
            capabilities=self.capabilities,
            started_at=utc_now_iso(),
            metadata={"pi_session_id": session_id},
        )

    def send(self, session: HarnessSession, command: HarnessCommand) -> None:
        self._validate_session(session)
        transport = self._transport
        if transport is None or not transport.is_alive():
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "pi process is not running.",
                {
                    "session_id": session.session_id,
                    "stderr_tail": transport.stderr_tail() if transport else "",
                },
            )
        if command.verb == "send_turn":
            self._send_turn(command)
        elif command.verb == "steer":
            self._steer(command)
        elif command.verb == "interrupt":
            self._interrupt(command)
        elif command.verb == "end":
            self._end(command)
        else:  # pragma: no cover - HarnessCommand.__post_init__ already closes this set
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "unknown command verb.", {"verb": command.verb})

    def events(self) -> Iterator[HarnessEvent]:
        """Blocking generator, bounded so it can NEVER block forever, and
        with its OWN independent fan-out subscription (C2 fix) - calling
        this a second time, or from a second thread, no longer SPLITS the
        stream with the first caller (the pre-fix defect: one shared
        ``queue.Queue`` meant two concurrent consumers each got roughly
        half the events, unpredictably, with no way to tell which half).
        Each call registers a fresh per-consumer queue, seeded with every
        event pushed since the connector started (see ``_event_history`` on
        ``__init__``) so a LATE subscriber - a supervisor that reconnects,
        or simply calls this after the turn already started - still gets
        the full stream from the beginning, not just what happens to be
        pushed after it subscribes.

        Real events are still delivered the instant they are pushed - a
        ``Queue.get(timeout=_EVENTS_POLL_S)`` returns immediately once an
        item exists, exactly like an unbounded ``get()`` would, so this is
        NOT polling for events (D1 is not violated: nothing here re-checks
        store state in a sleep loop). The timeout only bounds how long an
        IDLE wait can run before re-checking :attr:`_closed_event`, so a
        call to this method - EVEN A SECOND OR LATER CALL, EVEN FROM ANOTHER
        THREAD - always terminates within one poll period of :meth:`close`,
        never later. This replaces an earlier single-consumption sentinel
        design that could only ever be observed by ONE generator instance,
        found in review to deadlock any second caller of :meth:`events` (or
        the same caller invoking it twice) on an unbounded wait with no
        timeout at all - see mismatch note 9.
        """
        my_queue: "queue.Queue[HarnessEvent]" = queue.Queue()
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
    # Lifecycle helpers (not part of the port; connector-owned resources)
    # ------------------------------------------------------------------ #
    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
        self._closed_event.set()

    # ------------------------------------------------------------------ #
    # Command translation
    # ------------------------------------------------------------------ #
    def _build_argv(self, pi_session_id: str) -> list[str]:
        argv = list(self._command) + ["--session-id", pi_session_id]
        if self._provider:
            argv += ["--provider", self._provider]
        if self._model:
            argv += ["--model", self._model]
        argv += list(self._extra_args)
        return argv

    def _extract_text(self, command: HarnessCommand) -> str:
        text = command.payload.get("text")
        if not isinstance(text, str) or not text:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "command.payload['text'] must be a non-empty string.",
                {"verb": command.verb, "payload": command.payload},
            )
        return text

    def _validate_session(self, session: HarnessSession) -> None:
        with self._session_lock:
            session_id = self._session_id
            ended = self._ended
        if session_id is None or session.session_id != session_id:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "no live pi session with this id on this connector.",
                {"session_id": session.session_id},
            )
        if ended:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "this pi session has already ended.",
                {"session_id": session.session_id},
            )

    def _guard_not_awaiting_settle(self, verb: str) -> None:
        """Enforce ``interrupt_requires_settle_wait=True`` (mismatch 4): the
        port's ``send()`` has no return channel to say "not yet", so this
        raises ``CONFLICT`` rather than racing the aborted turn's own
        teardown - the exact hang the protocol reference's §6 warns about.
        """
        with self._session_lock:
            awaiting = self._awaiting_settle_generation is not None
        if awaiting:
            raise OktoNexusError(
                ErrorCode.CONFLICT,
                f"cannot {verb}: waiting for the aborted turn's agent_settled "
                "first (interrupt_requires_settle_wait=True); retry after the "
                "next agent_settled event.",
                {"verb": verb},
            )

    def _surface_if_rejected(self, response: Mapping[str, Any]) -> None:
        """``success:false`` is pi's clean, non-fatal error path (protocol
        reference §8) - surfaced as an event, never raised synchronously
        from :meth:`send` (which the port's docstring says never blocks for
        a reply).
        """
        if response.get("success") is False:
            self._push_event("error", _TYPE_RESPONSE, dict(response))

    def _send_turn(self, command: HarnessCommand) -> None:
        text = self._extract_text(command)
        self._guard_not_awaiting_settle(command.verb)
        response = self._transport.request(_VERB_PROMPT, {"message": text}, timeout_s=self._command_timeout_s)  # type: ignore[union-attr]
        self._surface_if_rejected(response)

    def _steer(self, command: HarnessCommand) -> None:
        text = self._extract_text(command)
        self._guard_not_awaiting_settle(command.verb)
        response = self._transport.request(_VERB_STEER, {"message": text}, timeout_s=self._command_timeout_s)  # type: ignore[union-attr]
        self._surface_if_rejected(response)

    def _interrupt(self, command: HarnessCommand) -> None:
        with self._session_lock:
            if self._awaiting_settle_generation is not None:
                raise OktoNexusError(
                    ErrorCode.CONFLICT,
                    "an interrupt is already pending its aborted turn's "
                    "agent_settled; wait for it before issuing another one.",
                    {"session_id": command.session_id},
                )
            generation = next(self._next_settle_generation)
            self._awaiting_settle_generation = generation
        try:
            # M1 fix: this call can itself raise (e.g. `request()` timing
            # out on the ack, or the transport's write failing outright).
            # The OLD code set the gate BEFORE this call and only cleared it
            # on a reply that never arrived on this path - wedging every
            # future send_turn/steer behind a CONFLICT whose own message
            # promises a retry-after-agent_settled event that was never
            # going to come, permanently, even though pi itself was alive
            # and reachable. Any exception here now rolls the gate back.
            response = self._transport.request(_VERB_ABORT, {}, timeout_s=self._command_timeout_s)  # type: ignore[union-attr]
        except BaseException:
            with self._session_lock:
                if self._awaiting_settle_generation == generation:
                    self._awaiting_settle_generation = None
            raise
        if response.get("success") is False:
            # The abort write itself was rejected - there is no aborted turn
            # to wait a settle out for, so release the gate immediately
            # rather than blocking every future send_turn/steer forever.
            with self._session_lock:
                if self._awaiting_settle_generation == generation:
                    self._awaiting_settle_generation = None
        self._surface_if_rejected(response)

    def _end(self, command: HarnessCommand) -> None:
        """No wire verb means "end this session" (mismatch 2): the correct
        way to end a pi RPC session is closing stdin / killing the process,
        which is exactly what a full connector teardown does. Because
        ``multiplexes_sessions=False`` (one connector IS one session), that
        teardown is total - unlike codex's ``thread/unsubscribe``, there is
        no shared child left running afterward to preserve. This does NOT
        delete the on-disk session ``.jsonl`` (protocol reference §7); that
        would destroy the very persistence property the evidence proves.
        """
        with self._session_lock:
            self._ended = True
        self.close()

    # ------------------------------------------------------------------ #
    # Inbound translation (native pi line -> domain HarnessEvent)
    # ------------------------------------------------------------------ #
    def _on_push_event(self, msg: dict[str, Any]) -> None:
        native_type = msg.get("type")
        if not isinstance(native_type, str) or not native_type:
            native_type = "unknown"
        if native_type == _TYPE_AGENT_SETTLED:
            # The one signal that clears the settle-wait gate (mismatch 1 /
            # mismatch 4) - tracked off the REAL native type, never off
            # `kind`, precisely because EVENT_KINDS collapses several
            # distinct native types into "turn_completed". Clears whichever
            # generation is outstanding (see the C1 comment on
            # `_awaiting_settle_generation`'s declaration for why this is
            # honestly a single-outstanding-generation clear, not true
            # per-turn correlation - the wire gives this connector nothing
            # to correlate against).
            with self._session_lock:
                self._awaiting_settle_generation = None
        kind = _EVENT_KIND_BY_TYPE.get(native_type, _DEFAULT_EVENT_KIND)
        self._push_event(kind, native_type, msg)

    def _on_unmatched_response(self, msg: dict[str, Any]) -> None:
        """A response envelope with no matching in-flight request. Should
        not happen under this connector's own one-command-in-flight
        discipline, but a stray/duplicate line from the child must not be
        silently dropped (D2: no native occurrence is lost, only coarsened).
        """
        self._push_event("error", _TYPE_RESPONSE, msg)

    def _on_child_exit(self, returncode: int | None, stderr_tail: str) -> None:
        with self._session_lock:
            self._ended = True
            self._awaiting_settle_generation = None
        self._push_event(
            "error",
            "pi/process_exited",
            {"returncode": returncode, "stderr_tail": stderr_tail},
        )
        self._closed_event.set()

    def _on_malformed_line(self, line: str, error: str) -> None:
        self._push_event(
            "error",
            "pi/transport_malformed_line",
            {"line": line, "error": error},
        )

    def _on_line_processing_error(self, line: str, error: str) -> None:
        """RES-B1 fix: the broad backstop, distinct from
        :meth:`_on_malformed_line`. Fires for anything a single line's
        parse (e.g. ``RecursionError`` on a pathologically deep but
        syntactically VALID JSON line - confirmed live, not theoretical) or
        dispatch can raise that is NOT a ``json.JSONDecodeError``. Kept as
        its own native type rather than folded into
        ``pi/transport_malformed_line`` so "the JSON was invalid" and "the
        JSON was fine but something else about processing this line broke"
        stay distinguishable to anything consuming this event stream.
        """
        self._push_event(
            "error",
            "pi/transport_line_processing_error",
            {"line": line, "error": error},
        )

    def _on_reader_exit(self) -> None:
        """RES-B1/B2 fix: called UNCONDITIONALLY as the reader thread's
        very last act (see ``_PiTransport._read_stdout``'s inner
        ``finally``), regardless of why or how it is exiting - even past a
        failure in ``_wait_for_exit_bounded``, ``_fail_all_pending`` or
        ``_on_child_exit`` themselves. ``threading.Event.set()`` is
        idempotent, so this composes cleanly with the two OTHER places that
        already set the same event (:meth:`_on_child_exit` for an
        unexpected death, :meth:`close` for an intentional one): whichever
        of them runs, every current and future :meth:`events` consumer is
        guaranteed to observe shutdown within one ``_EVENTS_POLL_S`` period,
        by construction, not by hoping every upstream step happened to
        succeed.
        """
        self._closed_event.set()

    def _push_event(self, kind: str, native_type: str, payload: dict[str, Any]) -> None:
        session_id = self._session_id
        if session_id is None:
            return  # defensive: cannot happen on the real start()/close() paths
        event = HarnessEvent(
            session_id=session_id,
            harness_kind="pi",
            kind=kind,
            native_event=native_type,
            occurred_at=utc_now_iso(),
            payload=payload,
        )
        # C2 fix: append to the durable history and fan out to every LIVE
        # subscriber under the same lock a new `events()` call uses to take
        # its backlog snapshot - this is what makes the snapshot-then-
        # subscribe in `events()` race-free: whichever of {this push,
        # a concurrent subscribe} takes the lock first fully happens before
        # the other, so a new subscriber can never miss an event that raced
        # its own registration, and never sees it twice.
        with self._history_lock:
            self._event_history.append(event)
            subscribers = list(self._subscribers)
        for subscriber_queue in subscribers:
            subscriber_queue.put(event)


# --------------------------------------------------------------------------- #
# Known protocol-to-port mismatches (reported, not smoothed over)
# --------------------------------------------------------------------------- #
# 1. `EVENT_KINDS` has no member for `agent_settled` - the ONE native event a
#    supervisor MUST branch on to honour `interrupt_requires_settle_wait=True`
#    (the port's own `interrupt_requires_settle_wait` docstring says exactly
#    this). This is a direct collision with `domain/harness.py`'s own claim
#    that "the domain never inspects [native_event], only carries it for
#    traceability" (D2/D4/D6/D7): here, correct supervisor behaviour is
#    IMPOSSIBLE without inspecting `native_event`. This connector maps
#    `agent_settled` -> `kind="turn_completed"` (the least-wrong bucket - it
#    IS a completion signal) but `turn_end` ALSO maps to `turn_completed` and
#    fires earlier and more often (once per intra-turn tool-continuation
#    boundary, confirmed in the protocol reference §3's tool-turn sequence)
#    than `agent_settled` (once per whole exchange). A supervisor that reacts
#    to `kind=="turn_completed"` alone to decide "safe to send the next
#    command" will send too early. This connector does NOT rely on `kind` for
#    its OWN internal settle-wait gate (`_on_push_event` checks
#    `native_type == "agent_settled"` directly) - proof that the escape hatch
#    is necessary, not merely convenient.
#
# 2. `COMMAND_VERBS` includes `end`; pi's RPC protocol has no wire verb that
#    means it (the full verified verb set is `prompt`, `steer`, `abort`,
#    `get_last_assistant_text`, `get_state`, `get_session_stats`,
#    `extension_ui_response` - protocol reference §2). Ending a pi session is
#    achieved by closing stdin / killing the process, not any command. Since
#    `multiplexes_sessions=False` (one connector IS one session, unlike
#    codex's shared child), this connector maps `end` to a FULL teardown
#    (`close()`) rather than a partial detach - there is nothing else running
#    on the process to preserve. It deliberately does NOT delete the
#    on-disk `~/.pi/agent/sessions/<cwd-slug>/<ts>_<session-id>.jsonl` file;
#    doing so would destroy the exact persist-across-process-kill property
#    proven live in protocol reference §7. "end" means "detach", not
#    "forget" - the domain has no vocabulary to distinguish those two and
#    this connector picked the non-destructive reading.
#
# 3. The wire has NO id-based correlation at all - verified by grepping every
#    `"type":"response"` line across all three raw capture files: not one
#    carries an `id` field, including the `{"command":"parse", ...}` error
#    for malformed input (a verb this connector never sent). The command
#    envelope's documented `{"id"?, ...}` shape accepts an id but pi never
#    echoes it back. This connector therefore serialises every correlated
#    request (`get_state`/`prompt`/`steer`/`abort`) behind one lock so at
#    most one command is ever awaiting a reply, and correlates purely by the
#    response's `command` field - not a stylistic borrow from
#    `pi-companion.mjs`'s own queue discipline, but the ONLY correlation
#    scheme the wire supports. A caller that fired two different verbs
#    concurrently without this discipline would have no way to tell which
#    response belongs to which.
#
# 4. `interrupt_requires_settle_wait=True` has no expression in
#    `HarnessConnector.send()`'s signature - the port docstring states send()
#    "never blocks for a reply" and there is no out-of-band channel to say
#    "not yet". This connector enforces the guard itself: `send_turn` and
#    `steer` both raise `CONFLICT` if called while an issued interrupt's
#    `agent_settled` has not yet arrived, rather than silently queuing (which
#    pi has no queue for outside of `steer`'s own next-turn-boundary
#    mechanism) or writing straight through and racing the aborted turn's
#    teardown - the exact hang protocol reference §6 calls "the classic
#    hang". A supervisor built strictly against the Protocol's type
#    signature alone has no way to learn this guard exists except by reading
#    this connector's source or catching the raised error; the port gives
#    connectors no vocabulary for "temporarily unavailable, retry after an
#    event".
#
# 5. `extension_ui_request` sits entirely outside the frozen command/event
#    vocabulary: it is neither a `COMMAND_VERB` a supervisor would issue nor
#    an occurrence a supervisor needs to react to, yet it MUST be answered on
#    the wire or (per the protocol reference) it "queues up as noise". This
#    connector auto-replies `{"type":"extension_ui_response","cancelled":
#    true}` to every one, unconditionally, bypassing the request/response
#    correlation lock entirely (mismatch 3) since a ui-response expects no
#    reply of its own and would deadlock against an in-flight `prompt`/
#    `steer`/`abort` otherwise. It is ALSO forwarded as a
#    `HarnessEvent(kind="tool_activity")` purely for traceability, per the
#    task's "handle deliberately" instruction. There is no port-level way for
#    a supervisor that does NOT want ui noise in its event stream to ask this
#    connector to suppress it.
#
# 6. `get_state`, `get_last_assistant_text` and `get_session_stats` - three
#    real, useful, side-effect-free pi verbs - have no representation in
#    `COMMAND_VERBS` at all. This connector uses `get_state` internally ONLY
#    as the readiness probe (protocol reference §1), never exposes it through
#    `send()`. A caller wanting "what did pi just say"
#    (`get_last_assistant_text`) or session stats has no port-level way to
#    ask for it short of accumulating `message_end`/`turn_end` payloads out
#    of the ordinary event stream itself.
#
# 7. `SESSION_STATUSES`' `STARTING` has no legal `STARTING -> ENDED`
#    transition (mirrors `codex.py`'s own mismatch note 5): this
#    connector's `start()` happens to never expose that gap on its own happy
#    path, because the `get_state` readiness probe is SYNCHRONOUS and
#    blocking - a dead-on-arrival child (crash before the first response) is
#    caught inside `start()` itself (which raises, never returning a
#    `HarnessSession` at all) rather than surfacing as a session stuck in
#    `STARTING` forever. It remains a live gap for the supervisor's
#    transition table in general, just not one this specific connector's
#    `start()` shape can trigger.
#
# 8. This connector's `send()` is NOT purely fire-and-forget at the wire
#    level, unlike `codex.py`'s `send_fire_and_forget` (which never
#    waits for even the ack). Because mismatch 3 forces one-command-in-flight
#    correlation, `_send_turn`/`_steer`/`_interrupt` all block briefly
#    (bounded by `command_timeout_s`) on the IMMEDIATE ack response
#    (`response(prompt,success:true)` etc, before `send()` returns. The HAPPY
#    PATH latency for that ack, per the raw captures, is ms-to-low-hundreds-
#    of-ms - but that is NOT the worst case (an earlier revision of this note
#    understated it as if it were). The WORST case is the full configured
#    `command_timeout_s` (30s by default): if pi is wedged, or the process
#    has died without the reader thread having noticed yet, `send()` blocks
#    for the entire timeout before raising. This is consistent with the port
#    docstring's letter - `send()`'s RETURN VALUE never carries the reply,
#    which is the contract's actual promise - but it is a real, and in the
#    worst case NOT small, blocking window `codex.py` does not have,
#    traded deliberately for the correlation safety mismatch 3 requires on a
#    wire with no id echo. (The child-death sub-case of this worst case is
#    now bounded much tighter in practice by the M1/M2 fixes in note 10:
#    a detected child exit fails every pending `request()` immediately
#    rather than waiting out the full timeout.)
#
# 9. DEFECT FOUND IN REVIEW, FIXED - recorded because it is the single most
#    valuable thing an integrator of this connector needs to know. The
#    first version of `PiRpcConnector.events()` was an UNBOUNDED
#    `self._event_queue.get()` loop, terminated by a single sentinel object
#    (`_SHUTDOWN`) pushed once by `close()`/an unexpected child exit. A
#    plain `Queue` sentinel is SINGLE-CONSUMPTION: only the ONE generator
#    instance whose `get()` happens to dequeue it ever sees it. A test that
#    called `connector.events()` a second time after a first caller (a
#    background pump thread inside a test helper) had already drained that
#    sentinel hung for 17 REAL minutes on an unbounded wait with no timeout
#    at all and no `pi` process anywhere in sight - exactly the "unbounded
#    queue.get() ... in the connector or your test double" hazard flagged in
#    this task's own brief, and it was real, not a flaky environment. Root
#    cause: a single-consumption shutdown signal is unsafe for a method that
#    a caller might reasonably invoke more than once (a supervisor retrying
#    after a reconnect, or - as here - two independent consumers of the same
#    connector's event stream). FIX: shutdown is now a `threading.Event`
#    (`_closed_event`), checked on every `queue.Empty` from a
#    `Queue.get(timeout=_EVENTS_POLL_S)` (module-level constant, currently
#    1.0s) rather than encoded as an item IN the queue at all - EVERY caller,
#    called ANY number of times, from ANY thread, now observes shutdown
#    within one poll period, and the "no polling for events" property (D1)
#    is preserved because real events still satisfy `get()` immediately;
#    only the IDLE-shutdown-detection path is bounded-and-rechecked instead
#    of unbounded. `_PiTransport.request()`'s `_request_lock` acquisition
#    was also changed from a bare `with` (implicitly bounded only via the
#    lock-holder's own eventual timeout) to an explicit
#    `acquire(timeout=timeout_s)` that raises `INTERNAL_ERROR` on expiry,
#    for the same reason: every blocking wait in this module now has an
#    explicit, own timeout, not a transitive one.
#
# 10. FIVE MORE DEFECTS FOUND IN ADVERSARIAL REVIEW, FIXED - a second pass
#    after note 9, all reproduced with a failing test before the fix:
#    a) C1 - the fake server this module's own test file used to simulate pi
#       answered `response(abort,success:true)` THE INSTANT it read the
#       abort command, then completed the aborted turn (`agent_settled`)
#       ~20ms later. Our OWN captured protocol reference (§6(b)) proves the
#       REAL wire order is the opposite: `agent_settled` for the aborted
#       turn arrives BEFORE the ack. Rebuilding the fake to match the real
#       order made `test_interrupt_blocks_further_sends_until_agent_settled`
#       and `test_second_interrupt_while_awaiting_settle_raises_conflict`
#       both fail immediately (interrupt() returned with the gate already
#       clear, because on the real reader thread the settle event is
#       dispatched - and clears the gate - before the ack line is even
#       read). Those two tests were rewritten to assert what is actually
#       true given the real order (a reprompt immediately after interrupt()
#       returns CAN legitimately succeed, since agent_settled - the
#       semantically correct gate per §6(b) - already fired) and to instead
#       prove the gate holds DURING the real race window: while `interrupt()`
#       is still blocked waiting on the delayed ack, a concurrent send_turn
#       from another thread must get CONFLICT. `_awaiting_settle` was also
#       promoted from a bare bool to a generation token (see its declaration
#       on `__init__`) so `_interrupt` can roll back its OWN pending state on
#       failure (feeds into M1 below) without ambiguity about which
#       "settle-wait" it is clearing.
#    b) C2 - `events()` fed every caller off ONE shared `queue.Queue`: two
#       concurrent consumers split the stream, each seeing an unpredictable
#       subset, contradicting this module's own note-9-era claim that a
#       second/later `events()` call is an independent, safe consumer.
#       Reproduced: after one `send_turn`, two threads each calling
#       `events()` - thread A got all 17 events through `agent_settled`,
#       thread B got ZERO and was still blocked after an 8s join. FIX:
#       fan-out - `_event_history` (append-only) plus one subscriber queue
#       per `events()` call, race-free by construction (see `_push_event`).
#    c) C3 - a failed `start()` called `transport.close()`, which only sets
#       the TRANSPORT's own `_closed` Event, never the CONNECTOR's separate
#       `_closed_event` that `events()` actually checks. Reproduced: a fake
#       pi that never acks `get_state` made `start()` raise `INTERNAL_ERROR`
#       as expected, then `list(conn.events())` did not finish in 5s - the
#       SAME unbounded-wait class note 9 fixed, reintroduced via a second,
#       untested exit path. FIX: `start()`'s except clause now sets
#       `_closed_event` too, and was widened from `except OktoNexusError`
#       to `except BaseException` (and now wraps `transport.start()` itself,
#       not just the readiness probe) so no way of failing to start leaves
#       this gap open again.
#    d) M1 - `_interrupt` set the settle-wait gate BEFORE writing `abort`,
#       then blocked on the ack; if that raised (e.g. a timeout), the
#       function exited via the exception and never reached the code that
#       would have cleared the gate. Reproduced with a fake pi that accepts
#       abort but never answers it: `interrupt()` timed out, the gate stayed
#       set, and every subsequent `send_turn`/`interrupt` raised `CONFLICT`
#       forever - even though `CONFLICT`'s own message promises a retry
#       after the next `agent_settled`, which was never coming, and pi
#       itself was alive and reachable throughout. FIX: `_interrupt` now
#       wraps the abort `request()` in try/except and rolls its own
#       generation back on ANY exception before re-raising.
#    e) M2 - `_on_child_exit` never drained `_PiTransport._pending` nor
#       closed the transport, so a caller blocked in `request()` waited out
#       the FULL `command_timeout_s` even though the reader thread detected
#       the child's exit immediately. Reproduced: a fake pi that
#       `os._exit()`s the instant it reads `abort`, with
#       `command_timeout_s=2.0` - `send(interrupt)` took the full 2.0s to
#       raise instead of failing within milliseconds of the exit being
#       detected. FIX: `_read_stdout`'s exit path now fails every pending
#       `request()` immediately (`_fail_all_pending`, factored out of and
#       shared with `close()`) before invoking the `on_child_exit` callback.
