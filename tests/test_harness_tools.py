"""MCP tool-surface tests for the harness connector lifecycle (ADR 0004,
Phase 3.5 - ``adapters/inbound/mcp/tools/harness.py``).

Drives the REAL registered tool functions through a capture-server (mirrors
``tests/test_mcp_projection_tools.py``'s ``CaptureServer`` pattern) against a
FAKE connector injected through ``deps.harness_connector_factories`` (the
injection point ``tools/harness.py`` itself defines for exactly this
purpose). Spawning a real ``pi``/``codex``/``claude`` binary is out of scope
here - the four real connector modules each have their own dedicated test
suite (``test_harness_*_connector.py``) and ``harness_list`` (tested below)
reads their DECLARED capabilities straight off the real classes regardless of
what this file injects, so that guarantee is exercised without spawning
anything either.

Covers, at minimum: the full lifecycle through the tool surface (open -> send
-> get -> close -> get again, durable fallback); D3 agent registration;
kind/substrate validation (the domain HARNESS_KINDS/CLAUDE_CODE_SUBSTRATES
grammar); capability gating (steer rejected on a send_only/steer_timing=None
substrate, matching cc-socks); D10 event replay ordering + notable-message
delivery through the real inbox.
"""

from __future__ import annotations

import asyncio
import queue
import time
from typing import Any

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools import harness as harness_tools
from okto_nexus.domain.base import utc_now_iso
from okto_nexus.domain.harness import (
    STATUS_STARTING,
    STEER_TIMING_IMMEDIATE,
    HarnessCapabilities,
    HarnessEvent,
    HarnessSession,
    new_harness_session_id,
)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
class FakeConnector:
    """Minimal :class:`~okto_nexus.application.ports.HarnessConnector`
    double. Full-duplex by default; pass ``capabilities`` with
    ``send_only=True`` to exercise the cc-socks-shaped finite-snapshot
    ``events()`` instead (mirrors ``harness_supervisor.py``'s own module
    docstring on the port's two real shapes)."""

    def __init__(
        self,
        *,
        kind: str = "pi",
        capabilities: HarnessCapabilities | None = None,
        **_ignored: Any,
    ) -> None:
        self.capabilities = capabilities or HarnessCapabilities(
            send_only=False,
            steer_timing=STEER_TIMING_IMMEDIATE,
            interrupt_requires_settle_wait=False,
            multiplexes_sessions=False,
            observes_session_end=True,
        )
        self._kind = kind
        self._queue: "queue.Queue[Any]" = queue.Queue()
        self.session: HarnessSession | None = None
        self.sent: list[Any] = []
        self.close_called = False

    def start(self, *, owning_agent_id: str) -> HarnessSession:
        session_id = new_harness_session_id()
        self.session = HarnessSession(
            session_id=session_id,
            harness_kind=self._kind,
            owning_agent_id=owning_agent_id,
            status=STATUS_STARTING,
            capabilities=self.capabilities,
            started_at=utc_now_iso(),
        )
        return self.session

    def send(self, session: HarnessSession, command: Any) -> None:
        self.sent.append(command)

    def events(self):
        if self.capabilities.send_only:
            drained: list[Any] = []
            while True:
                try:
                    drained.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            return iter(drained)
        return self._pump_forever()

    def _pump_forever(self):
        while True:
            item = self._queue.get()
            if item is None:
                return
            yield item

    def push_event(
        self, *, kind: str = "output_delta", native_event: str = "native/x", payload=None
    ) -> None:
        assert self.session is not None
        self._queue.put(
            HarnessEvent(
                session_id=self.session.session_id,
                harness_kind=self._kind,
                kind=kind,
                native_event=native_event,
                occurred_at=utc_now_iso(),
                payload=payload or {},
            )
        )

    def end(self) -> None:
        self._queue.put(None)

    def close(self) -> None:
        self.close_called = True
        self.end()


