"""Private bridge from copied synchronous adapters to the async Core port."""

from __future__ import annotations

from .adapter_types import RuntimeCommandRejected

import asyncio
import concurrent.futures
import json
import re
import sys
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from typing import Any, Protocol

from ..models import (CoreError, EffectNotSent, ExecutionContext, PreparedLaunch,
                      ProcessBirthEvidence, RuntimeEvent)
from ..harness_config import _token_env_name
from ..pi_extension_resource import PiNativeActionLaunch
from .adapter_types import (HarnessCommand, HarnessEvent, HarnessSession,
                            NativeAdapterError, RuntimeCommandNotSent)
from .adapters.compatibility import qualified_build, can_probe_protocol

#: Reserved capacity for containment/observation calls (C2/R02): physical
#: force, lifecycle observation and connector close never queue behind the
#: default-executor work used by normal sends and stream reads.
_CONTROL_POOL_SIZE = 4
#: C3/S05: physical force has its OWN reserved capacity, never consumable
#: by state observations or graceful closes - a blocked observation
#: backend cannot starve the emergency dispatch.
_FORCE_POOL_SIZE = 2

# Bound only the waiting startup thread, never cancel a possibly committed
# journal write. A timeout retains the conservative post-spawn outcome.
_PROCESS_BIRTH_RECORD_TIMEOUT = 10.0

from .event_ingest import translate_native_event
from .registry import adapter_spec, load_adapter, registered_managed_contract
from .redaction import NativeSecretRedactor, credential_values
from .process import snapshot_owned_process_birth


# C2/R09: CodexResumeGrant is the PUBLIC resume contract (models.py);
# the bridge imports the same class object so its exact-type validation
# accepts instances consumers build from the public export.
from ..models import CodexResumeGrant  # noqa: E402  (re-export identity)


class _CopiedConnector(Protocol):
    def start(self, *, owning_agent_id: str) -> HarnessSession: ...
    def send(self, session: HarnessSession, command: HarnessCommand) -> None: ...
    def events(self) -> Iterator[HarnessEvent]: ...
    def close(self) -> None: ...
    def force_stop(self) -> None: ...
    def observe_lifecycle(self, session: HarnessSession) -> Mapping[str, Any]: ...


def _next_event(iterator: Iterator[HarnessEvent]) -> HarnessEvent | None:
    try:
        return next(iterator)
    except StopIteration:
        return None


class EffectFence:
    """Thread-safe pre-dispatch guard shared with the native bridge (PC03).

    The runtime trips it whenever the in-memory admission fence closes
    (expiry/revocation/closing/fault). The copied-adapter bridge checks it
    on the loop AND inside the dispatch thread immediately before the
    native write/spawn - the closest point to the effect (RC-03-03: a
    thread that starts late must not write under stale authorization).
    Containment controls (interrupt/close) stay allowed past a lease
    deadline by contract; everything else fails closed before the write.

    C2/R03: the guard also consults the LIVE monotonic clock against the
    CURRENT lease deadline - never only a watcher flag, which is only as
    fresh as the watcher's last run. Linearization of the revoke/renew
    race: revoke publishes its flags before returning; renew replaces the
    binding context under the runtime lock. Reading the deadline first
    and the flags second is conservative under both orders - an
    extension racing this check can only delay an acceptance, never
    widen one, and an effect dispatched before a later revocation keeps
    its upstream OUTCOME_UNKNOWN handling (no exactly-once claim).
    """

    __slots__ = ("_probe", "_clock", "_lease_deadline", "_deadline_probe", "_productive_drain_probe")

    def __init__(self, probe=None, *, clock=None, lease_deadline=None,
                 deadline_probe=None, productive_drain_probe=None):
        self._probe = probe
        self._clock = clock
        self._lease_deadline = lease_deadline
        self._deadline_probe = deadline_probe
        self._productive_drain_probe = productive_drain_probe

    def check(self, action: str) -> None:
        if (action in {'send_turn', 'steer'} and self._productive_drain_probe is not None
                and self._productive_drain_probe()):
            raise RuntimeCommandNotSent('runtime is draining', code='RUNTIME_DRAINING')
        probe = self._probe
        if probe is not None:
            closed, closing, revoked, expired, faulted = probe()
            if closed:
                reason, code = "session closed before dispatch", "SESSION_CLOSED"
            elif revoked:
                reason, code = "authorization revoked before dispatch", "AGENT_REVOKED"
            elif faulted:
                reason, code = ("event stream unavailable before dispatch",
                                "EVENT_STREAM_UNAVAILABLE")
            elif closing and action not in {"interrupt", "end"}:
                reason, code = "session closing before dispatch", "SESSION_CLOSING"
            elif (expired and
                    action not in {"interrupt", "end"}):
                reason, code = "lease expired before dispatch", "AGENT_REVOKED"
            else:
                reason = None
            if reason is not None:
                raise RuntimeCommandNotSent(reason, code=code)
        # C2/R03: the real clock at the write frontier - a dispatch that
        # starts after the deadline must refuse even when the watcher flag
        # has not caught up yet.
        clock = self._clock
        if clock is not None and action not in {"interrupt", "end"}:
            deadline = (self._lease_deadline if self._deadline_probe is None
                        else self._deadline_probe())
            if deadline is not None and clock() >= deadline:
                raise RuntimeCommandNotSent(
                    "lease deadline reached before dispatch",
                    code="AGENT_REVOKED")


