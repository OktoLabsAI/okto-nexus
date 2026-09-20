"""The harness supervisor - Phase 3.5 of the harness-integrations feature.

Owns everything ADR 0004 D1 assigns to "the supervisor": a registry of live
:class:`~okto_nexus.domain.harness.HarnessSession` objects keyed by session
id, one :class:`~okto_nexus.application.ports.HarnessConnector` instance per
live session, the in-memory
:class:`~okto_nexus.application.ports.HarnessSubscriberRegistry` fan-out, and
lifecycle (open / send / close / reaping on child death).

This module is a CONCRETE application service, not a ``Protocol`` in
``ports.py`` - it follows the same shape as every other orchestration class
in this package (:class:`~okto_nexus.application.messages.MessageService`,
:class:`~okto_nexus.application.identity.IdentityService`,
:class:`~okto_nexus.application.approvals.ApprovalService`): inbound adapters
(the MCP tools / HTTP routes a later phase adds) import
:class:`HarnessSupervisor` directly and call its public methods, exactly as
``tools/messages.py`` imports ``MessageService`` directly today. Its public
methods (:meth:`open`, :meth:`open_declared`, :meth:`send`, :meth:`close`,
:meth:`get`, :meth:`list_live`, :meth:`replay_events`) ARE the surface a
future tool/route layer wraps - "whatever the supervisor itself must expose
to the inbound adapters" from the Phase 3.5 spec is exactly this method set.

Consumes the FROZEN :class:`~okto_nexus.application.ports.HarnessConnector`
and :class:`~okto_nexus.application.ports.HarnessSubscriberRegistry` ports
without modifying either. Depends only on ports + domain + the sibling
:class:`~okto_nexus.application.messages.MessageService` (an in-layer
import, like every other cross-slice dependency in ``application/``) - no
``sqlite3``, no ``mcp`` (enforced by ``tests/test_import_boundary.py``).

Design notes on the two genuinely hard parts, spelled out here because they
are the ones a reviewer will want justified rather than assumed:

* **Bounded waits without ``SleepPollWaiter`` (D1/D8).** The one place this
  module must wait for something that might never happen is
  :meth:`open`, where a connector's :meth:`~HarnessConnector.start` can wedge
  (Phase 3's "looks alive, delivers nothing" failure class applies to
  startup too - see :func:`_bounded_start`). That bound is a plain
  ``threading.Thread.join(timeout)`` - a stdlib blocking wait on a condition
  variable, not a re-checking sleep loop - so ``SleepPollWaiter`` never
  enters the harness path and D1's push-not-poll contract holds
  structurally.
* **Two shapes of ``events()`` (D2's "one uniform port, real transports
  still differ").** Pi/Codex/Claude-Code-stream-json's ``events()`` are
  BLOCKING generators fed by the connector's own reader thread(s); this
  module pumps each with ONE dedicated daemon thread per session
  (:meth:`_pump`), which is what makes D1's push happen at all. The
  ``cc-socks`` attach connector's ``events()`` is instead documented as a
  FINITE snapshot iterator that "never blocks, never polls" (see its own
  docstring) - looping that in a background thread would either busy-spin
  or exit immediately after draining whatever was queued at ``open()`` time,
  silently losing every later error. :attr:`HarnessCapabilities.send_only`
  is the exact, already-declared signal for this shape difference (the
  domain module's own docstring says as much), so :meth:`open` skips the
  background pump for a ``send_only`` connector and :meth:`send` drains its
  finite ``events()`` synchronously right after every send instead - the one
  place that connector shape can ever produce an event.

Harness-to-harness relaying, and its loop protection (limitation 2 closed
here). :meth:`_on_inbox_delivery` forwards an ordinary target-grammar
message into a live harness's connector - including a message sent BY
another currently-live harness's own agent, e.g. via its ``notify_target``
at :meth:`open` time. That is a deliberate relay (an operator/agent set
``notify_target`` on session A to session B's own agent id - the API
already treats that as an instruction to relay, D10), not an accident, and
it must work. What must NOT work is the degenerate case: A and B (or a
longer chain back to A) notify-targeting each other so that every
``turn_completed`` re-triggers the next, forever.

* **What distinguishes a legitimate relay from a runaway cascade: DEPTH.**
  A cycle-check over the live session graph was considered and rejected -
  it would forbid a deliberate, ACYCLIC A->B->C hand-off chain (three
  DIFFERENT harnesses relaying in sequence, never revisiting a prior node)
  for no real safety reason, and it requires maintaining a graph rather
  than one integer. A bounded hop counter (:data:`DEFAULT_MAX_RELAY_DEPTH`,
  overridable via the ``max_relay_depth`` constructor kwarg) provably
  terminates in at most that many hops regardless of the chain's shape -
  that termination guarantee is the actual property needed, so it is what
  is built. A rate limit (N forwards per second) was also considered and
  rejected: it bounds throughput, not chain length, so a slow cascade
  (seconds between hops, well within any sane rate) would sail through it
  indefinitely while a legitimate BURST of several independent, unrelated
  relay hops in the same second would be throttled for no reason.
* **Where the depth lives: supervisor-side, on the supervisor's OWN
  ``_LiveSession`` bookkeeping - not on any frozen type.**
  :class:`~okto_nexus.domain.harness.HarnessEvent` and
  :class:`~okto_nexus.domain.harness.HarnessSession` are frozen (this
  feature's own absolute rule); riding the depth on the message body that
  :meth:`_deliver_notable_message` composes was considered, since that
  body is this module's own JSON and not frozen - but it only threads
  depth through the ONE call shape that originates a relay (a D10 auto
  notable-message), not through a harness explicitly authoring an ordinary
  message via ``message_create`` to hand work to another harness, which
  carries free-text the supervisor does not compose and cannot annotate.
  Attributing depth to the SOURCE SESSION itself (:attr:`_LiveSession.
  relay_depth` / ``relay_depth_updated_at``), read off ``from_agent_id`` ->
  its live session at forward time, covers both call shapes uniformly with
  no change to ``MessageService`` (owned by a sibling agent this session;
  ABSOLUTE RULE 3) and no new port. The depth is recorded on the TARGET
  session's own bookkeeping inside :meth:`send` itself - the ONE place
  anything ever writes :attr:`_LiveSession.relay_depth` - so a session
  reached through the ORDINARY, non-relay path (a direct :meth:`send` call
  from an MCP/HTTP tool) resets its bookkeeping to 0 rather than silently
  inheriting a stale depth from an unrelated relay chain that happened
  earlier in that same session's life. ``relay_depth_ttl_s`` bounds how
  long a source session's depth stays "live" for this purpose, so a slow,
  legitimate, sporadic relay pattern (hops minutes apart) never
  accumulates depth across unrelated conversations the way a fast runaway
  cascade would.
* **The failure mode when the cap IS hit: LOUD, never a silent drop.**
  This project's own recurring failure signature (EV-REV-003, SYS-10,
  RES-claude-code-attach.md) is a conclusion presented as safe when it was
  never actually observed to be. A refused relay publishes AND persists a
  synthetic ``kind="error"`` :class:`~okto_nexus.domain.harness.HarnessEvent`
  (:meth:`_report_relay_cascade_blocked`) attributed to the session whose
  forward was refused, live (subscribers) AND durable (replay), plus a
  stderr breadcrumb - never merely a ``return`` with nothing to observe.
  This deliberately BYPASSES :meth:`_handle_event` /
  :meth:`_deliver_notable_message`: routing the block event through the
  normal notable-message path would create ANOTHER message from that
  session's own agent, which would re-enter this SAME relay path on its
  next delivery - the loop guard manufacturing a loop of its own.
"""

