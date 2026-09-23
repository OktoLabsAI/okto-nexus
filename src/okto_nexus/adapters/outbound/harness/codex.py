"""Codex ``app-server`` connector - the D6 leg of the harness transport port.

Implements :class:`okto_nexus.application.ports.HarnessConnector` against
``codex app-server`` (codex-cli 0.144.6, JSON-RPC 2.0 over child stdio; see
``docs/design/0004-harness-integrations.md`` D6 and
``docs/harness-integrations/evidence/`` for the protocol facts this module
was written against). This is the ADAPTER edge D2 calls for: every codex
method name, param shape and event name below is native vocabulary that
stops here - the domain (``domain/harness.py``) never sees a ``threadId``,
a ``turnId`` or a string like ``"turn/completed"`` except carried opaquely
in :attr:`~okto_nexus.domain.harness.HarnessEvent.native_event`.

Param and event shapes were read directly off
``codex app-server generate-json-schema`` against the installed 0.144.6
binary (not re-derived from the ADR's prose), so property names
(``threadId``, ``expectedTurnId``, the ``sandbox``/``approvalPolicy``
fields on ``thread/start``, ...) are exact, not guessed.

Threading model (no asyncio): :class:`HarnessConnector` is a synchronous
Protocol, so a private event loop thread would buy nothing. This module
uses ``subprocess.Popen`` plus two daemon reader threads (stdout, stderr) -
the same shape ``tests/conftest.py``'s ``real_server`` fixture (EV-INF-001)
uses to drain a child's pipes without deadlocking on a full buffer.
``readline()`` blocking on a pipe is not polling; nothing in this module
sleeps in a loop or re-polls a flag, so ``SleepPollWaiter`` (D1) has no
reason to appear here and does not (see
``tests/test_harness_codex_connector.py`` for a structural check).
:meth:`CodexAppServerConnector.events` is the one deliberate exception:
it blocks on a BOUNDED ``Queue.get(timeout=_EVENTS_POLL_S)`` and re-checks
a shutdown flag on each timeout, rather than an unbounded ``get()`` woken by
a single-consumption sentinel - see that method's docstring and mismatch
note 9 for the defect this fixed (a sentinel only one generator instance
can ever observe, found in review to hang a second caller of ``events()``
forever). Every other blocking wait in this module - the handshake, every
correlated ``request()``, the stdin write lock, the reader thread's own
``proc.wait()`` on exit - is likewise bounded with an explicit timeout, per
the same standing rule.

See the module docstring's "Known protocol-to-port mismatches" section
(bottom of this file) for every place codex's real shape does not fit the
frozen port cleanly - reported instead of smoothed over, per instructions.
"""

from __future__ import annotations

from .owned_process import spawn_owned_process, observe_owned_process
from .framing import FrameLimitExceeded, protocol_lines, stderr_chunks
from .event_buffers import NativeEventHistory, subscribe, stop_overflowed_process

from .environment import child_environment

import json
import hashlib
import queue
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping, Sequence

from ....domain.base import utc_now_iso
from ....domain.harness import (
    STATUS_STARTING,
    STEER_TIMING_IMMEDIATE,
    HarnessCapabilities,
    HarnessCommand,
    HarnessEvent,
    HarnessSession,
    new_harness_session_id,
)
from ....errors import ErrorCode, OktoNexusError

__all__ = ["CodexAppServerConnector"]

# --------------------------------------------------------------------------- #
# Native wire vocabulary (adapter-only; D2 forbids this crossing into domain)
# --------------------------------------------------------------------------- #
_METHOD_INITIALIZE = "initialize"
_METHOD_THREAD_START = "thread/start"
_METHOD_THREAD_RESUME = "thread/resume"
_METHOD_THREAD_FORK = "thread/fork"
_METHOD_THREAD_INJECT_ITEMS = "thread/inject_items"
_METHOD_THREAD_UNSUBSCRIBE = "thread/unsubscribe"
_METHOD_TURN_START = "turn/start"
_METHOD_TURN_STEER = "turn/steer"
_METHOD_TURN_INTERRUPT = "turn/interrupt"

#: Notifications that carry ``turn.id`` as the active-turn signal for a
#: thread (used to answer "what is the current turnId?" for steer/interrupt,
#: since :meth:`CodexAppServerConnector.send` never awaits ``turn/start``'s
#: own response - see the mismatch note on turn-id tracking below).
_METHOD_TURN_STARTED = "turn/started"
_METHOD_TURN_COMPLETED = "turn/completed"

def _extract_thread_id(params: dict[str, Any]) -> str | None:
    """Resolve a notification's thread id, live-verified against 0.144.6.

    Most notifications carry a top-level ``threadId`` string (confirmed:
    ``item/started``, ``item/completed``, ``turn/started``,
    ``thread/status/changed``, ``warning``, ...). ``thread/started`` is the
    one exception observed live: its params are ``{"thread": {"id": ...,
    ...}}`` with NO top-level ``threadId`` at all - the JSON Schema dump
    names a ``ThreadStartedNotification`` type but this module was fixed
    against the REAL wire shape, not that schema entry (never inspected in
    detail; the live capture is authoritative). Checked in this order so a
    top-level ``threadId`` always wins when both could theoretically be
    present.
    """
    thread_id = params.get("threadId")
    if isinstance(thread_id, str):
        return thread_id
    thread_obj = params.get("thread")
    if isinstance(thread_obj, dict):
        nested = thread_obj.get("id")
        if isinstance(nested, str):
            return nested
    return None

#: Native notification method -> normalised :data:`~okto_nexus.domain.harness.EVENT_KINDS`.
#: EVENT_KINDS has 5 members against ~68 real codex notification methods -
#: this mapping is deliberately lossy (see the mismatch note); every native
#: method not named here (and every one that IS) is preserved verbatim in
#: :attr:`HarnessEvent.native_event`, so nothing is silently dropped, only
#: coarsened (INT-03's requirement).
_EVENT_KIND_BY_METHOD: dict[str, str] = {
    "error": "error",
    # Synthetic native_event this connector itself mints for a late ERROR
    # response to a fire-and-forget send() (see mismatch note 7) - not a
    # real codex notification method, but classified the same way.
    "jsonrpc/error_response": "error",
    # Synthetic native_event strings this connector mints on its own
    # transport/lifecycle failures (child death, an unparseable line, a
    # structurally-valid-but-domain-invalid notification that blew up
    # dispatch - see mismatch note 10). These are NOT routine tool activity;
    # EVENT_KINDS has an "error" slot built for exactly this, and
    # `observes_session_end=True` depends on `process/exited` being
    # distinguishable from noise.
    "process/exited": "error",
    "transport/malformed_line": "error",
    "transport/dispatch_error": "error",
    _METHOD_TURN_STARTED: "turn_started",
    _METHOD_TURN_COMPLETED: "turn_completed",
    "item/agentMessage/delta": "output_delta",
    "item/reasoning/summaryTextDelta": "output_delta",
    "item/reasoning/textDelta": "output_delta",
    "item/plan/delta": "output_delta",
}
#: Fallback bucket for every other real event (item lifecycle, token usage,
#: rate limits, status changes, diffs, plans, ...): still forwarded, just
#: coarsely classified. Read ``native_event`` for the real occurrence.
_DEFAULT_EVENT_KIND = "tool_activity"

#: Bounded wake-up period for the shutdown liveness check in
#: :meth:`CodexAppServerConnector.events` (mirrors ``harness/pi.py``'s own
#: ``_EVENTS_POLL_S`` - see that module's mismatch note 9 for the defect
#: class both connectors independently shipped and this constant fixes).
#: NOT polling for events: a real event still satisfies
#: ``Queue.get(timeout=...)`` immediately; this only bounds how long an IDLE
#: wait can block before re-checking whether the connector closed.
_EVENTS_POLL_S = 1.0

#: Bound on the reader thread's own ``proc.wait()`` once its stdout loop
#: ends (child exited, or a dispatch failure forced the loop to stop
#: draining stdout). The child is normally already dead by the time this
#: runs; the timeout exists so a wedged/zombied child cannot block this
#: thread forever (the standing "every blocking wait has a timeout" rule).
_PROC_WAIT_TIMEOUT_S = 5.0