class CopiedAdapterSession:
    def __init__(self, connector: _CopiedConnector, session: HarnessSession,
                 *, session_id: str, stream_epoch: str,
                 context: ExecutionContext,
                 redactor: NativeSecretRedactor | None = None,
                 control_executor: concurrent.futures.Executor | None = None,
                 force_executor: concurrent.futures.Executor | None = None):
        self._connector = connector
        self._session = session
        self._session_id = session_id
        self._epoch = stream_epoch
        self._context = context
        self._redactor = redactor or NativeSecretRedactor()
        # C2/R02: containment/observation capacity is reserved and owned.
        # The factory owns one pool for its sessions; a directly constructed
        # session owns its own, disposed when it closes. Cancelling the await
        # never claims the underlying thread terminated.
        self._owns_control_executor = control_executor is None
        self._control_executor: concurrent.futures.Executor = (
            control_executor if control_executor is not None else
            concurrent.futures.ThreadPoolExecutor(
                max_workers=_CONTROL_POOL_SIZE,
                thread_name_prefix="nexus-core-control"))
        self._owns_force_executor = force_executor is None
        self._force_executor: concurrent.futures.Executor = (
            force_executor if force_executor is not None else
            concurrent.futures.ThreadPoolExecutor(
                max_workers=_FORCE_POOL_SIZE,
                thread_name_prefix="nexus-core-force"))
        # C3/S05: one in-flight observation per session - repeated polls
        # coalesce onto the shared unit instead of piling units on the
        # control pool while a backend hangs.
        self._observe_inflight: asyncio.Task | None = None
        self.native_id = session.session_id
        self._closed = False
        self._preset_bridge = None
        self._preset_config = None
        self._close_started = False
        self._end_attempted = False
        self._end_sent = False
        self._active_operation_id: str | None = None
        self._replacement_operations: deque[str] = deque()
        self._active_turn_id: str | None = None
        self._pi_started_for_active = False
        # Claude Code can emit frames on its own (background subagent output,
        # scheduled wakeup, task notification). Count the frames dropped here.
        self._unsolicited_frames = 0
        self._last_outcome: str | None = None
        self._last_failure_code: str | None = None
        self._recent_codex_turn_ids: deque[str] = deque()
        self._recent_codex_turn_set: set[str] = set()
        self.context_observation_contract = None

    async def observe_context(self, envelope: Mapping, guard) -> None:
        """Optional host-owned context storage, never a native send/turn."""
        method = getattr(self._connector, 'observe_context', None)
        if self.context_observation_contract != 1 or not callable(method):
            raise EffectNotSent('Context observation is not qualified', code='CAPABILITY_UNSUPPORTED')
        def checked():
            guard()
            if self._close_started:
                raise EffectNotSent('Session closed', code='SESSION_CLOSED')
            fence = getattr(self, 'effect_fence', None)
            if fence is not None:
                fence.check('observe_context')
        def write():
            checked()
            guards = getattr(self._connector, '_dispatch_guards', None)
            if guards is None:
                raise EffectNotSent('Context guard unavailable', code='CAPABILITY_UNSUPPORTED')
            guards.set(checked)
            try:
                method(self._session, envelope)
            except RuntimeCommandNotSent as error:
                raise EffectNotSent(str(error), code=error.code) from error
            finally:
                guards.clear()
        task = asyncio.create_task(asyncio.to_thread(write))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # Cancellation cannot release ownership of a still-running writer.
            await task
            raise

    def _remember_codex_turn(self, turn_id: str) -> None:
        if len(self._recent_codex_turn_ids) >= 256:
            self._recent_codex_turn_set.remove(
                self._recent_codex_turn_ids.popleft())
        self._recent_codex_turn_ids.append(turn_id)
        self._recent_codex_turn_set.add(turn_id)

    def owned_process_birth(self) -> ProcessBirthEvidence | None:
        """Historical birth token, only for a Core-owned child container."""
        process = getattr(self._connector, "_proc", None)
        if process is None:
            process = getattr(getattr(self._connector, "_transport", None), "_proc", None)
        if process is None:
            return None  # External attach has no Core-owned process.
        return snapshot_owned_process_birth(process)

    def active_turn(self) -> bool:
        """Whether a native turn was sent without a correlated terminal event."""
        return self._active_operation_id is not None

    async def send(self, verb: str, payload: Mapping[str, str],
                   operation_id: str, *,
                   expected_turn_id: str | None = None) -> None:
        if self._close_started:
            raise CoreError("SESSION_CLOSED", "native_send")
        if verb in {"interrupt", "steer"}:
            if self._active_operation_id is None:
                raise RuntimeCommandNotSent("no active turn to control",
                                            code="STALE_TURN")
            if (expected_turn_id is not None and
                    expected_turn_id != self._active_turn_id):
                raise RuntimeCommandNotSent("expected native turn is not active",
                                            code="STALE_TURN")
            if (verb == "steer" and
                    self._session.harness_kind == "pi" and
                    not self._pi_started_for_active):
                # Pi's wire carries no native turn ID, so the only honest
                # ID-less steer target is the agent run this bridge has
                # observed starting for the active submit. Refusing before
                # the write keeps it a durable safe failure, never a guess
                # that lands on a turn that never started.
                raise RuntimeCommandNotSent(
                    "no started pi agent run to steer", code="STALE_TURN")
        if verb == "send_turn":
            if self._active_operation_id is not None:
                raise CoreError("STALE_TURN", "native_send")
            # Set before calling the blocking native port: a terminal event
            # may arrive before the synchronous send returns.
            self._active_operation_id = operation_id
            self._active_turn_id = None
            self._pi_started_for_active = False
            self._last_outcome = None
            self._last_failure_code = None
        replacement = verb == "steer" and self._session.harness_kind == "claude_code"
        if replacement:
            # Claude emits results in submission order. Keep the old operation
            # active through its interrupted result, including when that result
            # arrives before the blocking replacement write returns.
            self._replacement_operations.append(operation_id)
        native_payload = dict(payload)
        if verb in {"send_turn", "steer"} and self._session.harness_kind == "claude_code":
            native_payload = {"content": native_payload["text"]}
        command = HarnessCommand(self._session.session_id, verb, native_payload,
                                 operation_id=operation_id,
                                 expected_turn_id=expected_turn_id)
        try:
            fence = getattr(self, "effect_fence", None)
            guards = getattr(self._connector, "_dispatch_guards", None)
            if fence is not None:
                # Loop-side check: fail fast, before paying for the thread
                # hop. Thread-side check happens at the closest point to
                # the native write/spawn (RC-03-03): the thread may start
                # late.
                fence.check(command.verb)

                def _guarded_dispatch() -> None:
                    fence.check(command.verb)
                    # C4/T03: install the thread-scoped transport guard so
                    # the refusal is re-consulted AFTER the adapter's own
                    # lock waits, at the zero-byte frontier.
                    if guards is not None:
                        guards.set(lambda: fence.check(command.verb))
                    try:
                        self._connector.send(self._session, command)
                    finally:
                        if guards is not None:
                            guards.clear()

                await asyncio.to_thread(_guarded_dispatch)
            else:
                await asyncio.to_thread(self._connector.send,
                                        self._session, command)
        except RuntimeCommandNotSent:
            if replacement:
                self._discard_replacement(operation_id)
            if verb == "send_turn":
                self._active_operation_id = None
                self._active_turn_id = None
                self._pi_started_for_active = False
            raise
        except RuntimeCommandRejected as exc:
            if replacement:
                self._discard_replacement(operation_id)
            if verb == "send_turn":
                self._active_operation_id = None
                self._active_turn_id = None
                self._pi_started_for_active = False
                self._last_outcome = None
                self._last_failure_code = None
            from ..models import EffectRejected
            raise EffectRejected(exc.message, failure_code=exc.failure_code) from exc
        except NativeAdapterError as exc:
            # Only the adapter's explicit pre-write evidence may become a
            # durable safe failure. A write/flush error remains uncertain.
            if exc.details.get("not_sent") is not True:
                raise
            if replacement:
                self._discard_replacement(operation_id)
            if verb == "send_turn":
                self._active_operation_id = None
                self._active_turn_id = None
                self._pi_started_for_active = False
            raise RuntimeCommandNotSent(exc.message, code=exc.code.value) from exc

    def _discard_replacement(self, operation_id: str) -> None:
        if operation_id in self._replacement_operations:
            self._replacement_operations.remove(operation_id)
        elif self._active_operation_id == operation_id:
            # The preceding result may already have advanced the FIFO while
            # the native adapter refused this replacement before its write.
            self._active_operation_id = None
            self._active_turn_id = None
            self._last_outcome = None
            self._last_failure_code = None

    async def reply_native_approval(
            self, request: Mapping[str, object], decision: str,
            operator_response: Mapping[str, object] | None) -> None:
        """Reply only to a still-active adapter-owned native request."""
        from .native_inputs import INPUT_METHODS

        method = request.get("method")
        params = request.get("params")
        if self._close_started or self._active_operation_id is None:
            raise RuntimeCommandNotSent("native approval turn is not active",
                                        code="STALE_TURN")
        if method in {"item/commandExecution/requestApproval",
                      "item/fileChange/requestApproval", *INPUT_METHODS}:
            if (self._session.harness_kind != "codex" or
                    not isinstance(params, dict) or
                    params.get("turnId") != self._active_turn_id):
                raise RuntimeCommandNotSent("native approval turn changed",
                                            code="STALE_TURN")
        elif method == "control_request:can_use_tool":
            if self._session.harness_kind != "claude_code":
                raise RuntimeCommandNotSent("native approval adapter changed",
                                            code="STALE_TURN")
        elif method == "extension_ui_request":
            if self._session.harness_kind != "pi":
                raise RuntimeCommandNotSent("native input adapter changed", code="STALE_TURN")
        else:
            raise RuntimeCommandNotSent("native approval method unsupported",
                                        code="CAPABILITY_UNSUPPORTED")
        reply = getattr(self._connector, "reply_native_approval", None)
        if not callable(reply):
            raise RuntimeCommandNotSent("native approval unavailable",
                                        code="CAPABILITY_UNSUPPORTED")
        projected = dict(request)
        if operator_response is not None:
            projected["operator_response"] = dict(operator_response)
        # C3/S03: a PERMISSIVE decision (accept/provide) grants work and
        # shares the same effect guard as every other write - checked on
        # the loop AND inside the dispatch thread at the write frontier,
        # including deadline, revocation, fault and closing flags. Deny-
        # style answers never grant anything, so refusing them past a
        # deadline would only make containment harder: they stay allowed
        # while the session is not closed.
        outcome = "decline" if decision == "cancel" else decision
        permissive = operator_response is not None or outcome not in {
            "decline", "deny", "denied", "reject", "refuse", "cancel"}
        fence = getattr(self, "effect_fence", None)
        guards = getattr(self._connector, "_dispatch_guards", None)
        originating_operation = self._active_operation_id

        def _correlation_still_valid() -> bool:
            if self._close_started or self._active_operation_id != originating_operation:
                return False
            if method == "extension_ui_request" and not self._connector.native_input_still_current(dict(request)):
                return False
            if method in {"item/commandExecution/requestApproval",
                          "item/fileChange/requestApproval", *INPUT_METHODS}:
                if (not isinstance(params, dict) or
                        params.get("turnId") != self._active_turn_id):
                    return False
            return True

        def _frontier_check() -> None:
            """C5/U01: the guard consulted by the TRANSPORT WRITER after
            its lock wait - deadline/revocation via the fence PLUS the
            request/turn correlation, so an answer authorized for turn 1
            can never reach the wire after turn 2 took over."""
            if permissive and fence is not None:
                fence.check("approval_reply")
            if not _correlation_still_valid():
                raise RuntimeCommandNotSent(
                    "native approval turn is not active", code="STALE_TURN")

        if permissive and fence is not None:
            fence.check("approval_reply")

        def _guarded_reply():
            if permissive and fence is not None:
                fence.check("approval_reply")
            if not _correlation_still_valid():
                raise RuntimeCommandNotSent(
                    "native approval turn is not active", code="STALE_TURN")
            # C5/U01: install the thread-scoped guard so the WRITER
            # re-validates after its own lock wait, immediately before
            # the first byte; removed in finally so nothing leaks to a
            # later operation on the same worker thread.
            if guards is not None:
                guards.set(_frontier_check)
            try:
                return reply(self._session.session_id, projected, outcome)
            finally:
                if guards is not None:
                    guards.clear()

        await asyncio.to_thread(_guarded_reply)

    async def events(self) -> AsyncIterator[RuntimeEvent]:
        from .codex_thread_configuration import EVENT_TYPE, METADATA_KEY, redact_observation

        metadata = getattr(self._session, 'metadata', {})
        configuration = metadata.get(METADATA_KEY) if isinstance(metadata, dict) else None
        if getattr(self._session, 'harness_kind', None) == 'codex' and isinstance(configuration, dict):
            # Core-originated lifecycle metadata, not a fabricated Codex
            # notification. It is session-scoped before any queue/discovery
            # consumption and redacted before the runtime journals the event.
            payload = redact_observation(configuration, self._redactor.clean)
            yield RuntimeEvent(self._context.server_id, self._context.executor_id,
                self._session_id, self._epoch, 0, 'lifecycle', EVENT_TYPE, payload)
        observe_configuration = getattr(self._connector, 'configuration_observation', None)
        if callable(observe_configuration):
            try:
                configuration = await asyncio.to_thread(observe_configuration)
                from ..protocol import canonical_json
                from hashlib import sha256
                configuration['candidate_ref'] = getattr(self._connector, '_configuration_candidate_ref', None)
                configuration.pop('schema_revision', None)
                configuration = self._redactor.clean(configuration)
                configuration['schema_revision'] = 'sha256:' + sha256(canonical_json(configuration)).hexdigest()
                # Leave room for event framing within the public event limit.
                if len(canonical_json(configuration)) > 48000:
                    raise CoreError('CAPACITY_EXCEEDED', 'configuration_discovery')
                payload = {'harness_configuration': configuration}
                category = 'lifecycle'
            except Exception:
                # Failure is visible but cannot stop an otherwise usable
                # session. Never publish transport text containing credentials.
                payload = {'configuration_discovery_error': 'NATIVE_DISCOVERY_FAILED'}
                category = 'system_warning'
            yield RuntimeEvent(self._context.server_id, self._context.executor_id,
                self._session_id, self._epoch, 0, category, 'core/harness_configuration', payload)
        if hasattr(self._connector, "events_for_session"):
            iterator = self._connector.events_for_session(self._session.session_id)
        else:
            iterator = self._connector.events()
        while True:
            native = await asyncio.to_thread(_next_event, iterator)
            if native is None:
                return
            phase_fn = getattr(self._connector, "delivery_event_phase", None)
            outcome_fn = getattr(self._connector, "delivery_outcome", None)
            phase = native.delivery_phase or (phase_fn(native) if phase_fn else None)
            outcome = native.delivery_outcome or (outcome_fn(native) if outcome_fn else None)
            # Claude Code can emit frames with no submitted turn. Drop them
            # instead of faulting a healthy session. A frame that names an
            # operation still goes through the strict checks below.
            if (native.harness_kind == "claude_code" and
                    self._active_operation_id is None and
                    native.operation_id is None and
                    (native.kind == "output_delta" or phase == "started" or
                     (phase == "terminal" and
                      (native.kind == "turn_completed" or
                       (native.kind == "error" and
                        native.native_event.startswith("result:") and
                        outcome == "failed"))))):
                self._unsolicited_frames += 1
                continue
            # Codex streams identify their native turn, not the Nexus operation.
            # Correlate every assistant delta before redaction withholds its tail.
            if native.harness_kind == "codex" and native.native_event == "item/agentMessage/delta":
                active = self._active_operation_id
                if (active is None or native.operation_id not in (None, active) or
                        not native.turn_id or native.turn_id != self._active_turn_id):
                    raise CoreError("EVENT_OPERATION_MISMATCH", "native_pump",
                                    possible_effect=True)
                native = replace(native, operation_id=active)
            # Claude and Pi process one submitted turn at a time. Text frames
            # carry no operation ID; bind them before redaction splits off
            # a terminal tail, otherwise the host drops the entire prefix.
            if native.harness_kind in {"claude_code", "pi"} and native.kind == "output_delta":
                active = self._active_operation_id
                if (active is None or native.operation_id not in (None, active) or
                        (native.harness_kind == "pi" and not self._pi_started_for_active)):
                    raise CoreError("EVENT_OPERATION_MISMATCH", "native_pump",
                                    possible_effect=True)
                native = replace(native, operation_id=active)
            if (native.harness_kind == "pi" and native.native_event == "agent_start" and
                    phase == "started" and self._active_operation_id is not None):
                self._pi_started_for_active = True
            if native.kind == "turn_started":
                if native.harness_kind == "codex" and (
                        self._active_operation_id is None or
                        type(native.turn_id) is not str or not native.turn_id or
                        native.turn_id in self._recent_codex_turn_set or
                        (self._active_turn_id is not None and
                         self._active_turn_id != native.turn_id)):
                    raise CoreError("EVENT_OPERATION_MISMATCH", "native_pump",
                                    possible_effect=True)
                if native.turn_id is not None:
                    self._active_turn_id = native.turn_id
            if phase == "started":
                active = self._active_operation_id
                if active is None or native.operation_id not in (None, active):
                    raise CoreError("EVENT_OPERATION_MISMATCH", "native_pump",
                                    possible_effect=True)
                native = replace(native, operation_id=active,
                                 delivery_phase=phase)
            from .failure_codes import provider_failure_code
            failure_code = provider_failure_code(native)
            if (failure_code and self._active_operation_id is not None
                    and native.operation_id in (None, self._active_operation_id)
                    and (native.harness_kind != "codex" or
                         (native.turn_id is not None and native.turn_id == self._active_turn_id))):
                self._last_failure_code = failure_code
            # Claude result errors are terminal facts, unlike transport errors.
            terminal_error = (native.harness_kind == "claude_code" and
                native.kind == "error" and native.native_event.startswith("result:")
                and outcome == "failed")
            terminal_code = None
            if phase == "terminal" and (native.kind == "turn_completed" or terminal_error):
                active = self._active_operation_id
                if (native.harness_kind == "pi" and native.native_event == "agent_settled" and
                        (active is None or not self._pi_started_for_active)):
                    raise CoreError("EVENT_OPERATION_MISMATCH", "native_pump",
                                    possible_effect=True)
                if native.harness_kind == "codex" and (
                        active is None or type(native.turn_id) is not str or
                        not native.turn_id or
                        native.turn_id != self._active_turn_id):
                    raise CoreError("EVENT_OPERATION_MISMATCH", "native_pump",
                                    possible_effect=True)
                if active is not None and native.operation_id not in (None, active):
                    raise CoreError("EVENT_OPERATION_MISMATCH", "native_pump",
                                    possible_effect=True)
                if outcome in {"success", "failed", "interrupted"}:
                    self._last_outcome = outcome
                settled_outcome = outcome or self._last_outcome
                if settled_outcome == "failed":
                    terminal_code = self._last_failure_code or "NATIVE_OPERATION_FAILED"
                native = replace(native, kind="turn_completed", operation_id=active,
                                 delivery_phase="terminal", delivery_outcome=settled_outcome)
                if native.harness_kind == "codex":
                    self._remember_codex_turn(native.turn_id)
                self._active_operation_id = (self._replacement_operations.popleft()
                    if native.harness_kind == "claude_code" and self._replacement_operations else None)
                self._active_turn_id = None
                self._pi_started_for_active = False
                self._last_outcome = None
                self._last_failure_code = None
            elif outcome in {"success", "failed", "interrupted"}:
                self._last_outcome = outcome
            # Only the adapter's correlated request port can supply an
            # operational proposal. Redacted event text is never its source.
            request_of = getattr(self._connector, "native_approval_request", None)
            operational = request_of(native) if callable(request_of) else None
            if operational is not None:
                from ..protocol import canonical_json, strict_json
                from ..decision_bridge_r4 import native_request_action
                encoded = canonical_json(operational)
                if len(encoded) > 16384 or self._active_operation_id is None:
                    raise CoreError("NATIVE_REQUEST_NOT_OBSERVED", "native_pump")
                operational = strict_json(encoded.decode("utf-8"))
                action = native_request_action(operational)
                native = replace(native, operation_id=self._active_operation_id)
            native = replace(native, native_approval=None,
                payload={key: value for key, value in native.payload.items()
                         if key not in ("native_approval", "delivery_error_code")})
            event = translate_native_event(self._redactor.scrub(native),
                                         server_id=self._context.server_id,
                                         executor_id=self._context.executor_id,
                                         session_id=self._session_id,
                                         stream_epoch=self._epoch,
                                         native_session_id=self._session.session_id)
            if terminal_code is not None:
                event = replace(event, payload={**event.payload, "delivery_error_code": terminal_code})
            if operational is not None:
                # This is the authenticated execution plane. Hosts must keep
                # the immutable proposal separate from UI/history display.
                display = self._redactor.clean(operational)
                display["request_hash"] = operational["request_hash"]
                event = replace(event,
                    category="input_request" if action == "input.provide" else "approval_request",
                    payload={**event.payload, "native_approval": operational,
                             "native_approval_display": display})
            yield event

    async def _run_control(self, fn, /, *args):
        """Run a containment/observation call on the reserved control pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._control_executor, fn, *args)

    async def _run_force(self, fn, /, *args):
        """Run the PHYSICAL force on its own reserved pool (C3/S05)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._force_executor, fn, *args)

    async def _lifecycle(self) -> Mapping[str, Any]:
        """Coalesced lifecycle observation: concurrent callers share one
        in-flight backend unit; a new poll starts only after the previous
        one returns. Cancellation of one waiter never cancels the shared
        unit."""
        task = self._observe_inflight
        if task is None or task.done():
            task = asyncio.create_task(
                self._run_control(self._connector.observe_lifecycle,
                                  self._session))
            self._observe_inflight = task

            def _clear(done: asyncio.Task) -> None:
                if self._observe_inflight is done:
                    self._observe_inflight = None
            task.add_done_callback(_clear)
        return await asyncio.shield(task)

    async def close(self) -> str:
        preset_error = None
        if self._preset_bridge is not None:
            try:
                await self._preset_bridge.close()
            except Exception as error:
                preset_error = error
        if self._closed:
            if preset_error is not None:
                raise preset_error
            return "already_closed"
        self._close_started = True
        if not self._end_attempted:
            self._end_attempted = True
            try:
                await asyncio.to_thread(self._connector.send, self._session,
                                        HarnessCommand(self._session.session_id, "end"))
                self._end_sent = True
            except Exception:
                pass
        try:
            before_close = await self._lifecycle()
        except Exception:
            before_close = {}
        reported = await self._run_control(self._connector.close)
        try:
            after_close = await self._lifecycle()
        except Exception:
            after_close = {}
        # C3/S08: the freshly observed result feeds the outcome (and any
        # downstream decision) immediately - never a stale prior flag.
        # Session-owned executors (direct construction, not the public
        # composition) are NOT disposed here: a confirmed stop can still be
        # followed by legitimate late observation/retries, and the public
        # lifecycle for factory-owned capacity is the runtime shutdown.
        self._closed = after_close.get("stop_observed") is True
        if self._closed and self._preset_config is not None:
            self._preset_config.close()
        if preset_error is not None:
            raise preset_error
        # Adapter classification is trusted only after independent tree-stop
        # observation. Older adapters without a report retain the conservative
        # pre-close observation rule.
        if self._closed and isinstance(reported, str) and reported in {"graceful", "forced"}:
            return reported
        return ("graceful" if self._closed and self._end_sent and
                before_close.get("stop_observed") is True else "unknown")

    async def force_stop(self) -> None:
        """Request owned-tree containment independently of a stuck send."""
        self._close_started = True
        try:
            await self._run_force(self._connector.force_stop)
        finally:
            if self._preset_bridge is not None:
                await self._preset_bridge.close()

    async def observe(self) -> tuple[str, str]:
        lifecycle = await self._lifecycle()
        state = "STOPPED" if lifecycle.get("stop_observed") is True else "RUNNING"
        if state == "STOPPED":
            self._closed = True
            self._close_started = True
            if self._preset_bridge is not None:
                await self._preset_bridge.close()
            if self._preset_config is not None:
                self._preset_config.close()
        return state, "UNKNOWN"