from __future__ import annotations

import functools
import json
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ..domain.base import new_id
from ..domain.harness import (
    STATUS_ENDED,
    STATUS_ERRORED,
    STATUS_RUNNING,
    HarnessCapabilities,
    HarnessCommand,
    HarnessEvent,
    HarnessSession,
    can_transition_session,
    validate_harness_kind,
)
from ..errors import ErrorCode, OktoNexusError
from .messages import MessageService
from .ports import (
    AgentRepo,
    Clock,
    ConnectionFactory,
    HarnessConnector,
    HarnessEventRepo,
    HarnessSessionRepo,
    HarnessSubscriberRegistry,
    InboxDeliveryNotifier,
)

#: The normalised event kinds this supervisor treats as worth a message, on
#: top of the durable event row every kind already gets (D10). Turn
#: completion is the ADR's own headline example ("above all"); ``error`` is
#: added here (and justified, per the spec's instruction to justify any
#: addition) because an unsurfaced harness failure is exactly the "looks
#: alive, delivers nothing" failure class Phase 3 was built to defend
#: against - an operator/agent watching only their inbox must still learn a
#: harness broke, not just that it silently stopped producing turns.
NOTABLE_EVENT_KINDS: frozenset[str] = frozenset({"turn_completed", "error"})

#: Command verbs a ``send_only`` connector (D7b, cc-socks) can honour. Read
#: off :attr:`HarnessCapabilities.send_only`, never hardcoded per harness
#: kind (domain/harness.py's own docstring is explicit that this is a
#: capability-driven check, not a per-verb special case).
_SEND_ONLY_ALLOWED_VERBS: frozenset[str] = frozenset({"send_turn"})

#: Default bounds for supervisor-side waits (D8: "every supervisor-side wait
#: is bounded and raises a clear error on expiry"). Generous enough to cover
#: a real child-process handshake (the pi connector's own handshake timeout
#: defaults to 30s) without being so long that a wedged boot-time harness
#: meaningfully delays ``serve`` noticing and moving on to the next one.
DEFAULT_START_TIMEOUT_SECONDS = 30.0
DEFAULT_CLOSE_TIMEOUT_SECONDS = 10.0
#: Harness-to-harness relay loop protection (limitation 2; see the module
#: docstring's "Harness-to-harness relaying" section for the full design
#: rationale). A relay chain longer than this many hops is refused, loudly
#: (:meth:`HarnessSupervisor._report_relay_cascade_blocked`), rather than
#: run forever. 4 is generous enough for a deliberate multi-harness
#: hand-off (A->B->C->D) while catching a 2-party ping-pong (A<->B) within
#: two round trips.
DEFAULT_MAX_RELAY_DEPTH = 4
#: How long a source session's recorded relay depth stays "live" for the
#: NEXT forward's depth computation before being treated as 0 (a fresh,
#: unrelated chain) again. Generous relative to how fast a REAL cascade
#: reproduces (sub-second to low-single-digit-second hops in every
#: connector this project ships) so it never masks one, while still being
#: short enough that two harnesses relaying sporadically, minutes apart,
#: are never throttled by history that has nothing to do with their
#: current exchange.
DEFAULT_RELAY_DEPTH_TTL_SECONDS = 30.0
#: Bound for one forwarded inbox delivery (SYS-03/UAT-05 follow-up): a
#: connector's own ``send`` can genuinely block on a transport write/ack
#: (e.g. pi's ``_send_turn`` awaits a reply up to its own command timeout),
#: and this forward runs on the CALLING thread of whatever fired
#: ``message_create`` (an MCP tool call, an HTTP request) - it must never
#: wedge that caller past a bound, per D8's "every wait bounded".
DEFAULT_FORWARD_TIMEOUT_SECONDS = 10.0


@dataclass(slots=True)
class _LiveSession:
    """The supervisor's in-memory bookkeeping for ONE live session (D1).

    This - not :class:`HarnessSessionRepo` - is the supervisor's actual
    source of truth for "is this session live right now". ``session`` is the
    SAME mutable object a connector's ``start()`` returned; the supervisor
    mutates its ``status``/``ended_at`` in place as the session's lifecycle
    advances, exactly like every other slice's domain object is mutated
    in-memory before (or instead of, on a non-observing connector) being
    persisted.
    """

    connector: HarnessConnector
    session: HarnessSession
    project_root: str
    notify_target: Any = None
    pump_thread: "threading.Thread | None" = None
    #: send_only cursor (RES-A2 follow-up): a send_only connector's
    #: ``events()`` is now a BROADCAST snapshot of an append-only history
    #: (see ``ClaudeCodeAttachConnector.events()``), not a destructive
    #: drain - the port never promised destructive-drain semantics (see
    #: ``HarnessConnector.events()``'s docstring, which only promises "an
    #: iterable/iterator of normalised inbound events"). This tracks how
    #: many of THIS session's send_only events have already been handled so
    #: :meth:`HarnessSupervisor.send` can replay only the tail on each call,
    #: keeping the "handle every event exactly once" invariant entirely on
    #: the caller side without needing the connector to change behaviour.
    send_only_events_handled: int = 0
    #: Handle returned by InboxDeliveryNotifier.subscribe for this session's
    #: owning_agent_id (SYS-03/UAT-05 follow-up); None when no notifier is
    #: wired. Unsubscribed in _claim_for_reap - the same single place
    #: anything leaves the live registry.
    inbox_subscription: Any = None
    #: Harness-to-harness relay depth bookkeeping (limitation 2 fix - see
    #: the module docstring's "Harness-to-harness relaying" section). The
    #: depth this session's CURRENT activity was forwarded in at, 0 meaning
    #: "not currently mid-relay-chain" (a fresh open, or the last thing
    #: this session did was a direct, non-relay send()). Written ONLY by
    #: HarnessSupervisor.send (its `_relay_depth` kwarg) - never by the
    #: forwarding callback directly - so a direct send() through the
    #: ordinary MCP/HTTP path always resets it, rather than silently
    #: inheriting a stale value from an unrelated earlier relay chain.
    relay_depth: int = 0
    #: `time.monotonic()` timestamp of the last relay_depth write; paired
    #: with `HarnessSupervisor._relay_depth_ttl_s` so a depth this old is
    #: treated as expired (0) rather than extending an unrelated later
    #: chain. Monotonic, not the injected Clock's `now_iso()`, because this
    #: is purely an internal decay window, never a domain timestamp.
    relay_depth_updated_at: float = 0.0