#: Bound on acquiring ``_CodexTransport._write_lock``. A write blocks
#: holding this lock only if the child has stopped reading stdin (a full
#: pipe); without a bound, every OTHER sender queues up behind it forever -
#: the same wedge shape as an unbounded ``Queue.get()``.
_STDIN_WRITE_LOCK_TIMEOUT_S = 10.0

_EARLY_EVENT_LIMIT = 128
_EARLY_EVENT_BYTES = 1024 * 1024
_THREAD_START_LIMIT = 64


class EarlyEventLimitExceeded(RuntimeError):
    """Connection attribution is incomplete; retrying may duplicate work."""


def _client_info() -> dict[str, str]:
    return {"name": "okto-nexus", "version": "harness-integrations-d6", "title": None}


# --------------------------------------------------------------------------- #
# Internal bookkeeping (never the port's HarnessSession - see its docstring:
# "never persisted... the supervisor's in-memory bookkeeping record". This
# connector keeps its OWN private record so it can demux and validate
# without assuming it owns the port-shaped object callers hold.)
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class _ThreadState:
    session_id: str
    thread_id: str
    owning_agent_id: str
    active_turn_id: str | None = None
    ended: bool = False
    closing: bool = False
    close_unconfirmed: bool = False
    pending_start_id: int | None = None