class CaptureServer:
    """Stand-in for FastMCP: ``@server.tool()`` just records the callable."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _call(server: CaptureServer, name: str, **kwargs: Any) -> dict[str, Any]:
    fn = server.tools[name]
    if asyncio.iscoroutinefunction(fn):
        return asyncio.run(fn(**kwargs))
    return fn(**kwargs)


_STREAM_CAPS = HarnessCapabilities(
    send_only=False,
    steer_timing=STEER_TIMING_IMMEDIATE,
    interrupt_requires_settle_wait=False,
    multiplexes_sessions=False,
    observes_session_end=True,
)
_ATTACH_CAPS = HarnessCapabilities(
    send_only=True,
    steer_timing=None,
    interrupt_requires_settle_wait=False,
    multiplexes_sessions=False,
    observes_session_end=False,
)


@pytest.fixture
def ctx(tmp_path):
    # project_root must resolve to a REAL directory (create_message ->
    # resolve_realpath, strict=True) - the notable-message delivery path
    # exercises this even though HarnessSupervisor.open() itself does not.
    project_root = str(tmp_path / "project")
    (tmp_path / "project").mkdir()
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    connectors: dict[str, list[FakeConnector]] = {"pi": [], "codex": [], "claude_code": []}

    def _factory(kind: str):
        def factory(*, project_root: str, substrate: str | None, target_pid, **_ignored):
            caps = _STREAM_CAPS
            if kind == "claude_code" and substrate == "attach":
                caps = _ATTACH_CAPS
            conn = FakeConnector(kind=kind, capabilities=caps)
            connectors[kind].append(conn)
            return conn

        return factory

    deps.harness_connector_factories = {
        "pi": _factory("pi"),
        "codex": _factory("codex"),
        "claude_code": _factory("claude_code"),
    }
    server = CaptureServer()
    harness_tools.register(server, deps)
    return deps, server, connectors, project_root


def _wait_until(predicate, *, timeout_s: float = 2.0) -> None:
    """Poll a predicate (the pump runs on its own daemon thread) - a plain
    bounded retry loop in the TEST, not a claim about the production harness
    path (which is push-based, D1)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate(), "condition never became true within the timeout"


# --------------------------------------------------------------------------- #
# harness_list
# --------------------------------------------------------------------------- #
def test_harness_list_reports_real_connector_capabilities(ctx):
    _deps, server, _connectors, project_root = ctx
    result = _call(server, "harness_list")
    assert result["ok"]
    rows = {(r["kind"], r["substrate"]): r["capabilities"] for r in result["data"]["harnesses"]}
    assert set(rows) == {("pi", None), ("codex", None), ("claude_code", "stream"), ("claude_code", "attach")}
    # Read from the REAL connector classes, independent of this file's fake
    # factories (harness_list never consults deps.harness_connector_factories).
    assert rows[("pi", None)]["steer_timing"] == "NEXT_TURN_BOUNDARY"
    assert rows[("pi", None)]["interrupt_requires_settle_wait"] is True
    assert rows[("codex", None)]["multiplexes_sessions"] is True
    assert rows[("claude_code", "stream")]["send_only"] is False
    # The task's explicit example: cc-socks is visibly send_only + no steer.
    assert rows[("claude_code", "attach")]["send_only"] is True
    assert rows[("claude_code", "attach")]["steer_timing"] is None
    assert rows[("claude_code", "attach")]["observes_session_end"] is False


# --------------------------------------------------------------------------- #
# harness_open
# --------------------------------------------------------------------------- #
def test_harness_open_registers_agent_and_returns_running_session(ctx):
    deps, server, connectors, project_root = ctx
    result = _call(
        server, "harness_open", agent_id="pi-1", kind="pi", project_root=project_root
    )
    assert result["ok"], result
    data = result["data"]
    assert data["status"] == "RUNNING"
    assert data["kind"] == "pi"
    assert data["owning_agent_id"] == "pi-1"
    assert data["capabilities"]["steer_timing"] == "IMMEDIATE"
    assert len(connectors["pi"]) == 1

    with deps.connection_factory.unit_of_work(write=False) as uow:
        agent = deps.repos.agents.get(uow, "pi-1")
    assert agent is not None
    assert agent.metadata.get("harness_kind") == "pi"


def test_harness_open_rejects_unknown_kind(ctx):
    _deps, server, _connectors, project_root = ctx
    result = _call(
        server, "harness_open", agent_id="x", kind="not-a-kind", project_root=project_root
    )
    assert not result["ok"]
    assert result["error"]["code"] == "VALIDATION_ERROR"


def test_harness_open_rejects_substrate_for_non_claude_code_kind(ctx):
    _deps, server, _connectors, project_root = ctx
    result = _call(
        server,
        "harness_open",
        agent_id="x",
        kind="pi",
        project_root=project_root,
        substrate="stream",
    )
    assert not result["ok"]
    assert result["error"]["code"] == "VALIDATION_ERROR"