@dataclass(slots=True)
class HarnessBootSpec:
    """One boot-declared harness (D8): everything :meth:`HarnessSupervisor.open`
    needs, pre-built by the caller (a future config-driven boot sequence).
    The supervisor does not know how to construct a connector for a ``kind``
    - that wiring is the composition root's job, same as every other
    concrete adapter in this codebase (``build_repos`` wires SQLite repos;
    nothing analogous wires connectors here, deliberately - see the module
    docstring's scope note)."""

    kind: str
    connector: HarnessConnector
    owning_agent_id: str
    project_root: str
    role: str | None = None
    agent_capabilities: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] | None = None
    notify_target: Any = None


@dataclass(slots=True)
class HarnessBootResult:
    """Outcome of ONE :class:`HarnessBootSpec` from :meth:`HarnessSupervisor.open_declared`.

    Exactly one of ``session``/``error`` is set. A failed boot-time start is
    reported here, never raised past :meth:`~HarnessSupervisor.open_declared`
    - D8's "reported and skipped, never fatal to serve"."""

    spec: HarnessBootSpec
    session: HarnessSession | None
    error: OktoNexusError | None


class HarnessSupervisor:
    """Owns every live harness-connector session for the ``serve`` process.

    ONE instance is shared process-wide (like
    :class:`~okto_nexus.application.approvals.ApprovalService`): every
    boot-declared AND on-demand session converges on the same
    :meth:`open` call (D8), so there is exactly one code path that ever adds
    an entry to the live registry.

    ``messages`` is OPTIONAL, following this codebase's standing convention
    for an optional cross-slice dependency (``governance``/``approvals`` on
    :class:`~okto_nexus.application.messages.MessageService` itself are the
    precedent): when wired, a notable event (:data:`NOTABLE_EVENT_KINDS`) is
    ALSO delivered through the existing per-recipient inbox (D10, ADR 0001)
    with the harness's own registered agent as sender; when ``None``, that
    delivery is a no-op and only the durable :class:`HarnessEventRepo` row
    (and the in-memory publish) happen - the pump keeps working either way.
    """

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory,
        clock: Clock,
        agents: AgentRepo,
        sessions: HarnessSessionRepo,
        events: HarnessEventRepo,
        subscribers: HarnessSubscriberRegistry,
        messages: MessageService | None = None,
        inbox_notifier: InboxDeliveryNotifier | None = None,
        start_timeout_s: float = DEFAULT_START_TIMEOUT_SECONDS,
        close_timeout_s: float = DEFAULT_CLOSE_TIMEOUT_SECONDS,
        forward_timeout_s: float = DEFAULT_FORWARD_TIMEOUT_SECONDS,
        max_relay_depth: int = DEFAULT_MAX_RELAY_DEPTH,
        relay_depth_ttl_s: float = DEFAULT_RELAY_DEPTH_TTL_SECONDS,
    ) -> None:
        self._cf = connection_factory
        self._clock = clock
        self._agents = agents
        self._sessions = sessions
        self._events = events
        self._subscribers = subscribers
        self._messages = messages
        # SYS-03/UAT-05 follow-up: OPTIONAL, same standing convention as
        # `messages` above - None means the target grammar still does not
        # reach a harness (today's pre-fix behaviour), never an error.
        self._inbox_notifier = inbox_notifier
        self._start_timeout_s = float(start_timeout_s)
        self._close_timeout_s = float(close_timeout_s)
        self._forward_timeout_s = float(forward_timeout_s)
        # Harness-to-harness relay loop protection (limitation 2) - see
        # DEFAULT_MAX_RELAY_DEPTH / DEFAULT_RELAY_DEPTH_TTL_SECONDS.
        self._max_relay_depth = int(max_relay_depth)
        self._relay_depth_ttl_s = float(relay_depth_ttl_s)

        self._lock = threading.RLock()
        self._live: dict[str, _LiveSession] = {}

    # ------------------------------------------------------------------ #
    # subscriber registry passthrough (so a caller needs only ONE reference)
    # ------------------------------------------------------------------ #
    @property
    def subscribers(self) -> HarnessSubscriberRegistry:
        """The shared in-memory registry (D1) - a future SSE/stream reader
        subscribes here directly with a live ``session_id``."""
        return self._subscribers

    # ------------------------------------------------------------------ #
    # open (on-demand AND boot-declared converge here - D8)
    # ------------------------------------------------------------------ #
    def open(
        self,
        *,
        kind: str,
        connector: HarnessConnector,
        owning_agent_id: str,
        project_root: str,
        role: str | None = None,
        agent_capabilities: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        notify_target: Any = None,
    ) -> HarnessSession:
        """Open one harness session. Bounded; never leaves partial state.

        Order: bounded ``connector.start()`` -> ONE transaction that BOTH
        registers ``owning_agent_id`` as an ordinary Agent (D3) AND persists
        the durable session row -> add to the live registry -> start the
        background pump (full-duplex connectors only; see the module
        docstring).

        The agent registration deliberately happens AFTER a successful
        ``start()``, not before: this connector's identity needs no key and
        nothing calls back into Nexus to authenticate DURING ``start()``, so
        registering early buys nothing - and it costs a real hazard.
        Registering before a bounded-but-failed or wedged ``start()`` would
        leave a real, ACTIVE, routable Agent row (reachable by
        ``direct``/``capability``/``role``/``tag``) for a harness that never
        actually came up - exactly the "looks alive, delivers nothing"
        failure class D8 exists to prevent, now installed in the routing
        registry itself rather than merely in a session that never went
        live. Registering together with ``sessions.create`` in ONE
        transaction means a failure on EITHER write leaves NEITHER a phantom
        agent NOR a live session with no durable row to back it - see the
        failure branch below, which also tears the connector back down
        before propagating (the connector DID start successfully by this
        point, so there is something to tear down).

        Any failure before the live-registry insert raises WITHOUT ever
        having mutated the live registry, so a failed ``open`` can never
        corrupt or affect an already-open session (D8's isolation
        requirement) - the caller (an on-demand tool call, or the boot loop
        in :meth:`open_declared`) is the one responsible for not letting one
        failure stop it from trying the next harness.
        """
        validate_harness_kind(kind)
        if not isinstance(connector, HarnessConnector):
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "connector does not implement the HarnessConnector port.",
                {"kind": kind},
            )
        if not owning_agent_id:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR, "owning_agent_id is required.", {}
            )
        if not project_root:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR, "project_root is required.", {}
            )

        session = self._bounded_start(connector, owning_agent_id=owning_agent_id, kind=kind)
        if session.harness_kind != kind:  # pragma: no cover - defensive, connector bug
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "connector returned a session whose harness_kind does not "
                "match the kind it was opened as.",
                {"requested_kind": kind, "returned_kind": session.harness_kind},
            )
        if not can_transition_session(session.status, STATUS_RUNNING):
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                "connector.start() returned a session in an unexpected "
                "initial status (expected STARTING).",
                {"kind": kind, "status": session.status},
            )
        session.status = STATUS_RUNNING

        now = self._clock.now_iso()
        try:
            with self._cf.unit_of_work() as uow:
                # D3: the connector authenticates as an ordinary agent via
                # the EXISTING nxs_ key path - reusing AgentRepo.upsert (the
                # same idempotent registration agent_register itself
                # performs) is that reuse, not a new credential scheme.
                self._agents.upsert(
                    uow,
                    agent_id=owning_agent_id,
                    role=role,
                    capabilities=dict(agent_capabilities or {}),
                    metadata={**dict(metadata or {}), "harness_kind": kind},
                )
                self._sessions.create(uow, session=session, created_at=now)
        except Exception as exc:  # noqa: BLE001 - a started connector needs tearing down either way
            self._best_effort_teardown(connector, session)
            if isinstance(exc, OktoNexusError):
                raise
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                f"harness '{kind}' started but its session/agent record could "
                f"not be persisted: {exc}",
                {"kind": kind, "session_id": session.session_id, "exception_type": type(exc).__name__},
            ) from exc

        with self._lock:
            if session.session_id in self._live:  # pragma: no cover - defensive
                raise OktoNexusError(
                    ErrorCode.INTERNAL_ERROR,
                    "a live session with this id already exists.",
                    {"session_id": session.session_id},
                )
            live = _LiveSession(
                connector=connector,
                session=session,
                project_root=project_root,
                notify_target=notify_target,
            )
            self._live[session.session_id] = live

        # Full-duplex connectors (send_only=False) get ONE dedicated daemon
        # pump thread that blocks on connector.events() for the session's
        # whole life (D1's push mechanism). send_only connectors are drained
        # synchronously by send() instead - see the module docstring.
        if not connector.capabilities.send_only:
            thread = threading.Thread(
                target=self._pump,
                args=(session.session_id,),
                daemon=True,
                name=f"harness-pump-{session.session_id}",
            )
            with self._lock:
                live.pump_thread = thread
            thread.start()

        # SYS-03/UAT-05 follow-up: subscribe THIS session to ordinary
        # target-grammar deliveries addressed at its own owning_agent_id -
        # see _on_inbox_delivery's docstring for the forwarding contract.
        # Every send_only connector (not just full-duplex ones) is eligible:
        # send_turn is the one verb send_only connectors always accept, and
        # that is the only verb a forward ever issues.
        if self._inbox_notifier is not None:
            handle = self._inbox_notifier.subscribe(
                owning_agent_id,
                functools.partial(
                    self._on_inbox_delivery, session.session_id, owning_agent_id
                ),
            )
            with self._lock:
                live.inbox_subscription = handle
        return session

    def open_declared(
        self, specs: Iterable[HarnessBootSpec]
    ) -> list[HarnessBootResult]:
        """Boot-time entry point (D8): open every declared spec through the
        SAME :meth:`open` the on-demand path uses, isolating each failure so
        one misbehaving harness never blocks the rest, or a caller reading
        this list, or ``serve`` itself - nothing here raises.
        """
        results: list[HarnessBootResult] = []
        for spec in specs:
            try:
                session = self.open(
                    kind=spec.kind,
                    connector=spec.connector,
                    owning_agent_id=spec.owning_agent_id,
                    project_root=spec.project_root,
                    role=spec.role,
                    agent_capabilities=spec.agent_capabilities,
                    metadata=spec.metadata,
                    notify_target=spec.notify_target,
                )
                results.append(HarnessBootResult(spec=spec, session=session, error=None))
            except OktoNexusError as exc:
                results.append(HarnessBootResult(spec=spec, session=None, error=exc))
            except Exception as exc:  # noqa: BLE001 - boot must never propagate a raw exception
                wrapped = OktoNexusError(
                    ErrorCode.INTERNAL_ERROR,
                    f"unexpected failure starting harness '{spec.kind}': {exc}",
                    {"kind": spec.kind, "exception_type": type(exc).__name__},
                )
                results.append(HarnessBootResult(spec=spec, session=None, error=wrapped))
        return results

    def _bounded_start(
        self, connector: HarnessConnector, *, owning_agent_id: str, kind: str
    ) -> HarnessSession:
        """Run ``connector.start()`` on a helper thread, bounded by
        ``start_timeout_s`` (D8: "every supervisor-side wait is bounded and
        raises a clear error on expiry... a wedged supervisor is worse than
        a crashed one"). ``Thread.join(timeout)`` is a plain blocking wait on
        a condition variable - not a re-checking sleep loop - so this bound
        introduces no polling.

        Python gives no safe way to cancel a running thread: if ``start()``
        is genuinely wedged (not merely slow), the helper thread is
        abandoned (``daemon=True``, so it can never block process exit) and
        this call still returns - within the bound, every time. That is the
        D8 requirement; it does not claim the abandoned thread's resources
        (a half-spawned child process, an open socket) are reclaimed, which
        for a wedged connector they generally are not - reported honestly
        rather than smoothed over, per the standing instruction the four
        connector modules themselves follow.
        """
        outcome: dict[str, Any] = {}

        def _run() -> None:
            try:
                outcome["session"] = connector.start(owning_agent_id=owning_agent_id)
            except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread below
                outcome["error"] = exc

        thread = threading.Thread(
            target=_run, daemon=True, name=f"harness-start-{kind}"
        )
        thread.start()
        thread.join(self._start_timeout_s)
        if thread.is_alive():
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                f"harness '{kind}' did not start within {self._start_timeout_s}s "
                "(the connector may be wedged); the attempt was abandoned.",
                {"kind": kind, "timeout_s": self._start_timeout_s},
            )
        if "error" in outcome:
            exc = outcome["error"]
            if isinstance(exc, OktoNexusError):
                raise exc
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                f"harness '{kind}' failed to start: {exc}",
                {"kind": kind, "exception_type": type(exc).__name__},
            ) from exc
        session = outcome.get("session")
        if not isinstance(session, HarnessSession):  # pragma: no cover - defensive
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                f"harness '{kind}' connector.start() returned no session.",
                {"kind": kind},
            )
        return session

    # ------------------------------------------------------------------ #
    # send / steer / interrupt (one verb-dispatch method - HarnessCommand
    # already carries the verb, so there is no reason to fork into three)
    # ------------------------------------------------------------------ #
    def send(
        self,
        session_id: str,
        verb: str,
        payload: Mapping[str, Any] | None = None,
        *,
        _relay_depth: int | None = None,
    ) -> None:
        """Deliver ``verb`` (``send_turn`` / ``steer`` / ``interrupt`` / ``end``)
        to a live session. Capability-gates BEFORE calling the connector
        (the primary gate; the connector's own ``send()`` is the documented
        backstop, not relied on here) so a capability mismatch is a clear,
        immediate ``VALIDATION_ERROR`` instead of a connector-specific
        failure shape.

        Never blocks for a reply (the port's own contract) - EXCEPT that a
        ``send_only`` connector's finite ``events()`` snapshot is drained
        synchronously right here afterward (see the module docstring): that
        drain is bounded by construction (the connector's own docstring:
        "never blocks, never polls... a finite iterator"), not by a
        supervisor-imposed timeout.

        ``_relay_depth`` is INTERNAL - only :meth:`_on_inbox_delivery`
        passes it (see the module docstring's "Harness-to-harness
        relaying" section), giving the depth ``_resolve_relay_depth``
        already decided this forward may run at. Every OTHER caller (every
        MCP/HTTP tool, ``_best_effort_teardown``, every direct test call)
        leaves it ``None``, which resets this session's
        :attr:`_LiveSession.relay_depth` bookkeeping to 0 - this is the
        ONE place that field is ever written, deliberately, so a session
        reached through the ordinary, non-relay path never inherits a
        stale depth left over from an unrelated earlier relay chain.
        Written BEFORE the connector is called, so a fast connector (the
        real hazard this guards: one that replies before this call even
        returns) can never race ahead of its own session's own bookkeeping.
        """
        live = self._require_live(session_id)
        caps = live.connector.capabilities
        self._require_verb_allowed(caps, verb)
        with self._lock:
            live.relay_depth = _relay_depth if _relay_depth is not None else 0
            live.relay_depth_updated_at = time.monotonic()
        command = HarnessCommand(
            session_id=session_id, verb=verb, payload=dict(payload or {})
        )
        live.connector.send(live.session, command)
        if caps.send_only:
            # ``events()`` is a BROADCAST snapshot of an append-only history
            # (RES-A2 fix in ClaudeCodeAttachConnector), never a destructive
            # drain - the port's docstring only promises "an
            # iterable/iterator of normalised inbound events", nothing about
            # exactly-once delivery. A second call after a second send()
            # would therefore re-include every event already handled on the
            # first call. Materialise the snapshot once and replay only the
            # tail past ``send_only_events_handled`` so each event is
            # handled exactly once across this session's whole lifetime,
            # regardless of how many times send() is called.
            snapshot = list(live.connector.events())
            new_events = snapshot[live.send_only_events_handled :]
            live.send_only_events_handled = len(snapshot)
            for event in new_events:
                self._handle_event(session_id, event)

    def _require_verb_allowed(self, caps: HarnessCapabilities, verb: str) -> None:
        if caps.send_only and verb not in _SEND_ONLY_ALLOWED_VERBS:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"this harness connector is send_only; '{verb}' is not "
                "supported (only send_turn).",
                {"verb": verb},
            )
        if verb == "steer" and caps.steer_timing is None:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                "this harness connector does not support steering "
                "(capabilities.steer_timing is None).",
                {"verb": verb},
            )

    # ------------------------------------------------------------------ #
    # Inbox delivery forwarding (SYS-03/UAT-05 follow-up): the existing
    # target grammar (direct/capability/role/tag, ADR 0001) reaching a live
    # harness session.
    # ------------------------------------------------------------------ #
    def _on_inbox_delivery(
        self, session_id: str, owning_agent_id: str, message: Mapping[str, Any]
    ) -> None:
        """Callback registered with the shared ``InboxDeliveryNotifier`` on
        :meth:`open`: an ordinary ``message_create`` fan-out just delivered
        to THIS session's ``owning_agent_id`` inbox via the existing target
        grammar. Forward it as a ``send_turn`` through THIS SAME
        :meth:`send` - never a parallel delivery path, and never a
        fabricated capability: ``send_turn`` is the one verb every
        connector, including a ``send_only`` one (D7b/cc-socks), already
        accepts (:data:`_SEND_ONLY_ALLOWED_VERBS`). Reusing :meth:`send`
        also means this inherits its EXISTING capability guard
        (:meth:`_require_verb_allowed`) and its live-session check
        (:meth:`_require_live`) for free - there is nothing bespoke here to
        get wrong independently of those.

        Hand-off, not consumption (see
        :meth:`~okto_nexus.application.messages.MessageService.
        _maybe_notify_inbox_subscribers`'s docstring for the full
        justification): the delivery row this callback describes was
        ALREADY committed, durably, before this callback ever runs. A
        failure anywhere in this method - a dead connector, a timed-out
        transport write, this method raising outright - never loses the
        message; it is still sitting exactly where it always would have
        been, in the recipient's ordinary inbox, independent of whether the
        push below ever fires. Bounded by :attr:`_forward_timeout_s`
        (:meth:`_bounded_call`, the same non-polling ``Thread.join``
        pattern :meth:`open`/:meth:`close` already use) so a wedged
        connector can never turn an inbound message into a wedged caller
        (D8) - every failure, including a timeout, is caught and logged via
        :meth:`_log_best_effort_failure`, never raised back to the
        publisher.

        Guards, in order (see the module docstring's "Harness-to-harness
        relaying" section for the full design rationale behind the second
        one):

        * **Same-session self-address is unconditionally refused, at any
          depth.** A message whose ``from_agent_id`` is THIS session's own
          ``owning_agent_id`` is never forwarded, full stop - a ``direct``
          target does not exclude the sender at the routing layer the way
          group targets do (see ``MessageService._resolve_recipients``'s
          own docstring), so a session's ``notify_target`` pointed at
          itself is reachable and always degenerate: there is no legitimate
          reading of "harness relays to itself" as intentional
          orchestration, unlike A->B, so this is not depth-limited, it is
          simply never done.
        * **A message from ANY OTHER currently-live harness's agent IS now
          forwarded** (the limitation 2 fix - this previously matched the
          same blanket block as the self-address case above; it no longer
          does), bounded by :meth:`_resolve_relay_depth`'s hop cap so a
          deliberate A->B relay works while an A<->B (or longer) runaway
          cascade is refused, loudly
          (:meth:`_report_relay_cascade_blocked`), once the cap is reached.
        * A message with no non-empty string ``body`` is skipped, not
          forwarded as an empty turn every connector's own payload
          validation would reject anyway (``pi``/``codex``:
          ``payload['text']``; ``claude_code`` stream:
          ``payload['content']`` - see the next paragraph) - this is not a
          failure, just nothing to forward.

        Payload shape: BOTH known keys are set (``text`` for pi/codex,
        ``content`` for the claude_code stream connector) rather than
        switching on ``harness_kind`` - each connector reads only its own
        key via a plain ``.get(...)``, so the extra key is inert, and this
        stays correct without updating this method for a future
        connector's key choice as long as it also reads text/content.
        """
        from_agent_id = message.get("from_agent_id")
        if isinstance(from_agent_id, str) and from_agent_id == owning_agent_id:
            return
        body = message.get("body")
        if not isinstance(body, str) or not body:
            return
        relay_depth = 0
        if isinstance(from_agent_id, str):
            relay_depth = self._resolve_relay_depth(from_agent_id)
            if relay_depth is None:
                self._report_relay_cascade_blocked(
                    target_session_id=session_id, from_agent_id=from_agent_id
                )
                return
        payload = {"text": body, "content": body}
        try:
            self._bounded_call(
                lambda: self.send(
                    session_id, "send_turn", payload, _relay_depth=relay_depth
                ),
                timeout_s=self._forward_timeout_s,
                label="forwarding an inbox delivery",
            )
        except Exception:  # noqa: BLE001 - best-effort: a forward failure must never wedge the caller
            self._log_best_effort_failure(
                "forwarding an inbox delivery to the harness connector", session_id
            )

    def _resolve_relay_depth(self, from_agent_id: str) -> int | None:
        """The depth THIS forward would run at, or ``None`` if it would
        exceed :attr:`_max_relay_depth` (the caller's signal to refuse the
        forward and report it - see :meth:`_report_relay_cascade_blocked`).

        Read-only - does NOT itself write :attr:`_LiveSession.relay_depth`;
        that happens inside :meth:`send` (see its own docstring for why the
        write belongs there, not here). ``from_agent_id``'s depth is looked
        up against ITS OWN live session (0 if it has none, or if its own
        last-recorded depth is older than :attr:`_relay_depth_ttl_s` - an
        expired chain is treated as a fresh one), so a message from an
        ordinary, non-harness sender (an operator) resolves to depth 1 -
        the first hop of a brand new chain - exactly like a harness's own
        first, organic ``turn_completed``.
        """
        now = time.monotonic()
        with self._lock:
            source_depth = 0
            for live in self._live.values():
                if live.session.owning_agent_id != from_agent_id:
                    continue
                if (
                    live.relay_depth > 0
                    and (now - live.relay_depth_updated_at) <= self._relay_depth_ttl_s
                ):
                    source_depth = live.relay_depth
                break
        new_depth = source_depth + 1
        if new_depth > self._max_relay_depth:
            return None
        return new_depth

    def _report_relay_cascade_blocked(
        self, *, target_session_id: str, from_agent_id: str
    ) -> None:
        """LOUD, attributable refusal (never a silent drop - see the module
        docstring) when :meth:`_resolve_relay_depth` refuses a forward.

        Publishes AND persists a synthetic ``kind="error"``
        :class:`~okto_nexus.domain.harness.HarnessEvent` for the session
        the forward WOULD have reached, deliberately calling
        :meth:`~HarnessSubscriberRegistry.publish`/:meth:`_persist_event`
        directly rather than going through :meth:`_handle_event` /
        :meth:`_deliver_notable_message`: routing this through the notable
        -message path would create ANOTHER message from this session's own
        agent, which would re-enter THIS SAME forwarding path on its next
        delivery - the loop guard manufacturing a loop of its own. A
        stderr breadcrumb is also printed, matching every other
        best-effort failure in this module, so this is visible even to an
        operator watching neither the subscriber stream nor event replay.

        ``native_event`` is a value this module itself invents
        (``"nexus/relay_depth_exceeded"``), disclosed here rather than left
        implicit: :class:`HarnessEvent`'s own docstring describes
        ``native_event`` as the harness's own name for an occurrence, and
        this is the one synthetic exception - the supervisor's own
        refusal, not anything any harness emitted.
        """
        with self._lock:
            target = self._live.get(target_session_id)
        if target is None:  # pragma: no cover - reaped between refusal and this report
            return
        event = HarnessEvent(
            session_id=target_session_id,
            harness_kind=target.session.harness_kind,
            kind="error",
            native_event="nexus/relay_depth_exceeded",
            occurred_at=self._clock.now_iso(),
            payload={
                "reason": "harness-to-harness relay depth exceeded; forward refused",
                "from_agent_id": from_agent_id,
                "max_relay_depth": self._max_relay_depth,
            },
        )
        try:
            self._subscribers.publish(event)
        except Exception:  # noqa: BLE001 - a broken registry must never hide the refusal itself
            pass
        self._persist_event(event)
        print(
            "[okto-nexus] harness supervisor: relay refused - depth would exceed "
            f"max_relay_depth={self._max_relay_depth} (from '{from_agent_id}' into "
            f"session {target_session_id}).",
            file=sys.stderr,
        )

    # ------------------------------------------------------------------ #
    # close (explicit, operator/agent-requested end)
    # ------------------------------------------------------------------ #
    def close(self, session_id: str) -> HarnessSession:
        """End a live session and stop tracking it.

        CLAIMS the session first (:meth:`_claim_for_reap`) - this is what
        makes ``close`` deterministic and race-free against the full-duplex
        pump thread (:meth:`_pump`), which claims the SAME way once it
        notices the connector actually stopped: whichever of the two calls
        this first wins outright, and the other's claim comes back ``None``
        (a safe no-op) since :meth:`_claim_for_reap` is the ONLY place
        anything removes a session from the live registry.

        Deliberately does NOT mutate ``live.session.status`` before the
        connector calls below: the connector still sees the SAME
        :class:`~okto_nexus.domain.harness.HarnessSession` object it started
        with, in whatever status it was actually in, exactly as if ``close``
        had not touched it yet. Only :meth:`_finish_reap`, called LAST,
        writes the terminal status - so a connector that ever starts
        inspecting ``session.status`` internally (none of the four shipped
        ones currently do; ``claude_code_attach.py`` tracks its OWN separate
        copy) is never handed an already-``ENDED`` session while being asked
        to end it.

        Best-effort on the connector side (a ``send(verb="end")`` when the
        connector supports it, then its own non-port ``close()`` lifecycle
        helper when it exposes one - see the four connector modules'
        "Lifecycle helpers (not part of the port)" sections; not every
        connector has one, and this call tolerates that). ALWAYS returns the
        final in-memory :class:`HarnessSession`, even when every best-effort
        step below failed - a stuck connector must never make ``close``
        itself hang or fail (D8: a wedged supervisor is worse than a crashed
        one).
        """
        live = self._claim_for_reap(session_id)
        if live is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "no live harness session with this id.",
                {"session_id": session_id},
            )
        self._best_effort_teardown(live.connector, live.session)
        self._finish_reap(live, error=None)
        return live.session

    def _best_effort_teardown(
        self, connector: HarnessConnector, session: HarnessSession
    ) -> None:
        """Ask a connector to stop, tolerating every failure (bounded, never
        raises): a ``send(verb="end")`` when capabilities allow it, then the
        connector's own non-port ``close()`` lifecycle helper when it
        exposes one. Shared by :meth:`close` (an already-live session the
        operator is ending) and :meth:`open`'s failure branch (a connector
        that DID start successfully but whose session/agent record then
        failed to persist - it still needs tearing down, even though it was
        never added to the live registry)."""
        caps = connector.capabilities
        if not caps.send_only:
            try:
                self._bounded_call(
                    lambda: connector.send(
                        session, HarnessCommand(session_id=session.session_id, verb="end")
                    ),
                    timeout_s=self._close_timeout_s,
                    label="connector end",
                )
            except Exception:  # noqa: BLE001 - best-effort: closing must never itself fail
                self._log_best_effort_failure(
                    "sending 'end' to harness connector", session.session_id
                )
        close_fn = getattr(connector, "close", None)
        if callable(close_fn):
            try:
                self._bounded_call(
                    close_fn, timeout_s=self._close_timeout_s, label="connector close"
                )
            except Exception:  # noqa: BLE001 - best-effort, see above
                self._log_best_effort_failure("closing harness connector", session.session_id)

    def _bounded_call(self, fn: Any, *, timeout_s: float, label: str) -> None:
        """Run ``fn()`` on a helper thread, bounded by ``timeout_s`` - the
        same non-polling ``Thread.join(timeout)`` pattern as
        :meth:`_bounded_start`, reused here so ``close`` can never hang on a
        wedged connector either (D8). Every caller of this method wraps it
        in ``except Exception:`` (best-effort teardown); a non-``Exception``
        ``BaseException`` from ``fn`` (``SystemExit``/``KeyboardInterrupt``/
        ``GeneratorExit``) is therefore normalised into an
        :class:`OktoNexusError` here too, same as :meth:`_bounded_start`
        does for ``connector.start()`` - otherwise it would slip past every
        caller's ``except Exception`` and break the "``close`` never raises"
        contract for exactly the class of failure this method exists to
        bound."""
        outcome: dict[str, Any] = {}

        def _run() -> None:
            try:
                fn()
            except BaseException as exc:  # noqa: BLE001 - re-raised (normalised) below
                outcome["error"] = exc

        thread = threading.Thread(target=_run, daemon=True, name=f"harness-{label}")
        thread.start()
        thread.join(timeout_s)
        if thread.is_alive():
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                f"{label} did not complete within {timeout_s}s; abandoned.",
                {"timeout_s": timeout_s},
            )
        if "error" in outcome:
            exc = outcome["error"]
            if isinstance(exc, OktoNexusError):
                raise exc
            raise OktoNexusError(
                ErrorCode.INTERNAL_ERROR,
                f"{label} failed: {exc}",
                {"exception_type": type(exc).__name__},
            ) from exc

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get(self, session_id: str) -> HarnessSession | None:
        """The live, in-memory session, or ``None`` if it is not (or no
        longer) live. NOT a read of :class:`HarnessSessionRepo` - see the
        module/``_LiveSession`` docstrings for why the two can legitimately
        disagree after an unclean process exit."""
        with self._lock:
            live = self._live.get(session_id)
        return live.session if live is not None else None

    def list_live(self) -> list[HarnessSession]:
        """Every currently-live session (in-memory), newest-registered order
        not guaranteed - callers that need a stable order should sort."""
        with self._lock:
            return [live.session for live in self._live.values()]

    def replay_events(
        self, session_id: str, *, after_sequence: int = 0, limit: int = 200
    ) -> list[HarnessEvent]:
        """Durable replay (D10): the events a session actually emitted, in
        order, straight from :class:`HarnessEventRepo` - independent of
        whether the session is still live. This is what makes the
        no-polling push claim checkable after the fact."""
        with self._cf.unit_of_work(write=False) as uow:
            return self._events.list_for_session(
                uow, session_id=session_id, after_sequence=after_sequence, limit=limit
            )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _require_live(self, session_id: str) -> _LiveSession:
        with self._lock:
            live = self._live.get(session_id)
        if live is None:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                "no live harness session with this id.",
                {"session_id": session_id},
            )
        return live

    def _pump(self, session_id: str) -> None:
        """The background thread body for a full-duplex connector: drain
        ``connector.events()`` (a blocking generator) for the session's
        whole life, handling each event as it arrives. Runs until the
        generator ends (the connector observed its own end, or died) or
        raises (the connector broke) - either way :meth:`_reap` runs
        exactly once, and only this session's bookkeeping is touched, so one
        session's pump ending can never affect another's (D8)."""
        with self._lock:
            live = self._live.get(session_id)
        if live is None:  # pragma: no cover - defensive: reaped before the thread ran
            return
        try:
            for event in live.connector.events():
                self._handle_event(session_id, event)
        except BaseException as exc:  # noqa: BLE001 - the pump is this session's only watchdog
            self._reap(session_id, error=exc)
            return
        self._reap(session_id, error=None)

    def _handle_event(self, session_id: str, event: HarnessEvent) -> None:
        """Publish -> persist -> (maybe) notable message, IN THAT ORDER and
        no other (the spec's exact event-flow requirement): the in-memory
        push happens first and unconditionally; the durable write and the
        inbox delivery are both best-effort AFTER it and can never delay or
        gate it."""
        try:
            self._subscribers.publish(event)
        except Exception:  # noqa: BLE001 - a broken registry must never break the pump
            self._log_best_effort_failure("publishing harness event to subscribers", session_id)
        self._persist_event(event)
        if event.kind in NOTABLE_EVENT_KINDS:
            self._deliver_notable_message(session_id, event)

    def _persist_event(self, event: HarnessEvent) -> None:
        try:
            with self._cf.unit_of_work() as uow:
                self._events.append(
                    uow,
                    event_id=new_id("hevt"),
                    event=event,
                    created_at=self._clock.now_iso(),
                )
        except Exception:  # noqa: BLE001 - durability is best-effort relative to delivery (D1)
            self._log_best_effort_failure("persisting harness event", event.session_id)

    def _deliver_notable_message(self, session_id: str, event: HarnessEvent) -> None:
        """D10: turn completion (and ``error``, see :data:`NOTABLE_EVENT_KINDS`)
        is ALSO delivered as a message through the EXISTING per-recipient
        inbox (ADR 0001) - reusing
        :meth:`~okto_nexus.application.messages.MessageService.create_message`
        rather than building a parallel delivery mechanism. The connector's
        registered agent (``owning_agent_id``) is the sender, per D10/D3. No
        recipient is named on the frozen :class:`HarnessSession` shape, so
        the default target is a bare ``{"strategy": "broadcast"}`` - ADR
        0001's OWN bounded default (the sender's workspace, i.e. this
        session's ``project_root``, S1) - unless the caller supplied
        ``notify_target`` at :meth:`open` time. Best-effort: a delivery
        failure must never break the pump or lose the durable event row
        already written by :meth:`_persist_event`."""
        if self._messages is None:
            return
        with self._lock:
            live = self._live.get(session_id)
        if live is None:  # pragma: no cover - defensive: reaped mid-event
            return
        target = live.notify_target if live.notify_target is not None else {
            "strategy": "broadcast"
        }
        body = json.dumps(
            {
                "native_event": event.native_event,
                "payload": event.payload,
                "thread_id": event.thread_id,
                "turn_id": event.turn_id,
                "occurred_at": event.occurred_at,
            },
            ensure_ascii=False,
        )
        try:
            self._messages.create_message(
                project_root=live.project_root,
                from_agent_id=live.session.owning_agent_id,
                subject=f"harness {live.session.harness_kind} session "
                f"{session_id}: {event.kind}",
                body=body,
                target=target,
            )
        except Exception:  # noqa: BLE001 - best-effort, see docstring
            self._log_best_effort_failure("delivering notable harness event as a message", session_id)

    def _reap(self, session_id: str, *, error: BaseException | None) -> None:
        """Claim + finish a reap in one step - the pump thread's own path
        (:meth:`_pump`), where nothing else needs the still-live
        :class:`_LiveSession` in between. :meth:`close` instead calls
        :meth:`_claim_for_reap` and :meth:`_finish_reap` separately, with the
        connector calls sandwiched in between - see :meth:`close`'s
        docstring for why that ordering matters."""
        live = self._claim_for_reap(session_id)
        if live is not None:
            self._finish_reap(live, error=error)

    def _claim_for_reap(self, session_id: str) -> "_LiveSession | None":
        """Atomically remove ``session_id`` from the live registry and return
        it (``None`` if it was already gone - reaped, or closed, by someone
        else). This is the ONLY place anything pops ``_live``, so whichever
        caller wins this call is the one, and only one, allowed to finish
        the reap - :meth:`_pump` and :meth:`close` both call this and both
        tolerate ``None`` back (a safe no-op: the OTHER caller already owns
        it).

        ALSO the single place an inbox subscription (SYS-03/UAT-05
        follow-up) is torn down - a reaped session must stop receiving
        forwards, or it would keep calling into an already-gone connector
        and logging best-effort failures forever."""
        with self._lock:
            live = self._live.pop(session_id, None)
        if live is not None:
            self._unsubscribe_inbox(live)
        return live

    def _unsubscribe_inbox(self, live: "_LiveSession") -> None:
        if self._inbox_notifier is None or live.inbox_subscription is None:
            return
        try:
            self._inbox_notifier.unsubscribe(live.inbox_subscription)
        except Exception:  # noqa: BLE001 - best-effort: a broken notifier must never break a reap/close
            self._log_best_effort_failure(
                "unsubscribing from inbox deliveries", live.session.session_id
            )

    def _finish_reap(self, live: "_LiveSession", *, error: BaseException | None) -> None:
        """Given an ALREADY-CLAIMED ``live`` (see :meth:`_claim_for_reap`),
        transition and persist a terminal status - ONLY for a connector that
        declares ``observes_session_end=True``.

        A non-observing connector (D7b/cc-socks) never gets a fabricated
        ``ENDED``/``ERRORED`` here - per the domain module's own docstring,
        such a session "is abandoned by the peer, not transitioned". Nexus
        still stops TRACKING it (the claim already did that), it just never
        pretends to know how the peer's own session actually ended.
        """
        caps = live.connector.capabilities
        if not caps.observes_session_end:
            return
        now = self._clock.now_iso()
        target_status = STATUS_ERRORED if error is not None else STATUS_ENDED
        if not can_transition_session(live.session.status, target_status):
            return
        live.session.status = target_status
        live.session.ended_at = now
        try:
            with self._cf.unit_of_work() as uow:
                self._sessions.update_status(
                    uow,
                    session_id=live.session.session_id,
                    status=target_status,
                    updated_at=now,
                    ended_at=now,
                )
        except Exception:  # noqa: BLE001 - durability is best-effort relative to reaping
            self._log_best_effort_failure(
                "persisting harness session end status", live.session.session_id
            )

    @staticmethod
    def _log_best_effort_failure(action: str, session_id: str) -> None:
        """Stderr breadcrumb for a swallowed best-effort failure (durability
        write, notable-message delivery, subscriber publish). Never raises;
        mirrors the existing ``print(..., file=sys.stderr)`` breadcrumbs
        elsewhere in this codebase's own best-effort paths (e.g.
        ``cli/serve.py``'s auto-prune) rather than silently losing the
        signal entirely."""
        exc_type = sys.exc_info()[0]
        suffix = f" ({exc_type.__name__})" if exc_type is not None else ""
        print(
            f"[okto-nexus] harness supervisor: {action} failed for session "
            f"{session_id}{suffix}; continuing.",
            file=sys.stderr,
        )