class _StderrTail:
    """Bounded tail of the child's stderr, for attaching to a death report.

    Unbounded accumulation from a chatty ``[experimental]`` binary is a real
    memory-shaped failure; this caps it at the last 200 lines.
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


class _CodexTransport:
    """Owns the child process and the JSON-RPC 2.0 stdio framing.

    Classifies every inbound line three ways (a response to a request we
    sent, a server-initiated notification, or a server-initiated REQUEST -
    ``ServerRequest`` in the schema has ten methods, e.g.
    ``item/tool/call``, that carry BOTH ``id`` and ``method`` and are NOT
    notifications; treating them as one would leave codex waiting forever
    for a reply codex is entitled to expect) and dispatches to the
    connector-supplied callbacks. Contains no codex-specific SEMANTICS
    (event-kind mapping, turn tracking) - that is the connector's job.
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: str | None,
        env: Mapping[str, str] | None,
        on_notification: Callable[[str, dict[str, Any]], None],
        on_unmatched_response: Callable[[Any, Any, dict[str, Any] | None], None],
        on_child_exit: Callable[[int | None, str], None],
        on_malformed_line: Callable[[str, str], None],
        on_dispatch_error: Callable[[str, str], None],
        on_server_request: Callable | None = None,
    ) -> None:
        self._command = list(command)
        self._cwd = cwd
        self._env = dict(env) if env is not None else None
        self._on_notification = on_notification
        self._on_unmatched_response = on_unmatched_response
        self._on_child_exit = on_child_exit
        self._on_malformed_line = on_malformed_line
        self._on_dispatch_error = on_dispatch_error
        self._on_server_request = on_server_request

        self._proc: subprocess.Popen[str] | None = None
        self._write_lock = threading.Lock()
        self._id_lock = threading.Lock()
        self._next_id = 1
        self._pending: dict[int, queue.Queue[Any]] = {}
        self._pending_lock = threading.Lock()
        self._stderr_tail = _StderrTail()
        self._closed = threading.Event()

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        full_env = child_environment(self._env)
        try:
            self._proc = spawn_owned_process(
                self._command,
                cwd=self._cwd,
                env=full_env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,  # line-buffered - no framing beyond LF is expected
            )
        except OSError as exc:
            # Matches the house pattern claude_code_stream.py's start() uses
            # for the identical subprocess.Popen() call - a missing/
            # unreadable binary is a CONFIG_ERROR, not a raw FileNotFoundError
            # leaking past this module's own error-classification convention.
            raise OktoNexusError(
                ErrorCode.CONFIG_ERROR,
                f"failed to spawn codex app-server binary {self._command[0]!r}: {exc}",
                {"binary": self._command[0], "argv": list(self._command)},
            ) from exc
        threading.Thread(target=self._read_stdout, daemon=True, name="codex-stdout").start()
        threading.Thread(target=self._read_stderr, daemon=True, name="codex-stderr").start()

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stderr_tail(self) -> str:
        return self._stderr_tail.tail()

    # ------------------------------------------------------------------ #
    # Outbound
    # ------------------------------------------------------------------ #
    def _allocate_id(self) -> int:
        with self._id_lock:
            request_id = self._next_id
            self._next_id += 1
            return request_id

    def _write(self, payload: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "codex app-server transport is not started.",
                {},
            )
        line = json.dumps(payload) + "\n"
        acquired = self._write_lock.acquire(timeout=_STDIN_WRITE_LOCK_TIMEOUT_S)
        if not acquired:
            # A write blocks holding this lock only if the child has stopped
            # reading stdin (a full pipe) - without a bound, every OTHER
            # sender would queue up behind it forever, the same wedge shape
            # as an unbounded Queue.get(). See the standing "every blocking
            # wait has a timeout" rule and mismatch note 10.
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                f"codex app-server stdin write lock was not acquired within "
                f"{_STDIN_WRITE_LOCK_TIMEOUT_S}s (a concurrent write may be "
                "stuck on a full pipe; the child is likely unresponsive).",
                {"stderr_tail": self.stderr_tail()},
            )
        try:
            try:
                self._proc.stdin.write(line)
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise OktoNexusError(
                    ErrorCode.INTERNAL_ERROR,
                    "codex app-server stdin is closed (child likely died).",
                    {"stderr_tail": self.stderr_tail()},
                ) from exc
        finally:
            self._write_lock.release()

    def request(self, method: str, params: Mapping[str, Any], *, timeout_s: float) -> Any:
        """Correlated call - used ONLY for the handshake (``initialize``,
        ``thread/start``). Blocks on a single ``Queue.get(timeout=...)``,
        never a poll loop. Forbidden for :meth:`send`-issued commands (D2's
        "no correlated reply" contract) - see the module's mismatch note on
        why the handshake still needs correlation.
        """
        request_id = self._allocate_id()
        reply_q: queue.Queue[Any] = queue.Queue(maxsize=1)
        with self._pending_lock:
            if self._closed.is_set():
                raise OktoNexusError(ErrorCode.INTERNAL_ERROR, "codex transport is closed.", {})
            self._pending[request_id] = reply_q
        try:
            self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)})
        except BaseException:
            with self._pending_lock:
                self._pending.pop(request_id, None)
            raise
        try:
            kind, value = reply_q.get(timeout=timeout_s)
        except queue.Empty as exc:
            with self._pending_lock:
                self._pending.pop(request_id, None)
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                f"codex app-server did not answer {method!r} within {timeout_s}s.",
                {"method": method, "stderr_tail": self.stderr_tail()},
            ) from exc
        if kind == "error":
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                f"codex app-server rejected {method!r}: {value.get('message')}",
                {"method": method, "codex_error": value},
            )
        return value

    def send_fire_and_forget(self, method: str, params: Mapping[str, Any], *, on_allocated=None) -> int:
        """Send a request whose response is NOT awaited by the caller (D2).

        Returns the allocated id so the connector can correlate a LATE
        error response (if any) back to a session for surfacing as a
        :class:`~okto_nexus.domain.harness.HarnessEvent` - see
        :meth:`_CodexTransport.request`'s docstring and the mismatch note
        "an unwaited response is not a discarded response".
        """
        request_id = self._allocate_id()
        if on_allocated is not None:
            on_allocated(request_id)
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)})
        return request_id

    def reply_method_not_found(self, request_id: Any) -> None:
        """Answer a server->client REQUEST we do not implement.

        Unsupported native requests receive JSON-RPC -32601. This is a
        visible limitation, never an implicit approval or sandbox bypass.
        """
        self._write(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": "Method not implemented by okto-nexus connector"},
            }
        )

    def reply_result(self, request_id, result):
        self._write({"jsonrpc": "2.0", "id": request_id, "result": result})

    # ------------------------------------------------------------------ #
    # Inbound
    # ------------------------------------------------------------------ #
    def _read_stdout(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            for raw_line in protocol_lines(self._proc.stdout):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError as exc:
                    self._on_malformed_line(line, str(exc))
                    continue
                try:
                    self._dispatch(msg)
                except EarlyEventLimitExceeded:
                    raise
                except Exception as exc:  # noqa: BLE001 - see mismatch note 10
                    # A JSON-RPC-LEGAL but domain-invalid message (e.g. an
                    # empty "method", or "params" shaped as a JSON array
                    # where dict-shaped params are assumed) must never kill
                    # this loop: the child is still alive and stdout must
                    # keep being drained, or its pipe fills and everything
                    # wedges. Surfaced as an error event instead, and the
                    # callback itself is guarded so a failure IN reporting
                    # the failure still cannot escape this loop.
                    try:
                        self._on_dispatch_error(line, repr(exc))
                    except Exception:  # noqa: BLE001 - never let the guard itself wedge the reader
                        pass
        except EarlyEventLimitExceeded as exc:
            self._proc.kill()
            self._on_dispatch_error("", str(exc))
        except FrameLimitExceeded as exc:
            self._proc.kill()
            self._on_malformed_line("", str(exc))
        finally:
            if self._proc.stdout:
                self._proc.stdout.close()
            returncode: int | None = None
            try:
                returncode = self._proc.wait(timeout=_PROC_WAIT_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                # The stdout loop only reaches here once the pipe is closed
                # (the child already exited) or a dispatch failure forced an
                # early exit - proc.wait() should return almost immediately.
                # A bound exists anyway per the standing "every blocking
                # wait has a timeout" rule: a wedged reader thread here would
                # never reach _on_child_exit, so _closed_event would never
                # be set and a supervisor could wait on events() forever.
                self._proc.kill()
                try:
                    returncode = self._proc.wait(timeout=_PROC_WAIT_TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    returncode = None
            was_closed = self._closed.is_set()
            self._fail_pending("codex child exited before replying")
            if not was_closed:
                self._on_child_exit(returncode, self.stderr_tail())

    def _read_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        for raw_line in stderr_chunks(self._proc.stderr):
            self._stderr_tail.add(raw_line.rstrip("\n"))

    def _dispatch(self, msg: dict[str, Any]) -> None:
        has_id = "id" in msg
        has_method = "method" in msg
        if has_id and not has_method:
            # A response (result or error) to a request we sent.
            request_id = msg["id"]
            with self._pending_lock:
                reply_q = self._pending.pop(request_id, None)
            if "error" in msg:
                payload: dict[str, Any] = msg["error"]
                if reply_q is not None:
                    reply_q.put(("error", payload))
                else:
                    self._on_unmatched_response(request_id, None, payload)
            else:
                result = msg.get("result")
                if reply_q is not None:
                    reply_q.put(("result", result))
                else:
                    self._on_unmatched_response(request_id, result, None)
        elif has_method and has_id:
            # Server -> client REQUEST (ServerRequest.json): NOT a
            # notification. Must be answered or the turn can hang.
            if not self._on_server_request or not self._on_server_request(msg["id"], msg["method"], msg.get("params")):
                self.reply_method_not_found(msg["id"])
        elif has_method:
            # Server -> client notification (no id).
            self._on_notification(msg["method"], msg.get("params") or {})
        # else: neither id nor method - not a JSON-RPC message we recognise;
        # silently ignored (no callback contract for it exists on this port).

    def close(self, *, grace_s: float = 5.0) -> None:
        self._closed.set()
        if self._proc is None:
            return
        if self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=grace_s)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=grace_s)
        self._fail_pending("connector closed")

    def _fail_pending(self, reason: str) -> None:
        # EOF during initialize must release startup capacity immediately,
        # even when the connector has not yet installed this transport.
        with self._pending_lock:
            self._closed.set()
            pending = list(self._pending.items())
            self._pending.clear()
        for _request_id, reply_q in pending:
            reply_q.put_nowait(("error", {"code": -1, "message": reason}))


# --------------------------------------------------------------------------- #
# The connector
# --------------------------------------------------------------------------- #
class CodexAppServerConnector:
    """``codex app-server`` connector - implements ``HarnessConnector`` (D6).

    ONE instance owns ONE ``codex app-server`` child process and MULTIPLEXES
    every session started against it over that single stdio connection
    (``capabilities.multiplexes_sessions=True``), demuxing inbound events by
    ``threadId``/``turnId`` (ADR 0004 D6). :meth:`start` therefore does NOT
    spawn a new child per call - only the FIRST call spawns the process and
    performs the ``initialize`` handshake; every subsequent call issues a
    ``thread/start`` on the SAME connection. See the module's mismatch note
    "multiplexes_sessions has no expression in the port" for why this is an
    implicit contract rather than something the Protocol states.

    Every ``thread/start`` defaults to ``approvalPolicy="on-request"`` and
    ``sandbox="read-only"``. Only an explicitly approved runtime profile
    may override those controls. The approval bridge is tracked separately;
    an unsupported native request currently gets an explicit protocol error.
    Sandbox request values use the native string form.
    """

    event_stream_contract_version = 2

    def __init__(
        self,
        *,
        command: Sequence[str] = ("codex", "app-server"),
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        handshake_timeout_s: float = 30.0,
        thread_start_overrides: Mapping[str, Any] | None = None,
    ) -> None:
        self.capabilities = HarnessCapabilities(
            send_only=False,
            steer_timing=STEER_TIMING_IMMEDIATE,
            interrupt_requires_settle_wait=False,
            multiplexes_sessions=True,
            observes_session_end=True,
        )
        self._command = command
        self._cwd = cwd
        self._env = env
        self._handshake_timeout_s = handshake_timeout_s
        self._thread_start_overrides = dict(thread_start_overrides or {})

        self._transport: _CodexTransport | None = None
        self._start_lock = threading.Lock()
        # Lifetime attempts, including uncertain starts: never recycle a native
        # allocation on timeout or discard attribution of late ended-thread events.
        self._thread_start_attempts = 0

        # Native stream v2 retains a bounded replay window. Live consumers
        # receive ordered independent queues; durable history belongs to Nexus.
        self._event_history = NativeEventHistory()
        self._history_lock = threading.Lock()
        self._subscribers: list["queue.Queue[HarnessEvent]"] = []
        self._subscriber_sessions = {}
        self._sessions_by_id: dict[str, _ThreadState] = {}
        self._sessions_by_thread: dict[str, _ThreadState] = {}
        self._sessions_lock = threading.RLock()
        self._turn_changed = threading.Condition(self._sessions_lock)
        self._close_settle_timeout_s = 2.5
        # Set exactly once, by close() or an unexpected child exit. events()
        # polls this (bounded by _EVENTS_POLL_S) instead of relying on a
        # single-consumption sentinel object in the queue - see that
        # method's docstring and mismatch note 9 for why: a sentinel can
        # only ever be seen by ONE generator instance, silently stranding
        # any OTHER caller of events() (or a second call by the same
        # caller) on an unbounded Queue.get() forever.
        self._closed_event = threading.Event()

        # Events for a threadId that arrived before start()'s thread/start
        # response registered the mapping - see the "thread/started can
        # race the response" mismatch note. Held briefly, then replayed.
        self._unmapped_thread_events: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        self._early_event_count = 0
        self._early_event_bytes = 0
        self._early_event_failed = False

        # Pending fire-and-forget request ids -> the session an ERROR
        # response (if any) should be surfaced against.
        self._ff_pending: dict[int, tuple[str, str]] = {}
        self._ff_pending_lock = threading.Lock()
        self.native_approvals_enabled = False
        self._approval_requests = {}

    # ------------------------------------------------------------------ #
    # HarnessConnector protocol
    # ------------------------------------------------------------------ #
    def start(self, *, owning_agent_id: str) -> HarnessSession:
        with self._start_lock:
            if self._thread_start_attempts >= _THREAD_START_LIMIT:
                raise OktoNexusError(ErrorCode.CONFLICT,
                    "Codex connection thread capacity exhausted; use a fresh connection.",
                    {"reason": "connection_thread_capacity", "limit": _THREAD_START_LIMIT})
            if self._early_event_failed:
                raise EarlyEventLimitExceeded("early_event_limit_exceeded")
            if self._transport is None:
                self._spawn_and_initialize()
            self._thread_start_attempts += 1

        thread_start_params: dict[str, Any] = {
            "approvalPolicy": "on-request",
            "sandbox": "read-only",
        }
        thread_start_params.update(self._thread_start_overrides)
        result = self._transport.request(  # type: ignore[union-attr]
            _METHOD_THREAD_START, thread_start_params, timeout_s=self._handshake_timeout_s
        )
        thread_id = result["thread"]["id"]

        session_id = new_harness_session_id()
        state = _ThreadState(session_id=session_id, thread_id=thread_id, owning_agent_id=owning_agent_id)
        with self._sessions_lock:
            if self._early_event_failed:
                raise EarlyEventLimitExceeded("early_event_limit_exceeded")
            self._sessions_by_id[session_id] = state
            self._sessions_by_thread[thread_id] = state
            replay = self._unmapped_thread_events.pop(thread_id, [])
            self._early_event_count -= len(replay)
            self._early_event_bytes -= sum(self._early_event_size(method, params)
                                           for method, params in replay)
            # Replay before newer notifications can overtake registration, and
            # apply native turn state as well as publishing the buffered event.
            for method, params in replay:
                self._on_notification(method, params)

        return HarnessSession(
            session_id=session_id,
            harness_kind="codex",
            owning_agent_id=owning_agent_id,
            status=STATUS_STARTING,
            capabilities=self.capabilities,
            started_at=utc_now_iso(),
            metadata={"thread_id": thread_id},
        )

    def send(self, session: HarnessSession, command: HarnessCommand) -> None:
        with self._sessions_lock:
            state = self._sessions_by_id.get(session.session_id)
        if state is None or state.ended or (state.closing and command.verb != "end"):
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "no live codex thread for this session (never started, or already ended).",
                {"session_id": session.session_id},
            )
        if self._transport is None or not self._transport.is_alive():
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "codex app-server process is not running.",
                {"session_id": session.session_id, "stderr_tail": self._transport.stderr_tail() if self._transport else ""},
            )

        if command.verb == "send_turn":
            self._send_turn(state, command)
        elif command.verb == "steer":
            self._steer(state, command)
        elif command.verb == "interrupt":
            self._interrupt(state, command)
        elif command.verb == "end":
            self._end(state)
        else:  # pragma: no cover - HarnessCommand.__post_init__ already closes this set
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "unknown command verb.", {"verb": command.verb})

    def events_for_session(self, session_id):
        return self.events(session_id=session_id)

    def observe_lifecycle(self, session):
        result = observe_owned_process(self._transport._proc if self._transport else None)
        with self._sessions_lock:
            state = self._sessions_by_id.get(session.session_id)
            result["active_turn"] = bool(state and (
                state.active_turn_id or state.pending_start_id is not None or state.close_unconfirmed))
        return result

    def events(self, *, session_id=None) -> Iterator[HarnessEvent]:
        """Native stream v2: bounded replay, explicit expiration/overflow.

        Durable replay uses Nexus journal/SQLite, not this transient history.
        Each subscriber has a bounded independent queue; gaps raise explicitly.
        Idle waits only check shutdown and never poll native protocol status.
        """
        with self._history_lock:
            my_queue, backlog = subscribe(self._event_history, self._subscribers, session_id=session_id)
            self._subscriber_sessions[my_queue] = session_id
        try:
            for item in backlog:
                if session_id is None or item.session_id == session_id:
                    yield item
            while True:
                try:
                    item = my_queue.get(timeout=_EVENTS_POLL_S)
                except queue.Empty:
                    if self._closed_event.is_set():
                        return
                    if session_id is not None:
                        with self._sessions_lock:
                            state = self._sessions_by_id.get(session_id)
                            if state is None or state.ended:
                                return
                    continue
                if session_id is None or item.session_id == session_id:
                    yield item
        finally:
            with self._history_lock:
                try:
                    self._subscribers.remove(my_queue)
                    self._subscriber_sessions.pop(my_queue, None)
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
    def _text_input(self, command: HarnessCommand) -> list[dict[str, Any]]:
        text = command.payload.get("text")
        if not isinstance(text, str) or not text:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "command.payload['text'] must be a non-empty string.",
                {"verb": command.verb, "payload": command.payload},
            )
        return [{"type": "text", "text": text}]

    def _send_turn(self, state: _ThreadState, command: HarnessCommand) -> None:
        params: dict[str, Any] = {"threadId": state.thread_id, "input": self._text_input(command)}
        self._send_request(state, _METHOD_TURN_START, params)

    def _send_request(self, state, method, params, *, allow_closing=False):
        def register(request_id):
            # Register BEFORE the external write, without holding either lock
            # while writing. Fast native replies cannot outrun attribution.
            with self._turn_changed:
                if state.ended or (state.closing and not allow_closing):
                    raise OktoNexusError(ErrorCode.CONFLICT, "Codex thread is closing.", {})
                if method == _METHOD_TURN_START and (state.active_turn_id or state.pending_start_id is not None):
                    raise OktoNexusError(ErrorCode.CONFLICT, "Codex thread already has a pending or active turn.", {})
                with self._ff_pending_lock:
                    if len(self._ff_pending) >= 64:
                        raise OktoNexusError(ErrorCode.CONFLICT, "Codex pending request capacity exhausted.", {})
                    self._ff_pending[request_id] = (state.session_id, method)
                if method == _METHOD_TURN_START:
                    state.pending_start_id = request_id
        return self._transport.send_fire_and_forget(method, params, on_allocated=register)

    def _steer(self, state: _ThreadState, command: HarnessCommand) -> None:
        if state.active_turn_id is None:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "cannot steer: no active turn on this codex thread.",
                {"session_id": state.session_id},
            )
        params = {
            "threadId": state.thread_id,
            "expectedTurnId": command.expected_turn_id or state.active_turn_id,
            "input": self._text_input(command),
        }
        self._send_request(state, _METHOD_TURN_STEER, params)

    def _interrupt(self, state: _ThreadState, command: HarnessCommand | None = None) -> None:
        if state.active_turn_id is None:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "cannot interrupt: no active turn on this codex thread.",
                {"session_id": state.session_id},
            )
        params = {"threadId": state.thread_id, "turnId": (command.expected_turn_id if command else None) or state.active_turn_id}
        self._send_request(state, _METHOD_TURN_INTERRUPT, params)

    def _end(self, state: _ThreadState) -> None:
        """Interrupt an observed active turn, await its terminal, then detach.

        An interrupt response is not completion. A deadline leaves the binding
        uncertain; never kill sibling threads to manufacture a stopped state.
        """
        deadline = time.monotonic() + self._close_settle_timeout_s
        with self._turn_changed:
            if state.closing:
                return
            state.closing = True
            self._turn_changed.wait_for(
                lambda: state.pending_start_id is None or state.active_turn_id is not None,
                timeout=max(0, deadline - time.monotonic()))
            state.close_unconfirmed = state.pending_start_id is not None
            turn_id = state.active_turn_id
        if turn_id is not None:
            params = {"threadId": state.thread_id, "turnId": turn_id}
            self._send_request(state, _METHOD_TURN_INTERRUPT, params, allow_closing=True)
            with self._turn_changed:
                settled = self._turn_changed.wait_for(
                    lambda: state.active_turn_id != turn_id or self._closed_event.is_set(),
                    timeout=max(0, deadline - time.monotonic()),
                )
                state.close_unconfirmed = not settled or state.active_turn_id is not None
        if state.close_unconfirmed:
            self._push_event(state.session_id, "transport/close_unsettled",
                {"reason": "turn_start_or_interrupt_terminal_not_observed", "turn_id": turn_id},
                thread_id=state.thread_id, turn_id=turn_id)
        params = {"threadId": state.thread_id}
        self._send_request(state, _METHOD_THREAD_UNSUBSCRIBE, params, allow_closing=True)
        with self._sessions_lock:
            state.ended = True
            # Deliberately NOT popped from _sessions_by_thread (see mismatch
            # note 11): a turn already in flight when end() is called keeps
            # emitting trailing item/*/turn/completed notifications for this
            # exact thread_id afterward. _unmapped_thread_events exists ONLY
            # to hold events that race thread/start's own RESPONSE (replayed
            # once, by THIS thread_id being registered) - a thread_id that
            # is never re-registered (ids are never reused) would strand
            # them there permanently instead. Keeping the mapping alive lets
            # _emit_for_thread keep routing those trailing events through
            # the normal push path, so a supervisor still observes the
            # turn's real completion instead of losing it silently. send()
            # already rejects this session (state.ended) for any FURTHER
            # command, so nothing can be issued against a "live" ended
            # thread by mistake.

    # ------------------------------------------------------------------ #
    # Handshake
    # ------------------------------------------------------------------ #
    def _spawn_and_initialize(self) -> None:
        """Spawn the child and complete the ``initialize`` handshake.

        ``self._transport`` is assigned ONLY after ``initialize`` succeeds
        (see mismatch note 12). ``start()``'s own spawn guard is "is
        ``self._transport`` set" - assigning it earlier meant a failed/timed-
        out handshake left a non-``None`` transport behind, so every FUTURE
        ``start()`` skipped re-spawning entirely and fired ``thread/start``
        straight at a connection that never finished initializing,
        permanently wedging the connector. On failure here the half-spawned
        transport (and its child process) is torn down before the exception
        propagates, so a subsequent ``start()`` call gets a clean respawn.

        RES-A4 fix (mirrors ``harness/pi.py``'s own C3 fix): this failure
        path used to call ``transport.close()`` only - that sets the
        TRANSPORT's own private ``_closed`` flag (suppresses ITS
        ``on_child_exit`` callback), never this CONNECTOR's separate
        ``_closed_event``, which is the ONE flag :meth:`events` actually
        checks on every ``queue.Empty``. A caller of :meth:`events` after a
        failed :meth:`start` (with no separate, explicit :meth:`close` call)
        was therefore never told to stop - the generator looped forever.
        FIX: the ``except`` clause now also sets ``self._closed_event``, and
        the guarded region was widened to cover ``transport.start()`` itself
        (not just the handshake request), catching ``BaseException`` rather
        than ``Exception`` - the same "every way this can fail must still
        leave events() terminable" widening pi.py's own note 10(c) applies.
        """
        transport = _CodexTransport(
            self._command,
            cwd=self._cwd,
            env=self._env,
            on_notification=self._on_notification,
            on_unmatched_response=self._on_unmatched_response,
            on_child_exit=self._on_child_exit,
            on_malformed_line=self._on_malformed_line,
            on_dispatch_error=self._on_dispatch_error,
            on_server_request=self._on_server_request,
        )
        try:
            transport.start()
            transport.request(
                _METHOD_INITIALIZE, {"clientInfo": _client_info()}, timeout_s=self._handshake_timeout_s
            )
        except BaseException:
            transport.close()  # reap the child; nothing else references it yet
            self._closed_event.set()
            raise
        # RES-A4 fix, second-order (mismatch note 14c): a PRIOR failed
        # start() may have set `_closed_event` above. Since this method only
        # re-runs when `self._transport is None` (start()'s own guard) -
        # i.e. exactly the "failed, never reached this line, retried" path,
        # never the "deliberately close()'d" one (`close()` never clears
        # `self._transport`, so a post-close() start() skips this method
        # entirely) - reaching here with a real, initialized transport means
        # this connector is live again and `_closed_event` must be cleared,
        # or `events()` on the now-healthy connector would see a stale
        # "closed" flag from the earlier failure and return immediately on
        # its very first idle poll.
        self._closed_event.clear()
        self._transport = transport

    # ------------------------------------------------------------------ #
    # Inbound translation (native codex event -> domain HarnessEvent)
    # ------------------------------------------------------------------ #
    @staticmethod
    def delivery_output(event):
        if event.native_event == "item/agentMessage/delta" and isinstance(event.payload.get("delta"), str):
            return event.payload["delta"], False
        return None

    @staticmethod
    def delivery_event_phase(event):
        if event.native_event == _METHOD_TURN_STARTED:
            return "started"
        if event.native_event == _METHOD_TURN_COMPLETED:
            return "terminal"
        return "progress" if event.turn_id is not None else None

    def _on_server_request(self, request_id, method, params):
        from ....domain.native_inputs import INPUT_METHODS, ELICITATION, validate_request
        if not self.native_approvals_enabled or method not in {
                "item/commandExecution/requestApproval", "item/fileChange/requestApproval", *INPUT_METHODS}:
            return False
        if (type(request_id) not in {str, int} or not isinstance(params, dict) or
                not all(isinstance(params.get(k), str) and params[k] for k in
                        (("threadId", "turnId") if method == ELICITATION else ("threadId", "turnId", "itemId")))):
            return False
        if method in INPUT_METHODS:
            try:
                validate_request(method, params)
            except (ValueError, TypeError, OverflowError, RecursionError):
                return False
        if "availableDecisions" in params and (
                not isinstance(params["availableDecisions"], list) or
                "accept" not in params["availableDecisions"] or "decline" not in params["availableDecisions"]):
            return False
        encoded = json.dumps([request_id, method, params], sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 16384:
            return False
        key = json.dumps(request_id)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self._sessions_lock:
            state = self._sessions_by_thread.get(params["threadId"])
            if not state or state.ended or state.closing or state.active_turn_id != params["turnId"]:
                return False
            previous = self._approval_requests.get(key)
            if previous:
                return previous["pending"] and previous["request"]["request_hash"] == digest
            if len(self._approval_requests) >= 256 or sum(r["pending"] for r in self._approval_requests.values()) >= 32:
                return False
            request = {"schema_version": 1, "request_id": request_id, "method": method,
                       "request_hash": digest, "params": params}
            self._approval_requests[key] = {"pending": True, "session_id": state.session_id, "request": request}
        self._push_event(state.session_id, method, {"native_approval": request},
                         thread_id=params["threadId"], turn_id=params["turnId"])
        return True

    def native_approval_request(self, event):
        request = event.payload.get("native_approval")
        if not isinstance(request, dict):
            return None
        with self._sessions_lock:
            recorded = self._approval_requests.get(json.dumps(request.get("request_id")))
            if (recorded and recorded["session_id"] == event.session_id and recorded["request"] == request and
                    event.native_event == request["method"] and event.thread_id == request["params"]["threadId"] and
                    event.turn_id == request["params"]["turnId"]):
                return request
        return None

    def reply_native_approval(self, session_id, request, decision):
        from ....domain.runtime_commands import RuntimeCommandNotSent
        from ....domain.native_inputs import INPUT_METHODS, ELICITATION, response_for
        if decision not in {"accept", "decline"}:
            raise RuntimeCommandNotSent("Unsupported native approval decision")
        with self._sessions_lock:
            recorded = self._approval_requests.get(json.dumps(request.get("request_id")))
            state = self._sessions_by_id.get(session_id)
            if (not recorded or not recorded["pending"] or recorded["session_id"] != session_id or
                    recorded["request"]["request_hash"] != request.get("request_hash") or
                    not state or state.ended or state.closing or
                    state.active_turn_id != recorded["request"]["params"]["turnId"]):
                raise RuntimeCommandNotSent("Native approval request ended or changed")
            wire = {"decision": decision}
            if request["method"] in INPUT_METHODS:
                if decision == "accept":
                    wire = request.get("operator_response")
                    if wire is None:
                        raise RuntimeCommandNotSent("Native input requires an explicit operator response")
                    try:
                        wire = response_for(recorded["request"],
                            {"content": wire.get("content")} if request["method"] == ELICITATION else wire, approved=True)
                    except (ValueError, TypeError, OverflowError, RecursionError):
                        raise RuntimeCommandNotSent("Operator response does not match the original native input") from None
                else:
                    wire = response_for(recorded["request"], None, approved=False)
            recorded["pending"] = False
        # An RPC id is never readmitted on this connection, even after a write
        # failure. A late reply therefore cannot target another native request.
        self._transport.reply_result(request["request_id"], wire)

    def _on_notification(self, method: str, params: dict[str, Any]) -> None:
        thread_id = _extract_thread_id(params)
        if thread_id is not None:
            if method == _METHOD_TURN_STARTED:
                turn_id = (params.get("turn") or {}).get("id")
                with self._sessions_lock:
                    state = self._sessions_by_thread.get(thread_id)
                    if state is not None and turn_id is not None:
                        state.active_turn_id = turn_id
                        state.pending_start_id = None
                        self._turn_changed.notify_all()
            if method == _METHOD_TURN_COMPLETED:
                turn_id = (params.get("turn") or {}).get("id")
                with self._turn_changed:
                    state = self._sessions_by_thread.get(thread_id)
                    # An old terminal must never settle a newer turn. Queue
                    # the native terminal before waking teardown to unsubscribe.
                    self._emit_for_thread(thread_id, method, params)
                    if state is not None and turn_id is not None and state.active_turn_id == turn_id:
                        state.active_turn_id = None
                        for request in self._approval_requests.values():
                            if request["session_id"] == state.session_id and request["request"]["params"]["turnId"] == turn_id:
                                request["pending"] = False
                        self._turn_changed.notify_all()
            else:
                self._emit_for_thread(thread_id, method, params)
            return

        # Connection-scoped: no threadId (nor a nested thread.id) to
        # attribute this to at all (error, account/*, skills/changed, ...).
        # Fan out to every LIVE session on this connector - see the
        # "connection-scoped events have no session to attribute to"
        # mismatch note. With zero live sessions the event has nowhere to
        # go and is dropped; that residual hole is documented, not hidden.
        with self._sessions_lock:
            live_session_ids = [s.session_id for s in self._sessions_by_id.values() if not s.ended]
        for session_id in live_session_ids:
            self._push_event(session_id, method, params, thread_id=None, turn_id=None)

    @staticmethod
    def _early_event_size(method: str, params: dict[str, Any]) -> int:
        return len(json.dumps([method, params], ensure_ascii=False).encode("utf-8"))

    def _emit_for_thread(self, thread_id: str, method: str, params: dict[str, Any]) -> None:
        with self._sessions_lock:
            state = self._sessions_by_thread.get(thread_id)
            if state is None:
                # thread/started (or any other early event) can race the
                # thread/start RESPONSE that teaches start() the threadId -
                # see the mismatch note. Hold it; start() replays on mapping.
                # The lookup AND this append happen under the SAME lock
                # acquisition as start()'s own register-then-pop sequence
                # (mismatch note 13) - previously the append was unlocked, so
                # a registration could land in the gap between the lookup
                # and the append and strand this event permanently.
                size = self._early_event_size(method, params)
                if (self._early_event_failed or self._early_event_count >= _EARLY_EVENT_LIMIT
                        or self._early_event_bytes + size > _EARLY_EVENT_BYTES):
                    self._early_event_failed = True
                    raise EarlyEventLimitExceeded("early_event_limit_exceeded")
                self._unmapped_thread_events.setdefault(thread_id, []).append((method, params))
                self._early_event_count += 1
                self._early_event_bytes += size
                return
            session_id = state.session_id
        turn_id = None
        if isinstance(params.get("turn"), dict):
            turn_id = params["turn"].get("id")
        elif isinstance(params.get("turnId"), str):
            turn_id = params["turnId"]
        self._push_event(session_id, method, params, thread_id=thread_id, turn_id=turn_id)

    def _push_event(
        self,
        session_id: str,
        native_method: str,
        payload: dict[str, Any],
        *,
        thread_id: str | None,
        turn_id: str | None,
    ) -> None:
        kind = _EVENT_KIND_BY_METHOD.get(native_method, _DEFAULT_EVENT_KIND)
        event = HarnessEvent(
            session_id=session_id,
            harness_kind="codex",
            kind=kind,
            native_event=native_method,
            occurred_at=utc_now_iso(),
            payload=payload,
            thread_id=thread_id,
            turn_id=turn_id,
        )
        # Append and nonblocking fanout share one ordering lock. Overflow
        # stops the owned process; every affected reader observes an explicit gap.
        with self._history_lock:
            retained = self._event_history.append(event)
            subscribers = [subscriber for subscriber in self._subscribers
                           if self._subscriber_sessions.get(subscriber) in (None, session_id)]
            overflow = not retained
            for subscriber_queue in subscribers:
                if subscriber_queue.put(event) is False:
                    overflow = True
        if overflow:
            stop_overflowed_process(self._transport._proc if self._transport else None)

    def _on_unmatched_response(self, request_id: Any, result: Any, error: dict[str, Any] | None) -> None:
        """A response to a fire-and-forget :meth:`send` call (D2: no
        correlated reply is ever awaited by the CALLER, but the transport
        still receives one and must not drop it - see the mismatch note
        "an unwaited response is not a discarded response"). A clean
        success is redundant with the native notification stream and is
        discarded; an ERROR has no other producer and becomes a
        ``HarnessEvent(kind="error")`` so a rejected ``turn/start`` is
        never silently swallowed.
        """
        with self._ff_pending_lock:
            pending = self._ff_pending.pop(request_id, None)
        if pending is None:
            return
        session_id, method = pending
        if error is None:
            return
        self._push_event(session_id, "jsonrpc/error_response", error, thread_id=None, turn_id=None)
        if method == _METHOD_TURN_START:
            with self._turn_changed:
                state = self._sessions_by_id.get(session_id)
                if state is not None and state.pending_start_id == request_id:
                    state.pending_start_id = None
                    self._turn_changed.notify_all()

    def _on_child_exit(self, returncode: int | None, stderr_tail: str) -> None:
        with self._sessions_lock:
            live_session_ids = [s.session_id for s in self._sessions_by_id.values() if not s.ended]
            for state in self._sessions_by_id.values():
                state.ended = True
            self._sessions_by_thread.clear()
        for session_id in live_session_ids:
            self._push_event(
                session_id,
                "process/exited",
                {"returncode": returncode, "stderr_tail": stderr_tail},
                thread_id=None,
                turn_id=None,
            )
        self._closed_event.set()

    def _on_malformed_line(self, line: str, error: str) -> None:
        with self._sessions_lock:
            live_session_ids = [s.session_id for s in self._sessions_by_id.values() if not s.ended]
        for session_id in live_session_ids:
            self._push_event(
                session_id,
                "transport/malformed_line",
                {"line": line, "error": error},
                thread_id=None,
                turn_id=None,
            )

    def _on_dispatch_error(self, line: str, error: str) -> None:
        """A structurally-valid JSON-RPC line whose SEMANTICS this
        connector could not process (e.g. an empty "method", or "params"
        shaped as a JSON array where dict-shaped params are assumed - both
        legal on the wire per JSON-RPC 2.0). Distinct from
        :meth:`_on_malformed_line` (which is JSON that failed to PARSE at
        all): this is JSON that parsed fine but broke this connector's own
        translation logic. See mismatch note 10 and
        :meth:`_CodexTransport._read_stdout`.
        """
        with self._sessions_lock:
            live_session_ids = [s.session_id for s in self._sessions_by_id.values() if not s.ended]
        for session_id in live_session_ids:
            self._push_event(
                session_id,
                "transport/dispatch_error",
                {"line": line, "error": error},
                thread_id=None,
                turn_id=None,
            )


# --------------------------------------------------------------------------- #
# Known protocol-to-port mismatches (reported, not smoothed over)
# --------------------------------------------------------------------------- #
# 1. ``multiplexes_sessions=True`` has no expression in ``HarnessConnector``.
#    The Protocol's ``start()`` returns ONE ``HarnessSession`` and there is
#    no "attach a new session to this already-running connector" method
#    distinct from ``start()``. This connector resolves it by making
#    ``start()`` idempotent-on-the-process (spawn+initialize once, lazily,
#    on the FIRST call) and non-idempotent-on-the-thread (every call issues
#    a fresh ``thread/start``) - an implicit contract the port's docstrings
#    do not state anywhere.
#
# 2. Connection-scoped events have no session to attribute to. ``error``,
#    ``account/*``, ``skills/changed``, ``deprecationNotice``,
#    ``configWarning``, ``app/list/updated`` (and friends) carry NO
#    ``threadId``, but ``HarnessEvent`` REQUIRES a ``session_id``. This
#    connector fans such an event out to every currently-live session on
#    the connector. The residual hole: with ZERO live sessions (e.g. a
#    connection-level auth error before any ``thread/start`` completes),
#    the event has nowhere to go and is dropped. There is no session-less
#    event sink in the port to hand it to instead.
#
# 3. ``EVENT_KINDS`` has 5 members against ~68 real codex notification
#    methods (``turn/diff/updated``, ``turn/plan/updated``,
#    ``thread/tokenUsage/updated``, ``item/started``, ``item/completed``,
#    every ``item/commandExecution/*``/``item/fileChange/*`` variant, ...).
#    All of these collapse into the ``tool_activity`` bucket; only
#    ``native_event`` preserves which one actually happened. A supervisor
#    that branches only on ``kind`` cannot tell a file-change diff from a
#    plan update from a rate-limit notice without also reading
#    ``native_event`` - this is real information loss the port's closed
#    vocabulary forces, not an oversight in this adapter.
#
# 4. ``COMMAND_VERBS`` includes ``end``; codex ``app-server`` has no
#    ``thread/end`` (or any single method that means it). The closest real
#    methods are ``thread/unsubscribe`` (stop receiving updates - reversible,
#    non-destructive), ``thread/archive`` and ``thread/delete``
#    (destructive). Because ONE connector multiplexes MANY sessions over
#    ONE child process, ending a single session must never tear down that
#    shared process - only ``close()`` (not part of the port; a connector
#    lifecycle method) does that, when the LAST session is done with it.
#    This connector interrupts an observed active turn, awaits its matching
#    terminal under a deadline, then sends ``thread/unsubscribe`` and marks the
#    session locally ended. A missing terminal leaves close_unconfirmed true.
#    It does not call ``thread/archive`` or
#    ``thread/delete``, since those destroy the codex-side rollout, which
#    ``end`` has no documented licence to do.
#
# 5. ``SESSION_STATUSES``' transition table has no ``STARTING -> ENDED``.
#    If the child process dies (or the connection drops) before a thread's
#    first ``turn/started`` ever arrives, the only legal terminal status
#    for that session is ``ERRORED`` - a clean, deliberate early
#    ``thread/unsubscribe``/shutdown on a session that never ran a turn has
#    no legal STARTING-origin path to ``ENDED`` in the table. This
#    connector does not attempt to paper over that; it is a gap for the
#    supervisor's transition logic to account for, not something fixable
#    at the adapter edge.
#
# 6. ``interrupt_requires_settle_wait=False`` for codex means the port
#    permits a supervisor to fire ``turn/start`` (or ``turn/steer``)
#    immediately after ``turn/interrupt`` with no wait. Whether codex's
#    real ``app-server`` accepts a same-millisecond follow-up request
#    against a thread whose interrupt has not yet settled was NOT exercised
#    by any live run behind this module (D6's own open questions list this
#    as unverified) - the declaration matches ADR 0004's instruction, not
#    an empirical proof of codex's tolerance for it.
#
# 7. An "unwaited" response is not a "discarded" response. D2's headline
#    claim - "send() returns no correlated reply for ANY transport" - is
#    about what the CALLER awaits, not about whether the wire ever sends
#    one back. Codex answers every request it receives, including the
#    fire-and-forget ones this connector issues for ``turn/start``,
#    ``turn/steer`` and ``turn/interrupt``. A late ERROR response to one of
#    those has no other producer in the protocol (no notification restates
#    "your turn/start was rejected"), so this connector still correlates
#    fire-and-forget request ids internally, purely to convert a late error
#    into a ``HarnessEvent(kind="error")`` instead of silently losing it -
#    a success response is discarded as redundant with the native
#    notification stream, but an error is never dropped on the floor.
#
# 8. The generated JSON Schema (``codex app-server generate-json-schema``)
#    is not a reliable guide to REQUEST shapes, only response/definition
#    shapes - proven, not assumed. ``ThreadStartParams.sandbox`` was read
#    off the schema as the tagged object ``{"type": "dangerFullAccess"}``
#    (that IS what a ``thread/start`` RESPONSE echoes back under
#    ``sandbox``). Sending that same object as the REQUEST value was
#    rejected live with ``-32600 Invalid request: unknown variant \`type\`,
#    expected one of \`read-only\`, \`workspace-write\`,
#    \`danger-full-access\``` - the request wants the bare dash-case
#    string. This connector sends the string (matching the ADR's own
#    ``-s danger-full-access`` spelling) and was re-verified end-to-end
#    against the LAN backend (D5) after the fix: ``initialize`` ->
#    ``thread/start`` -> ``turn/start`` -> the full
#    ``turn/started``/``item/*``/``item/agentMessage/delta``/
#    ``turn/completed`` notification sequence, with a real model reply.
#    A second, smaller instance of the same class of mismatch:
#    ``thread/started`` (unlike every other thread-scoped notification)
#    has NO top-level ``threadId`` - its thread id is nested at
#    ``params.thread.id``, confirmed in the same live capture. Both
#    corrections are load-bearing; a strict schema-only implementation
#    would have shipped broken on the very first ``thread/start`` call.
#
# 9. DEFECTS FOUND IN REVIEW, FIXED - recorded because a second connector in
#    this same codebase (``harness/pi.py``) independently shipped the exact
#    same shutdown-signalling bug, and because this file's own reader thread
#    had a second, worse defect stacked on top of it. Both concern
#    :meth:`CodexAppServerConnector.events`:
#
#    (a) The first version pushed a single ``_SHUTDOWN`` sentinel object
#        into ``_event_queue`` from ``close()``/``_on_child_exit`` and
#        looped on an UNBOUNDED ``_event_queue.get()``. A plain ``Queue``
#        sentinel is SINGLE-CONSUMPTION: only the ONE generator instance
#        whose ``get()`` happens to dequeue it ever sees it. A second call
#        to ``events()`` after shutdown (a fresh consumer, or the same
#        caller invoking it twice) would hang forever with no timeout and
#        no way out. FIX (mirrors ``harness/pi.py``'s own note 9): shutdown
#        is now a ``threading.Event`` (``_closed_event``), checked on every
#        ``queue.Empty`` from a ``Queue.get(timeout=_EVENTS_POLL_S)``
#        (currently 1.0s) instead of encoded as an item IN the queue at
#        all - EVERY caller, called ANY number of times, from ANY thread,
#        now observes shutdown within one poll period. Real events are
#        still delivered the instant they are pushed (D1's "no polling for
#        events" is preserved); only the IDLE-shutdown-detection path is
#        bounded-and-rechecked instead of unbounded.
#
#    (b) ``_CodexTransport._read_stdout``'s loop called ``self._dispatch(msg)``
#        with NO exception guard. A JSON-RPC-LEGAL but domain-invalid
#        notification (e.g. ``{"method": "", "params": {}}`` -
#        ``HarnessEvent.__post_init__`` rejects an empty ``native_event``;
#        or ``params`` as a JSON ARRAY, which JSON-RPC 2.0 explicitly
#        permits and which made ``_extract_thread_id``'s ``params.get()``
#        raise ``AttributeError``) made ``_dispatch`` raise. The exception
#        unwound into the ``finally`` block's ``self._proc.wait()``, called
#        with NO TIMEOUT while the child was still alive and healthy - the
#        reader thread blocked there forever, ``_on_child_exit`` was never
#        reached, no shutdown signal ever fired, and stdout stopped being
#        drained (a pipe-fill deadlock once the child's own stdout buffer
#        filled). FIX: ``_dispatch`` is now called inside its own
#        ``try/except``; a failure is surfaced as a
#        ``HarnessEvent(kind="error", native_event="transport/dispatch_error")``
#        (the callback itself is ALSO guarded, so a failure in reporting the
#        failure cannot re-wedge the loop) and the reader keeps draining
#        stdout. ``proc.wait()`` in the ``finally`` block is now bounded by
#        ``_PROC_WAIT_TIMEOUT_S`` regardless, per the standing rule below.
#
# 10. STANDING RULE, applied throughout this module after the review that
#     found 9(b): every blocking wait has an explicit timeout and raises (or
#     otherwise surfaces) a clear signal on expiry, rather than relying on
#     an assumption that the other side will always respond promptly. This
#     covers ``_CodexTransport._write``'s ``_write_lock`` acquisition
#     (previously a bare ``with``, unbounded if a concurrent write were
#     stuck on a full pipe - now ``acquire(timeout=_STDIN_WRITE_LOCK_TIMEOUT_S)``,
#     raising ``INTERNAL_ERROR`` on expiry) and the reader thread's own
#     ``proc.wait()`` noted in 9(b). ``request()`` and ``events()`` were
#     already bounded before this review; nothing there changed.
#
# 11. ``_end()`` used to POP the thread_id mapping from ``_sessions_by_thread``
#     synchronously, while the turn that was already in flight when ``end()``
#     was called kept emitting ``turn/started``/``item/*``/``turn/completed``
#     notifications for that SAME thread_id afterward. ``_emit_for_thread``
#     treated any unmapped thread_id identically to the "``thread/started``
#     raced ``thread/start``'s response" early-event case (mismatch note
#     above) and buffered it into ``_unmapped_thread_events`` - a dict only
#     ever drained by ``start()`` re-registering that EXACT thread_id, which
#     never happens again since thread ids are never reused. Ending a
#     session as soon as it is no longer needed (an ordinary sequence, e.g.
#     cancelling right as a turn finishes) silently and permanently dropped
#     that turn's own completion and leaked one dict entry per such session,
#     forever, for the life of the connector process. FIX: ``_end()`` no
#     longer pops the ``_sessions_by_thread`` mapping (only
#     ``state.ended = True``); trailing events for an ended thread now keep
#     resolving through the normal ``_emit_for_thread`` -> ``_push_event``
#     path instead of being mis-routed into the early-event buffer, so a
#     supervisor still observes the turn's real completion. This is a
#     deliberate DELIVER reading, not a DROP one: the trailing events are
#     real, already-in-flight observations the child produced before this
#     connector asked it to stop, and ``send()`` already rejects any FURTHER
#     command against ``state.ended``, so nothing can be issued against a
#     session that looks live but isn't.
#
# 12. ``_spawn_and_initialize`` used to set ``self._transport = transport``
#     BEFORE calling ``transport.request(_METHOD_INITIALIZE, ...)``. If that
#     request raised (a handshake timeout or a rejected ``initialize``), the
#     exception propagated out of ``start()``, but ``self._transport`` was
#     already non-``None``. ``start()``'s own spawn guard
#     (``if self._transport is None: self._spawn_and_initialize()``) then
#     skipped respawning entirely on every SUBSEQUENT ``start()`` call,
#     firing ``thread/start`` straight at a connection whose handshake never
#     completed - permanently wedging the connector after one bad handshake,
#     with no recovery short of constructing a brand-new instance. The
#     half-spawned child was also never reaped. A dead, write-only
#     ``self._initialized`` flag (grep-confirmed: set in two places, read
#     nowhere) sat next to this bug looking like it gated something; it did
#     not. FIX: ``self._transport`` is assigned only AFTER ``initialize``
#     succeeds; a failure closes (and thereby reaps) the half-spawned
#     transport before re-raising, so the NEXT ``start()`` call gets a clean
#     respawn. The dead ``self._initialized`` flag was removed rather than
#     wired up, since nothing in this connector needs it once the guard
#     above is correct.
#
# 13. ``_emit_for_thread``'s lookup of ``_sessions_by_thread.get(thread_id)``
#     was done under ``_sessions_lock``, but the subsequent append to
#     ``_unmapped_thread_events`` (for a genuinely-unmapped thread_id) ran
#     UNLOCKED, while ``start()`` registers the mapping AND pops
#     ``_unmapped_thread_events`` in the SAME lock acquisition. A
#     registration landing in the gap between the unlocked lookup and the
#     unlocked append could pop an as-yet-empty buffer, after which the
#     append lands - and that event is buffered forever, never replayed:
#     the exact race the buffer/replay mechanism exists to prevent. FIX:
#     the lookup and the (conditional) append now share ONE
#     ``_sessions_lock`` acquisition, matching ``start()``'s own scope, so
#     the two can no longer interleave.
#
# 14. TWO DEFECTS FOUND BY THE PHASE-4 CAMPAIGN'S DEFECT-WITNESS TESTS
#     (RES-A2, RES-A4), FIXED THIS PASS - both are the exact same defect
#     CLASS ``harness/pi.py`` independently shipped and fixed (its own notes
#     9(b)/C2 and 10(c)/C3), reintroduced here because this module was
#     written independently of that fix:
#
#     a) RES-A2 - ``events()`` fed every caller off ONE shared
#        ``queue.Queue`` (``_event_queue``, set in ``__init__``): two
#        concurrent consumers raced for the same items and the stream was
#        SPLIT between them (a deterministic partition, not a flaky race -
#        ``test_two_concurrent_events_consumers_split_the_stream_instead_of_
#        each_getting_the_full_stream`` proved it 3/3 by asserting the total
#        item count across both consumers of an N-event stream: 2N with
#        correct fan-out, exactly N with a shared-queue split). FIX: the
#        same fan-out shape as ``pi.py``'s C2 - ``_event_history`` (an
#        append-only record) plus one subscriber ``Queue`` per ``events()``
#        call, both under ``_history_lock`` so a push can never land in the
#        gap between a new subscriber's backlog snapshot and its
#        registration. ``_event_queue`` itself is gone; every push now goes
#        through ``_push_event``'s history-append-then-fan-out.
#
#        HONEST CAVEAT this fix carries, NOT present in ``pi.py``'s own
#        version of the same fix: ``pi.py`` justifies never trimming
#        ``_event_history`` by "a session's event count is bounded by its
#        own lifetime" - true there because ``multiplexes_sessions=False``
#        (one ``PiRpcConnector`` IS one session). That premise does NOT hold
#        here: ``multiplexes_sessions=True`` means ONE ``_event_history``
#        can in principle accumulate events across MANY sessions' worth of
#        turns over the connector's WHOLE process lifetime, not one
#        session's. At today's actual wiring this is not reachable
#        (``adapters/inbound/mcp/tools/harness.py``'s ``_codex`` factory
#        constructs a brand-new ``CodexAppServerConnector`` - and therefore
#        a brand-new child process - on every ``harness_open`` call, so no
#        connector instance in production currently outlives more than one
#        session; grep-confirmed, no other call site in ``src/`` re-uses a
#        connector across sessions or re-subscribes to ``events()``), but it
#        is a real, unbounded-growth latent gap the moment multiplexing is
#        ever actually wired up as ``multiplexes_sessions=True`` implies it
#        should be (see mismatch note 1) - reported here rather than
#        silently inheriting a justification whose premise is false for this
#        connector.
#
#     b) RES-A4 - ``_spawn_and_initialize``'s failure path called
#        ``transport.close()`` on a failed/timed-out handshake, but that
#        only sets the TRANSPORT's own private ``_closed`` flag (suppresses
#        ITS ``on_child_exit`` callback) - never this CONNECTOR's separate
#        ``_closed_event``, the ONE flag ``events()`` actually checks on
#        every ``queue.Empty``. A caller of ``events()`` after a failed
#        ``start()`` with no separate, explicit ``close()`` call was
#        therefore never told to stop - proved deterministically 3/3 by
#        ``test_failed_start_leaves_events_terminable`` (a child that
#        consumes the ``initialize`` write but never answers it, so the
#        handshake times out cleanly with no crash involved). FIX: the
#        ``except`` clause now also sets ``self._closed_event``, and the
#        guarded region was widened to cover ``transport.start()`` itself
#        (not just the handshake ``request()``), catching ``BaseException``
#        rather than ``Exception`` - matching how widely ``pi.py``'s own C3
#        fix guards its equivalent spawn path, so no way of failing to
#        start leaves this gap open again.
#
#     c) SECOND-ORDER DEFECT INTRODUCED BY (b) ABOVE, ALSO FIXED (found in
#        this same pass's own self-review, not by an earlier agent): setting
#        ``_closed_event`` on a failed start() and never clearing it anywhere
#        would silently poison every FUTURE successful retry on the SAME
#        connector instance - unlike ``pi.py`` (``multiplexes_sessions=
#        False``, a second ``start()`` call always raises outright), codex's
#        own mismatch note 12 explicitly promises "a subsequent ``start()``
#        call gets a clean respawn" after a failed one. Without a clear,
#        that respawn would succeed at the transport level while leaving
#        ``events()`` observing a stale "closed" flag from the EARLIER
#        failure and returning immediately on its very first idle poll -
#        proved deterministically by
#        ``test_events_stays_live_after_a_failed_start_is_followed_by_a_
#        successful_retry`` (one connector instance, one failed spawn via a
#        marker-file script that hangs on its first invocation, then a
#        successful retry via the SAME script's second invocation
#        behaving like a real minimal app-server). FIX:
#        ``_spawn_and_initialize``'s success path now clears
#        ``self._closed_event`` immediately before assigning
#        ``self._transport``. This can only fire on the failed-then-retried
#        path: this method only re-runs when ``self._transport is None``
#        (``start()``'s own guard), which a deliberate ``close()`` never
#        makes true again (``close()`` does not reset ``self._transport``),
#        so a post-``close()`` ``start()`` never reaches this line at all.