def test_harness_open_claude_code_attach_requires_target_pid(ctx):
    _deps, server, _connectors, project_root = ctx
    result = _call(
        server,
        "harness_open",
        agent_id="x",
        kind="claude_code",
        project_root=project_root,
        substrate="attach",
    )
    assert not result["ok"]
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert "target_pid" in result["error"]["message"]


def test_harness_open_claude_code_attach_with_target_pid_uses_attach_capabilities(ctx):
    _deps, server, connectors, project_root = ctx
    result = _call(
        server,
        "harness_open",
        agent_id="cc-attach",
        kind="claude_code",
        project_root=project_root,
        substrate="attach",
        target_pid=4242,
    )
    assert result["ok"], result
    assert result["data"]["capabilities"]["send_only"] is True
    assert result["data"]["capabilities"]["steer_timing"] is None
    assert len(connectors["claude_code"]) == 1


# --------------------------------------------------------------------------- #
# harness_send / harness_steer / harness_interrupt
# --------------------------------------------------------------------------- #
def test_harness_send_requires_a_payload(ctx):
    deps, server, connectors, project_root = ctx
    opened = _call(server, "harness_open", agent_id="pi-1", kind="pi", project_root=project_root)
    session_id = opened["data"]["session_id"]

    result = _call(server, "harness_send", session_id=session_id, payload=None)
    assert not result["ok"]
    assert result["error"]["code"] == "VALIDATION_ERROR"


def test_harness_send_steer_interrupt_dispatch_the_right_verb(ctx):
    deps, server, connectors, project_root = ctx
    opened = _call(server, "harness_open", agent_id="pi-1", kind="pi", project_root=project_root)
    session_id = opened["data"]["session_id"]
    conn = connectors["pi"][0]

    r = _call(server, "harness_send", session_id=session_id, payload={"text": "hi"})
    assert r["ok"] and r["data"]["verb"] == "send_turn"

    r = _call(server, "harness_steer", session_id=session_id, payload={"text": "no wait"})
    assert r["ok"] and r["data"]["verb"] == "steer"

    r = _call(server, "harness_interrupt", session_id=session_id)
    assert r["ok"] and r["data"]["verb"] == "interrupt"

    verbs = [c.verb for c in conn.sent]
    assert verbs == ["send_turn", "steer", "interrupt"]
    assert conn.sent[0].payload == {"text": "hi"}
    assert conn.sent[2].payload == {}


def test_harness_steer_is_rejected_when_capability_forbids_it(ctx):
    deps, server, connectors, project_root = ctx
    opened = _call(
        server,
        "harness_open",
        agent_id="cc-attach",
        kind="claude_code",
        project_root=project_root,
        substrate="attach",
        target_pid=99,
    )
    session_id = opened["data"]["session_id"]

    result = _call(server, "harness_steer", session_id=session_id, payload={"content": "x"})
    assert not result["ok"]
    assert result["error"]["code"] == "VALIDATION_ERROR"