class CopiedAdapterFactory:
    """Guard installation integrity and negotiate native protocol at startup.

    Recorded build campaigns remain capability evidence. Other observed builds
    can attempt a live handshake without inheriting recorded control grants.
    """

    def __init__(self, environment: Callable[[PreparedLaunch],
                                             Awaitable[Mapping[str, str]]],
                 *, pi_native_action: Callable[[PreparedLaunch, str, ExecutionContext],
                                              Awaitable[PiNativeActionLaunch | None]] | None = None,
                 codex_client_info: Mapping[str, str] | None = None,
                 codex_resume: Callable[[PreparedLaunch, str, ExecutionContext],
                                        Awaitable[CodexResumeGrant | None]] | None = None,
                 native_approvals_enabled: bool = False,
                 native_approvals_from_lease: bool = False,
                 clock: Callable[[], float] | None = None):
        if type(native_approvals_enabled) is not bool:
            raise ValueError("native_approvals_enabled must be bool")
        if type(native_approvals_from_lease) is not bool:
            raise ValueError("native_approvals_from_lease must be bool")
        self._environment = environment
        self._pi_native_action = pi_native_action
        self._codex_client_info = (dict(codex_client_info)
                                   if codex_client_info is not None else None)
        self._codex_resume = codex_resume
        self._native_approvals_enabled = native_approvals_enabled
        self._native_approvals_from_lease = native_approvals_from_lease
        # C3/S01: the spawn gate ALWAYS has a clock - None never means
        # "protection off". The composition shares one effective source;
        # direct constructions fall back to the system monotonic clock.
        self._clock = clock if clock is not None else time.monotonic
        # C2/R02 + C3/S05: one reserved control pool for observations/close
        # and one DEDICATED force pool for every session this factory opens:
        # bounded, named and owned here; a blocked observation backend can
        # never consume the emergency force capacity. Normal data work stays
        # on the loop's default executor.
        self._control_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=_CONTROL_POOL_SIZE,
            thread_name_prefix="nexus-core-control")
        self._force_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=_FORCE_POOL_SIZE,
            thread_name_prefix="nexus-core-force")

    def close(self) -> None:
        """Release the factory-owned executors (best effort, non-blocking).

        In-flight containment calls are never cancelled mid-flight: threads
        already executing a physical force/observation run to completion.
        Queued-but-not-started calls are dropped; the runtime's own shutdown
        budget governs how long it waits for confirmation.
        """
        self._control_executor.shutdown(wait=False, cancel_futures=True)
        self._force_executor.shutdown(wait=False, cancel_futures=True)

    async def open(self, prepared: PreparedLaunch, session_id: str,
                   context: ExecutionContext, *, stream_epoch: str,
                   opening_guard=None,
                   process_birth_recorder: Callable[[ProcessBirthEvidence], Awaitable[None]] | None = None,
                   process_launch=None,
                   ) -> CopiedAdapterSession:
        resources = []
        try:
            return await self._open(prepared, session_id, context, stream_epoch=stream_epoch,
                                    opening_guard=opening_guard, resources=resources,
                                    process_birth_recorder=process_birth_recorder,
                                    process_launch=process_launch)
        except BaseException:
            for resource in resources:
                resource.close()
            raise

    async def _open(self, prepared: PreparedLaunch, session_id: str,
                    context: ExecutionContext, *, stream_epoch: str, opening_guard, resources,
                    process_birth_recorder=None, process_launch=None):
        spec = adapter_spec(prepared.intent.adapter_id)
        registered = registered_managed_contract(spec.adapter_id)
        if spec.mode != "managed":
            raise CoreError("CAPABILITY_UNSUPPORTED", "open", retry_safe=True)
        # PC11: refuse productive work before secrets/spawn when the host's
        # containment backend cannot honor its contract. Never a silent
        # fallback to bare kill(pid).
        from .process import require_containment
        require_containment()

        def _revalidate_launch(stage: str) -> None:
            """C2/R03 + C4/T04: the deadline is checked with the live clock
            after every await (journal-free memory read) and right before
            the spawn; an authorization valid at admission does not survive
            to the write frontier once the lease has expired under it. A
            runtime that began draining closes the opening guard - no
            pending open may start a native effect afterwards."""
            clock = self._clock
            probe = getattr(opening_guard, "context_probe", None)
            current_context = probe() if probe is not None else context
            if (clock is not None and
                    clock() >= current_context.lease_deadline_monotonic):
                raise CoreError("AGENT_REVOKED", stage, retry_safe=True)
            if opening_guard is not None and opening_guard.closed:
                raise CoreError("RUNTIME_DRAINING", stage, retry_safe=True)

        def _workspace_identity(stage: str) -> str:
            # A workspace is mutable: child creation/removal changes directory
            # size/mtime without changing the authorized directory itself.
            # Re-resolve the requested path too, so a redirected symlink or
            # junction cannot retain authorization for its old target.
            from pathlib import Path
            from ..profiles import _root_fingerprint
            try:
                root = Path(prepared.requested_root).resolve(strict=True)
                if root != Path(prepared.cwd) or not root.is_dir():
                    raise OSError('workspace target changed')
                identity = _root_fingerprint(root)
                if identity != prepared.root_fingerprint:
                    raise OSError('workspace identity changed')
                return identity
            except (OSError, ValueError, RuntimeError) as exc:
                raise CoreError('PROFILE_DRIFT', stage, retry_safe=True) from exc

        def _launch_signature(stage: str = 'open') -> tuple:
            """C4/T05 + C5/U05: stat seal over the REAL artifact set of
            this launch, taken before the callbacks and re-verified at
            every frontier. For single-binary adapters that is argv[0]+
            directory identity; for the Pi pair it is Node + CLI + the full declared
            dependency closure (stat-only walk with the identity's caps)
            - argv[0] is Node and proves nothing about the CLI or the
            dependencies. Residual same-stat window declared, not atomic."""
            import os
            workspace_identity = _workspace_identity(stage)
            launch_script = getattr(prepared.candidate, "launch_script",
                                    None)
            if (launch_script and
                    prepared.candidate.adapter_id == "pi_rpc"):
                from ..build_identity import launch_artifact_signature
                return (launch_artifact_signature(
                    prepared.argv[0], launch_script), workspace_identity)
            signature = [workspace_identity]
            for target in (prepared.argv[0],):
                try:
                    info = os.stat(target)
                    signature.append((info.st_size, info.st_mtime_ns))
                except OSError:
                    signature.append(None)
            return tuple(signature)

        def _revalidate_content(stage: str, snapshot: tuple) -> None:
            if _launch_signature(stage) != snapshot:
                raise CoreError("PROFILE_DRIFT", stage, retry_safe=True)

        async def _validate_frontier(stage: str) -> None:
            # Pi's seal walks its dependency closure. Never perform that I/O
            # on the event loop shared by existing sessions and their pumps.
            _revalidate_launch(stage)
            await asyncio.to_thread(_revalidate_content, stage, content_snapshot)
            _revalidate_launch(stage)  # authority can expire during the walk

        content_snapshot = await asyncio.to_thread(_launch_signature)
        kind = spec.native_kind
        candidate = prepared.candidate
        def is_qualified(observed):
            return qualified_build(kind, observed.version, sys.platform,
                observed.architecture, observed.fingerprint,
                build_identity=observed.build_identity)
        if registered is None and candidate.version is None and not is_qualified(candidate):
            # Passive discovery does not execute the installation. Observe
            # its version only at this admitted, selected launch boundary.
            # The probe filters the process environment and resolves no
            # provider credentials. Prepared identity remains unchanged.
            import os
            from ..discovery import _probe_selected_version
            def probe_guard():
                _revalidate_launch("version_probe")
                _revalidate_content("version_probe", content_snapshot)
            await _validate_frontier('version_probe')
            candidate = await asyncio.to_thread(_probe_selected_version,
                candidate, candidate.adapter_id, cwd=prepared.cwd,
                env=dict(os.environ), before_observe=probe_guard)
            await _validate_frontier('version_probe')
        recorded_build = is_qualified(candidate)
        # Build campaigns are evidence, not a cross-platform execution allowlist.
        # An observed native version may attempt the adapter's live handshake.
        # Unknown/malformed identities still fail before credentials are resolved.
        if registered is None and not recorded_build and not can_probe_protocol(
                candidate.version, candidate.architecture, candidate.fingerprint):
            raise CoreError("NATIVE_VERSION_UNQUALIFIED", "open", retry_safe=True)
        approval_actions = {"approval.decide", "input.provide"}.issubset(context.allowed_actions)
        if self._native_approvals_enabled and not approval_actions:
            raise CoreError("BINDING_NOT_AUTHORIZED", "native_approval_launch",
                            retry_safe=True)
        native_approvals_enabled = self._native_approvals_enabled or (
            self._native_approvals_from_lease and context.r4_authority is not None and approval_actions)
        from ..environment import ProcessHTTPEnvironment
        from ..harness_config import process_http_arguments
        environment = await self._environment(prepared)
        env = dict(environment)
        command = prepared.argv
        preset_bridge = environment.pi_mcp_bridge if isinstance(environment, ProcessHTTPEnvironment) else None
        preset_config = None
        if preset_bridge is not None:
            from importlib.resources import files
            command = (*command, '--extension', str(files('nexus_connector_core').joinpath('pi_extension', 'mcp.js')))
        if isinstance(environment, ProcessHTTPEnvironment) and prepared.intent.adapter_id != 'pi_rpc':
            templates = environment.http_templates
            mcp_arguments = process_http_arguments(
                prepared.intent.adapter_id, templates, prepared.secret_refs,
                inherit_global_mcps=prepared.intent.harness_settings.inherit_global_mcps == 'enabled',
                disabled_mcp_names=environment.disabled_mcp_names,
                preset_entries=environment.preset_entries, preset_strict=environment.preset_strict)
            if environment.preset_strict:
                from ..session_mcp_file import SessionMCPFile
                preset_config = SessionMCPFile()
                resources.append(preset_config)
                mcp_arguments = list(mcp_arguments)
                config_index = mcp_arguments.index('--mcp-config') + 1
                mcp_arguments[config_index] = await asyncio.to_thread(preset_config.create,
                    json.loads(mcp_arguments[config_index]))
            command = (*command, *mcp_arguments)
            if any(template.bearer_env_name not in env for template in templates):
                raise CoreError('PROVIDER_AUTH_REQUIRED', 'mcp_client_configuration')
        await _validate_frontier('environment')
        allowed_mcp_names = {_token_env_name(reference)
                             for reference in prepared.secret_refs
                             if isinstance(reference, str) and
                             reference.startswith("mcp-cap:")}
        for name, value in env.items():
            if name.startswith("NEXUS_MCP_TOKEN_"):
                if (name not in allowed_mcp_names or not isinstance(value, str) or
                        not value or "nxs_" in value or "nxsept_" in value):
                    raise CoreError("BINDING_NOT_AUTHORIZED", "environment",
                                    retry_safe=True)
            elif "NEXUS" in name.upper():
                raise CoreError("BINDING_NOT_AUTHORIZED", "environment",
                                retry_safe=True)
        native_action = None
        resume_grant = None
        if registered is not None:
            connector = load_adapter(spec.adapter_id)(command=command, cwd=prepared.cwd, env=env)
        elif kind == "codex":
            resume_grant = (await self._codex_resume(prepared, session_id, context)
                            if self._codex_resume is not None else None)
            await _validate_frontier('codex_resume')
            if resume_grant is not None and (
                    type(resume_grant) is not CodexResumeGrant or
                    not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,255}",
                                     resume_grant.thread_id) or
                    resume_grant.session_id != session_id or
                    resume_grant.server_id != context.server_id or
                    resume_grant.executor_id != context.executor_id or
                    resume_grant.binding_id != context.binding_id or
                    resume_grant.agent_id != context.agent_id or
                    resume_grant.workspace_id != context.workspace_id or
                    resume_grant.session_owner_generation != context.session_owner_generation or
                    resume_grant.candidate_fingerprint != prepared.candidate.fingerprint or
                    resume_grant.root_fingerprint != prepared.root_fingerprint or
                    resume_grant.profile_fingerprint != prepared.profile_fingerprint or
                    resume_grant.terminal_observed is not True or
                    resume_grant.persisted_rollout_observed is not True or
                    resume_grant.exclusive_owner is not True):
                raise CoreError("BINDING_NOT_AUTHORIZED", "codex_resume",
                                retry_safe=True)
            client_kwargs = (dict(self._codex_client_info)
                             if self._codex_client_info is not None else {})
            # PC08 (F07): the explicit model reaches the verified native
            # mechanism - thread/start (and thread/resume) accept a nullable
            # ``model`` string in the qualified 0.157.0 contract - instead of
            # disappearing after the profile digest.
            explicit_model = prepared.intent.model
            from ..harness_configuration import codex_thread_settings
            overrides = dict(client_kwargs.get('thread_start_overrides', {}))
            overrides.update(codex_thread_settings(prepared.intent.harness_settings))
            if explicit_model is not None:
                overrides['model'] = explicit_model
            if overrides:
                client_kwargs['thread_start_overrides'] = overrides
            connector = load_adapter(spec.adapter_id)(command=command,
                                                      cwd=prepared.cwd, env=env,
                                                      **client_kwargs)
        elif kind == "pi":
            native_action = (await self._pi_native_action(prepared, session_id, context)
                             if self._pi_native_action is not None else None)
            await _validate_frontier('native_action')
            if native_action is not None and (
                    not isinstance(native_action, PiNativeActionLaunch) or
                    native_action.session_id != session_id or
                    native_action.capability_ref not in prepared.secret_refs):
                raise CoreError("BINDING_NOT_AUTHORIZED", "native_action_launch")
            connector = load_adapter(spec.adapter_id)(command=command,
                                                      cwd=prepared.cwd, env=env,
                                                      native_action=native_action)
        else:
            connector = load_adapter(spec.adapter_id)(binary=command[0],
                                                      argv=command[1:],
                                                      cwd=prepared.cwd, env=env)
        if native_approvals_enabled and kind in {"codex", "claude_code", "pi"}:
            connector.native_approvals_enabled = True
        secrets = (*credential_values(env),
                   *((native_action.capability_ref,) if native_action is not None else ()))
        redactor = NativeSecretRedactor(secrets)
        await _validate_frontier('launch')
        # C5/U02: the guard travels WITH the connector so the native
        # creator itself re-validates after its OWN internal waits (start
        # locks, bootstrap steps) - the last memory-only checkpoint
        # before the spawn primitive. The content seal stays at the
        # queue/thread frontiers; this callable is tiny and I/O-free.
        if hasattr(connector, "_launch_guard") or True:
            connector._launch_guard = _revalidate_launch
        if process_launch is not None:
            identity = process_launch.identity
            if (identity.key.server_id, identity.key.executor_id, identity.key.session_id) != (
                    context.server_id, context.executor_id, session_id):
                raise CoreError('PROCESS_LAUNCH_CONFLICT', 'launch', retry_safe=True)
            connector._process_container_id = identity.container_id
        if process_birth_recorder is not None:
            loop = asyncio.get_running_loop()

            def _record_birth(evidence: ProcessBirthEvidence) -> None:
                # Runs in this opening's worker, not on the event loop. The
                # adapter retains its process handle before invoking us and
                # performs no handshake until the journal commit completes.
                async def _persist():
                    await process_birth_recorder(evidence)

                pending = _persist()
                try:
                    recorded = asyncio.run_coroutine_threadsafe(pending, loop)
                except BaseException:
                    pending.close()
                    raise
                recorded.result(timeout=_PROCESS_BIRTH_RECORD_TIMEOUT)
                # Recording may have waited for storage while the lease was
                # revoked or the runtime drained. Do not start protocol I/O
                # under that stale authority after the wait.
                _revalidate_launch("process_birth")

            connector._process_birth_observer = _record_birth
        try:
            if preset_bridge is not None:
                env.update(await preset_bridge.start())
                redactor = NativeSecretRedactor((*secrets, env['OKTO_PRESET_MCP_TOKEN']))
            start_kwargs = {"owning_agent_id": context.agent_id}
            if resume_grant is not None:
                start_kwargs["resume_thread_id"] = resume_grant.thread_id

            def _guarded_start():
                # C3/S02: the revalidation runs INSIDE the work unit that
                # starts the process, when the worker finally begins and
                # after every queue wait - not only before enqueueing. A
                # refusal here is provably pre-spawn: retry_safe stays
                # honest because nothing was started.
                _revalidate_launch("launch")
                _revalidate_content("launch", content_snapshot)
                return connector.start(**start_kwargs)

            if process_launch is None:
                native_session = await asyncio.to_thread(_guarded_start)
            else:
                native_session = await process_launch.produce(
                    validate_authority=lambda: _revalidate_launch('launch'), start=_guarded_start)
            if registered is not None:
                # Registration alone is not observed support. This handshake
                # belongs to the loaded connector and cannot be supplied over
                # the network or inferred from another runtime's version.
                observed = await asyncio.to_thread(connector.verify_protocol)
                if (type(observed) is not dict or type(observed.get('managed_contract')) is not int
                        or observed['managed_contract'] != 1
                        or type(observed.get('transport_binding_contract')) is not type(registered.transport_binding_contract)
                        or observed.get('transport_binding_contract') != registered.transport_binding_contract
                        or native_session.harness_kind != spec.native_kind
                        or native_session.owning_agent_id != context.agent_id):
                    from .adapter_types import ErrorCode
                    raise NativeAdapterError(ErrorCode.CONFLICT,
                        'The registered adapter did not confirm its managed contract.',
                        {'reason': 'protocol_incompatible'})
            if kind == 'claude_code' and not recorded_build:
                await asyncio.to_thread(connector.verify_protocol)
        except BaseException as error:
            if preset_bridge is not None:
                await preset_bridge.close()
            stopped = await asyncio.to_thread(connector.close)
            if isinstance(error, NativeAdapterError) and stopped in ('graceful', 'forced', 'already_closed'):
                from ..models import EffectRejected
                raise EffectRejected('Native startup failed and its process was stopped.',
                    failure_code=('NATIVE_PROTOCOL_INCOMPATIBLE'
                        if error.details.get('reason') == 'protocol_incompatible'
                        else 'NATIVE_STARTUP_FAILED')) from error
            raise
        connector._configuration_candidate_ref = prepared.candidate.installation_ref
        if kind == 'claude_code':
            from ..configuration_probe import probe_selected_configuration
            def observe_configuration():
                _revalidate_launch('configuration_discovery')
                value = probe_selected_configuration(candidate, cwd=prepared.cwd, env=env,
                    native_approvals_enabled=bool(native_approvals_enabled))
                _revalidate_launch('configuration_discovery')
                return value
            connector.configuration_observation = observe_configuration
        result = CopiedAdapterSession(connector, native_session,
                                    session_id=session_id,
                                    stream_epoch=stream_epoch, context=context,
                                    redactor=redactor,
                                    control_executor=self._control_executor,
                                    force_executor=self._force_executor)
        result._preset_bridge = preset_bridge
        result._preset_config = preset_config
        if (registered is not None and type(registered.context_observation_contract) is int
                and registered.context_observation_contract == 1
                and type(observed.get('context_observation_contract')) is int
                and observed['context_observation_contract'] == 1
                and callable(getattr(connector, 'observe_context', None))
                and getattr(connector, '_dispatch_guards', None) is not None):
            result.context_observation_contract = 1
        return result
