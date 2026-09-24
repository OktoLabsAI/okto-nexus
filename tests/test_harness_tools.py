"""Authenticated MCP lifecycle regressions using the actual serve composition.

External peers are fixtures; identities, profiles, authorization and durability
use production services. Native protocol suites qualify each adapter separately.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import contextmanager
from types import SimpleNamespace
import queue
import time
from typing import Any

import pytest

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
            compatibility_report={"control_contract_basis": "tested_protocol_contract",
                "native_version": {"pi": "0.85.1", "codex": "0.156.1", "claude_code": "2.1.281"}.get(self._kind),
                "transport_contract": "cc_socks_peer_1" if self.capabilities.send_only else None,
                "peer_protocol": 1 if self.capabilities.send_only else None,
                "compatible_controls": [] if self.capabilities.send_only else ["steer", "interrupt"]},
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
    if hasattr(server, "client"):
        from test_pr34_remediation import tool
        return tool(server.client, server.operator_key, name, kwargs)
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
def ctx(tmp_path, request):
    # Imported at fixture execution to avoid the shared FakeConnector import cycle.
    from test_pr34_remediation import runtime
    with contextmanager(runtime.__wrapped__)(tmp_path, request) as env:
        deps, client, root, _, operator_key, _ = env
        connectors = {kind: [] for kind in ("pi", "codex", "claude_code")}
        originals = deps.harness_connector_factories.copy()
        def wrap(kind):
            def build(**kwargs):
                peer = originals[kind](**kwargs)
                connectors[kind].append(peer)
                return peer
            return build
        deps.harness_connector_factories.update({kind: wrap(kind) for kind in originals})
        yield deps, SimpleNamespace(client=client, operator_key=operator_key), connectors, root


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
def test_harness_open_preserves_agent_and_returns_running_session(ctx):
    deps, server, connectors, project_root = ctx
    result = _call(
        server, "harness_open", agent_id="worker", kind="pi", project_root=project_root
    )
    assert result["ok"], result
    data = result["data"]
    assert data["status"] == "RUNNING"
    assert data["kind"] == "pi"
    assert data["owning_agent_id"] == "worker"
    assert data["capabilities"]["steer_timing"] == "IMMEDIATE"
    assert len(connectors["pi"]) == 1

    with deps.connection_factory.unit_of_work(write=False) as uow:
        agent = deps.repos.agents.get(uow, "worker")
    assert agent is not None
    assert agent.metadata == {"keep": "profile"}
    assert agent.role == "reviewer" and agent.capabilities == {"review": True}


def test_harness_open_rejects_unknown_kind(ctx):
    _deps, server, _connectors, project_root = ctx
    result = _call(
        server, "harness_open", agent_id="worker", kind="not-a-kind", project_root=project_root
    )
    assert not result["ok"]
    assert result["error"]["code"] == "NOT_FOUND"


def test_harness_open_rejects_substrate_for_non_claude_code_kind(ctx):
    _deps, server, _connectors, project_root = ctx
    result = _call(
        server,
        "harness_open",
        agent_id="worker",
        kind="pi",
        project_root=project_root,
        substrate="stream",
    )
    assert not result["ok"]
    assert result["error"]["code"] == "VALIDATION_ERROR"


def test_harness_open_claude_code_attach_requires_separate_opt_in(ctx):
    _deps, server, _connectors, project_root = ctx
    result = _call(
        server,
        "harness_open",
        agent_id="worker",
        kind="claude_code",
        project_root=project_root,
        substrate="attach",
    )
    assert not result["ok"]
    assert result["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.skipif(os.name == "nt", reason="Attach is a POSIX-only substrate; no Windows capability invented.")
def test_harness_open_claude_code_attach_with_target_pid_uses_attach_capabilities(ctx):
    ctx[0].config.feature_harness_attach = True
    _deps, server, connectors, project_root = ctx
    result = _call(
        server,
        "harness_open",
        agent_id="worker",
        kind="claude_code",
        project_root=project_root,
        substrate="attach",
        target_pid=12345,
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
    opened = _call(server, "harness_open", agent_id="worker", kind="pi", project_root=project_root)
    session_id = opened["data"]["session_id"]

    result = _call(server, "harness_send", session_id=session_id, payload=None)
    assert not result["ok"]
    assert result["error"]["code"] == "VALIDATION_ERROR"


def test_harness_send_steer_interrupt_dispatch_the_right_verb(ctx):
    deps, server, connectors, project_root = ctx
    opened = _call(server, "harness_open", agent_id="worker", kind="pi", project_root=project_root)
    session_id = opened["data"]["session_id"]
    conn = connectors["pi"][0]

    r = _call(server, "harness_send", session_id=session_id, payload={"text": "hi"})
    assert r["ok"] and r["data"]["verb"] == "send_turn"
    _wait_until(lambda: len(conn.sent) == 1)

    r = _call(server, "harness_steer", session_id=session_id, payload={"text": "no wait"})
    assert r["ok"] and r["data"]["verb"] == "steer"

    r = _call(server, "harness_interrupt", session_id=session_id)
    assert r["ok"] and r["data"]["verb"] == "interrupt"

    _wait_until(lambda: len(conn.sent) == 3)
    verbs = [c.verb for c in conn.sent]
    assert verbs == ["send_turn", "steer", "interrupt"]
    assert conn.sent[0].payload == {"text": "hi"}
    assert conn.sent[2].payload == {}


@pytest.mark.skipif(os.name == "nt", reason="Attach is a POSIX-only substrate; no Windows capability invented.")
def test_harness_steer_is_rejected_when_capability_forbids_it(ctx):
    ctx[0].config.feature_harness_attach = True
    deps, server, connectors, project_root = ctx
    opened = _call(
        server,
        "harness_open",
        agent_id="worker",
        kind="claude_code",
        project_root=project_root,
        substrate="attach",
        target_pid=12345,
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
    opened = _call(server, "harness_open", agent_id="worker", kind="pi", project_root=project_root)
    session_id = opened["data"]["session_id"]

    live = _call(server, "harness_get", session_id=session_id)
    assert live["ok"] and live["data"]["live"] is True and live["data"]["status"] == "RUNNING"

    closed = _call(server, "harness_close", session_id=session_id)
    from test_runtime_commands import wait_close_result
    assert closed["ok"]
    assert wait_close_result(server.client, server.operator_key, closed)["lifecycle_state"] == "detached"
    assert connectors["pi"][0].close_called is True

    after = _call(server, "harness_get", session_id=session_id)
    assert after["ok"]
    assert after["data"]["live"] is False
    assert after["data"]["lifecycle_state"] == "detached"

    # Closing a detached fixture is idempotent, without claiming observed exit.
    second = _call(server, "harness_close", session_id=session_id)
    assert second["ok"]


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
    opened = _call(server, "harness_open", agent_id="worker", kind="pi", project_root=project_root)
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


def test_harness_terminal_is_durable_without_unauthorized_broadcast(ctx):
    deps, server, connectors, root = ctx
    opened = _call(server, "harness_open", agent_id="worker", kind="pi", project_root=root)
    session_id = opened["data"]["session_id"]
    connectors["pi"][0].push_event(kind="turn_completed", native_event="agent_settled")
    _wait_until(lambda: _call(server, "harness_event_list", session_id=session_id)["data"]["count"] >= 1)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT * FROM runtime_results WHERE runtime_session_id = ?", (session_id,)).fetchone()
        assert row["publication_state"] == "PENDING_AUTHORIZATION"
        assert uow.connection.execute("SELECT count(*) FROM messages WHERE from_agent_id = ?", ("worker",)).fetchone()[0] == 0


# --------------------------------------------------------------------------- #
# H-1: harness_open backend selection (EV-SYS-002 - no silent ambient inherit)
# --------------------------------------------------------------------------- #
@pytest.fixture
def capturing_ctx(ctx):
    deps, server, connectors, root = ctx
    received = {kind: [] for kind in connectors}
    originals = deps.harness_connector_factories.copy()
    def wrap(kind):
        def build(**kwargs):
            received[kind].append(kwargs.get("backend"))
            return originals[kind](**kwargs)
        return build
    deps.harness_connector_factories.update({kind: wrap(kind) for kind in originals})
    return deps, server, connectors, received, root


@pytest.mark.parametrize("kind", ["pi", "codex"])
def test_harness_open_uses_approved_isolated_profile(capturing_ctx, kind):
    deps, server, _, received, root = capturing_ctx
    result = _call(server, "harness_open", agent_id="worker", kind=kind, project_root=root)
    assert result["ok"], result
    assert result["data"]["backend"] == {"profile_id": "profile-" + kind, "inherit_ambient": False, "revision": 1}
    env = received[kind][0]["env"]
    assert str(deps.config.home_dir) in env["HOME"]
    from okto_nexus.adapters.outbound.harness.environment import child_environment
    assert not any("NEXUS" in key.upper() for key in child_environment(env))
    assert env["CODEX_HOME" if kind == "codex" else "PI_CODING_AGENT_DIR"].startswith(env["HOME"])


@pytest.mark.parametrize("kind,backend", [
    ("pi", {"provider": "zai", "model": "glm-5.3", "extra_args": ["--foo"]}),
    ("codex", {"env": {"CODEX_HOME": "/tmp/unapproved"}}),
])
def test_harness_open_rejects_per_call_profile_override(capturing_ctx, kind, backend):
    _, server, _, received, root = capturing_ctx
    result = _call(server, "harness_open", agent_id="worker", kind=kind, project_root=root, backend=backend)
    assert not result["ok"] and result["error"]["code"] == "VALIDATION_ERROR"
    assert received[kind] == []


def test_harness_open_rejects_backend_field_unsupported_for_kind(capturing_ctx):
    """A backend field the connector cannot actually honour is a
    VALIDATION_ERROR naming the supported set - never a silent drop (the
    exact failure class H-2 catches on the agent_id description)."""
    _deps, server, _connectors, received_backend, project_root = capturing_ctx
    result = _call(
        server,
        "harness_open",
        agent_id="worker",
        kind="codex",
        project_root=project_root,
        backend={"provider": "zai"},
    )
    assert not result["ok"]
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert "approved runtime profile" in result["error"]["message"]
    assert received_backend["codex"] == []


def test_harness_open_rejects_backend_for_claude_code_attach_substrate(capturing_ctx):
    _deps, server, _connectors, received_backend, project_root = capturing_ctx
    result = _call(
        server,
        "harness_open",
        agent_id="worker",
        kind="claude_code",
        project_root=project_root,
        substrate="attach",
        target_pid=12345,
        backend={"env": {"X": "1"}},
    )
    assert not result["ok"]
    assert result["error"]["code"] == "PERMISSION_DENIED"
    assert received_backend["claude_code"] == []


def test_harness_open_rejects_non_object_backend(capturing_ctx):
    _deps, server, _connectors, _received_backend, project_root = capturing_ctx
    result = _call(
        server,
        "harness_open",
        agent_id="worker",
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
        agent_id="worker",
        kind="codex",
        project_root=project_root,
        backend={"env": "not-an-object"},
    )
    assert not result["ok"]
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert "approved runtime profile" in result["error"]["message"]


# --------------------------------------------------------------------------- #
# H-2: shipped tool text must not claim the target grammar reaches a harness
# --------------------------------------------------------------------------- #
def test_harness_open_schema_describes_canonical_identity_and_approved_profile(ctx):
    from test_pr34_remediation import mcp_call
    _, server, _, _ = ctx
    tools = mcp_call(server.client, server.operator_key, "tools/list", {})["tools"]
    schema = next(t for t in tools if t["name"] == "harness_open")["inputSchema"]["properties"]
    assert "Existing canonical agent" in schema["agent_id"]["description"]
    assert "does not create identity" in schema["agent_id"]["description"]
    assert "approved runtime profile" in schema["backend"]["description"]
    assert "broadcast" not in schema["notify_target"]["description"]


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