def test_harness_send_against_unknown_session_is_not_found(ctx):
    _deps, server, _connectors, project_root = ctx
    result = _call(server, "harness_send", session_id="hsess_nope", payload={"text": "hi"})
    assert not result["ok"]
    assert result["error"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# harness_close / harness_get (live vs durable fallback)
# --------------------------------------------------------------------------- #
def test_harness_close_ends_session_and_get_falls_back_to_durable_row(ctx):
    deps, server, connectors, project_root = ctx
    opened = _call(server, "harness_open", agent_id="pi-1", kind="pi", project_root=project_root)
    session_id = opened["data"]["session_id"]

    live = _call(server, "harness_get", session_id=session_id)
    assert live["ok"] and live["data"]["live"] is True and live["data"]["status"] == "RUNNING"

    closed = _call(server, "harness_close", session_id=session_id)
    assert closed["ok"] and closed["data"]["status"] == "ENDED"
    assert connectors["pi"][0].close_called is True

    after = _call(server, "harness_get", session_id=session_id)
    assert after["ok"]
    assert after["data"]["live"] is False
    assert after["data"]["status"] == "ENDED"

    # A second close is NOT_FOUND - the session is no longer live and close()
    # never re-tears-down an already-reaped session.
    second = _call(server, "harness_close", session_id=session_id)
    assert not second["ok"]
    assert second["error"]["code"] == "NOT_FOUND"


def test_harness_get_unknown_session_is_not_found(ctx):
    _deps, server, _connectors, project_root = ctx
    result = _call(server, "harness_get", session_id="hsess_never_opened")
    assert not result["ok"]
    assert result["error"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# harness_event_list (D10 durable replay) + notable-message delivery
# --------------------------------------------------------------------------- #
def test_harness_event_list_replays_in_order_and_respects_after_sequence(ctx):
    deps, server, connectors, project_root = ctx
    opened = _call(server, "harness_open", agent_id="pi-1", kind="pi", project_root=project_root)
    session_id = opened["data"]["session_id"]
    conn = connectors["pi"][0]

    conn.push_event(kind="turn_started", native_event="n1")
    conn.push_event(kind="output_delta", native_event="n2", payload={"chunk": "hi"})
    conn.push_event(kind="turn_completed", native_event="n3")

    _wait_until(
        lambda: _call(server, "harness_event_list", session_id=session_id)["data"]["count"] >= 3
    )

    result = _call(server, "harness_event_list", session_id=session_id)
    assert result["ok"]
    events = result["data"]["events"]
    assert [e["native_event"] for e in events] == ["n1", "n2", "n3"]
    assert [e["kind"] for e in events] == ["turn_started", "output_delta", "turn_completed"]
    assert events[1]["payload"] == {"chunk": "hi"}

    first_seq_result = _call(
        server, "harness_event_list", session_id=session_id, after_sequence=1
    )
    assert [e["native_event"] for e in first_seq_result["data"]["events"]] == ["n2", "n3"]


def test_harness_turn_completed_event_is_also_delivered_as_a_message(ctx):
    """D10: a notable event (turn_completed) is ALSO delivered through the
    existing per-recipient inbox, sender = the session's own registered
    agent - proves ``build_service``'s MessageService wiring is real, not
    just accepted and discarded."""
    deps, server, connectors, project_root = ctx
    opened = _call(server, "harness_open", agent_id="pi-1", kind="pi", project_root=project_root)
    session_id = opened["data"]["session_id"]
    conn = connectors["pi"][0]

    conn.push_event(kind="turn_completed", native_event="agent_settled")

    def _has_message() -> bool:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            rows = uow.connection.execute(
                "SELECT subject FROM messages WHERE from_agent_id = ?", ("pi-1",)
            ).fetchall()
        return len(rows) >= 1

    _wait_until(_has_message)

    with deps.connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute(
            "SELECT subject, body FROM messages WHERE from_agent_id = ?", ("pi-1",)
        ).fetchall()
    assert len(rows) == 1
    assert session_id in rows[0]["subject"]
    assert "agent_settled" in rows[0]["body"]


# --------------------------------------------------------------------------- #
# H-1: harness_open backend selection (EV-SYS-002 - no silent ambient inherit)
# --------------------------------------------------------------------------- #
@pytest.fixture
def capturing_ctx(tmp_path):
    """Same shape as ``ctx``, but the fake factories capture the ``backend``
    kwarg EXPLICITLY (the plain ``ctx`` fixture's factories swallow it via
    ``**_ignored`` - real, but not proof the value was received)."""
    project_root = str(tmp_path / "project")
    (tmp_path / "project").mkdir()
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    connectors: dict[str, list[FakeConnector]] = {"pi": [], "codex": [], "claude_code": []}
    received_backend: dict[str, list[Any]] = {"pi": [], "codex": [], "claude_code": []}

    def _factory(kind: str):
        def factory(*, project_root: str, substrate, target_pid, backend=None, **_ignored):
            caps = _STREAM_CAPS
            if kind == "claude_code" and substrate == "attach":
                caps = _ATTACH_CAPS
            received_backend[kind].append(backend)
            conn = FakeConnector(kind=kind, capabilities=caps)
            connectors[kind].append(conn)
            return conn

        return factory

    deps.harness_connector_factories = {
        "pi": _factory("pi"),
        "codex": _factory("codex"),
        "claude_code": _factory("claude_code"),
    }
    server = CaptureServer()
    harness_tools.register(server, deps)
    return deps, server, connectors, received_backend, project_root


def test_harness_open_with_no_backend_inherits_ambient_default_visibly(capturing_ctx):
    """Baseline (EV-SYS-002's own hazard): omitting backend keeps today's
    ambient-inherit behaviour (a bare `pi` open silently used the OPERATOR's
    own ~/.pi/agent/settings.json default provider) - but the response must
    now say so explicitly rather than leaving it invisible."""
    _deps, server, _connectors, received_backend, project_root = capturing_ctx
    result = _call(server, "harness_open", agent_id="pi-1", kind="pi", project_root=project_root)
    assert result["ok"], result
    assert received_backend["pi"] == [{}]
    backend_info = result["data"]["backend"]
    assert backend_info["explicit"] is False
    assert backend_info["applied"] == {}
    assert "ambient" in backend_info["note"]
    assert "provider" in backend_info["note"] or "env" in backend_info["note"]


def test_harness_open_backend_override_reaches_the_pi_connector_factory(capturing_ctx):
    """The live hazard, fixed: an operator CAN say which provider/model this
    session uses, and it actually reaches connector construction (not
    dropped on the floor, per EV-SYS-002's own finding that the frozen
    ``PiRpcConnector.__init__`` already accepts ``provider``/``model`` but
    the factory never passed them)."""
    _deps, server, _connectors, received_backend, project_root = capturing_ctx
    backend = {"provider": "zai", "model": "glm-5.3", "extra_args": ["--foo"]}
    result = _call(
        server,
        "harness_open",
        agent_id="pi-1",
        kind="pi",
        project_root=project_root,
        backend=backend,
    )
    assert result["ok"], result
    assert received_backend["pi"] == [backend]
    backend_info = result["data"]["backend"]
    assert backend_info["explicit"] is True
    assert backend_info["applied"] == backend


def test_harness_open_backend_env_reaches_the_codex_connector_factory(capturing_ctx):
    """codex's own backend selection is env-driven (CODEX_HOME + config.toml,
    D5/EV-SYS-002), not a provider/model kwarg - ``env`` is the field that
    must reach it."""
    _deps, server, _connectors, received_backend, project_root = capturing_ctx
    backend = {"env": {"CODEX_HOME": "/tmp/codex_home"}}
    result = _call(
        server,
        "harness_open",
        agent_id="codex-1",
        kind="codex",
        project_root=project_root,
        backend=backend,
    )
    assert result["ok"], result
    assert received_backend["codex"] == [backend]


def test_harness_open_rejects_backend_field_unsupported_for_kind(capturing_ctx):
    """A backend field the connector cannot actually honour is a
    VALIDATION_ERROR naming the supported set - never a silent drop (the
    exact failure class H-2 catches on the agent_id description)."""
    _deps, server, _connectors, received_backend, project_root = capturing_ctx
    result = _call(
        server,
        "harness_open",
        agent_id="codex-1",
        kind="codex",
        project_root=project_root,
        backend={"provider": "zai"},
    )
    assert not result["ok"]
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert "provider" in result["error"]["message"]
    assert "env" in result["error"]["message"]
    assert received_backend["codex"] == []


def test_harness_open_rejects_backend_for_claude_code_attach_substrate(capturing_ctx):
    _deps, server, _connectors, received_backend, project_root = capturing_ctx
    result = _call(
        server,
        "harness_open",
        agent_id="cc-attach",
        kind="claude_code",
        project_root=project_root,
        substrate="attach",
        target_pid=4242,
        backend={"env": {"X": "1"}},
    )
    assert not result["ok"]
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert "attach" in result["error"]["message"]
    assert received_backend["claude_code"] == []


def test_harness_open_rejects_non_object_backend(capturing_ctx):
    _deps, server, _connectors, _received_backend, project_root = capturing_ctx
    result = _call(
        server,
        "harness_open",
        agent_id="pi-1",
        kind="pi",
        project_root=project_root,
        backend=["not", "an", "object"],
    )
    assert not result["ok"]
    assert result["error"]["code"] == "VALIDATION_ERROR"


def test_harness_open_rejects_wrong_typed_backend_env(capturing_ctx):
    _deps, server, _connectors, _received_backend, project_root = capturing_ctx
    result = _call(
        server,
        "harness_open",
        agent_id="codex-1",
        kind="codex",
        project_root=project_root,
        backend={"env": "not-an-object"},
    )
    assert not result["ok"]
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert "env" in result["error"]["message"]


# --------------------------------------------------------------------------- #
# H-2: shipped tool text must not claim the target grammar reaches a harness
# --------------------------------------------------------------------------- #
def test_harness_open_agent_id_description_documents_the_sys03_fix(tmp_path):
    """Supersedes the pre-fix contract test of the same shape (H-2, surface
    task, ``test_harness_open_agent_id_description_does_not_promise_target_
    grammar_routing``): that assertion is now OBSOLETE, not wrong - it
    correctly locked in the pre-fix docstring contract at the time it was
    written. See docs/harness-integrations/evidence/EV-SYS-003-FOLLOWUP-
    target-grammar-fix.md for the fix that made it obsolete.

    EV-SYS-003/EV-UAT-05 originally falsified the claim that
    message_create's target grammar (direct/capability/role/tag) reaches an
    open harness session - it reported delivered_count:1 while the
    connector's own wire trace gained zero bytes. That gap is now CLOSED
    (HarnessSupervisor subscribes each live session's owning_agent_id to an
    InboxDeliveryNotifier and forwards arriving messages as send_turn - see
    application/harness_supervisor.py and the live SYS-03 re-run evidence).

    The SHIPPED tool description must say so accurately: the target grammar
    DOES now reach a live session (not an unqualified/silent claim - the
    original defect was leaving an operator to believe this by omission
    when it was false; the fix is leaving them to believe it correctly now
    that it is true), qualified as best-effort/hand-off (never guaranteed
    delivery the way harness_send is), and must still name harness_send/
    steer/interrupt as the explicit, session_id-addressed alternative for
    guaranteed delivery or a session that may not be live yet. Asserted
    against the LIVE FastMCP tool schema - what an operator actually reads -
    not the module's private string constant.
    """
    pytest.importorskip("mcp")
    from okto_nexus.adapters.inbound.mcp.server import bootstrap as real_bootstrap
    from okto_nexus.adapters.inbound.mcp.server import create_server

    deps = real_bootstrap({}, ["--home", str(tmp_path / "home")])
    server = create_server(deps)
    tools = asyncio.run(server.list_tools())
    harness_open_tool = next(t for t in tools if t.name == "harness_open")
    agent_id_desc = harness_open_tool.inputSchema["properties"]["agent_id"]["description"]

    # The pre-fix false-by-omission phrasing must not reappear verbatim.
    assert "other agents then address it via the normal target" not in agent_id_desc
    # The truthful, POSITIVE claim: input addressing via the target grammar
    # now reaches a live session.
    assert "direct/capability/role/tag" in agent_id_desc
    idx = agent_id_desc.index("direct/capability/role/tag")
    window = agent_id_desc[max(0, idx - 200) : idx]
    assert "can now" in window or "now ADDRESS" in window, (
        "the fixed behaviour must be stated as a positive, qualified claim "
        "(what changed and why it is safe), not a bare unqualified promise"
    )
    # Hand-off/best-effort semantics are disclosed, not silently assumed.
    assert "best-effort" in agent_id_desc or "hand-off" in agent_id_desc
    # The explicit, guaranteed-delivery alternative is still named.
    assert "harness_send" in agent_id_desc


# --------------------------------------------------------------------------- #
# H-1: the REAL (non-fake) connector factories - not exercised by any other
# test here, since every other test injects a fake via
# deps.harness_connector_factories. A wrong kwarg name in
# _default_connector_factories() would otherwise only surface when a real
# binary spawns.
# --------------------------------------------------------------------------- #
def test_default_connector_factories_pass_backend_into_the_real_pi_connector():
    factories = harness_tools._default_connector_factories()
    conn = factories["pi"](
        project_root="/tmp",
        substrate=None,
        target_pid=None,
        backend={"provider": "zai", "model": "glm-5.3", "extra_args": ["--foo"]},
    )
    assert conn._provider == "zai"
    assert conn._model == "glm-5.3"
    assert conn._extra_args == ["--foo"]


def test_default_connector_factories_pass_backend_env_into_the_real_codex_connector():
    factories = harness_tools._default_connector_factories()
    conn = factories["codex"](
        project_root="/tmp",
        substrate=None,
        target_pid=None,
        backend={"env": {"CODEX_HOME": "/tmp/codex_home"}},
    )
    assert conn._env == {"CODEX_HOME": "/tmp/codex_home"}


def test_default_connector_factories_pass_backend_env_into_the_real_claude_code_stream_connector():
    factories = harness_tools._default_connector_factories()
    conn = factories["claude_code"](
        project_root="/tmp",
        substrate="stream",
        target_pid=None,
        backend={"env": {"ANTHROPIC_BASE_URL": "https://example.invalid"}},
    )
    assert conn._env == {"ANTHROPIC_BASE_URL": "https://example.invalid"}
