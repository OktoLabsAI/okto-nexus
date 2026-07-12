"""Coordination health (spec 7df9b1e0, R-I7) - scenarios TS0..TS8.

Sections map to the Pulse test cards:

* T1/TS0: the PURE domain grammar - windows enum, thresholds lock,
  compute_health purity/determinism, fail-loud unknown window.
* T1/TS1: claimed->completed correlation per handoff_id - exact averages,
  incomplete pairs excluded, exact/null rejection rate, truncated propagated.
* T2/TS2+TS3: fail-closed feature_health gating (live flip, REST immune) and
  the fail-closed window grammar on both surfaces (default 24h).
* T3/TS4+TS5: seeded end-to-end scenario with exact per-metric values and
  workspace scoping; ==threshold is ok / >threshold warns, aggregate status.
* T4/TS6+TS7: tool/REST data parity under the same clock, canonical
  NOT_FOUND/404, pure reads (event log untouched), no-silent-caps
  (lifecycle LIMIT truncation flag + per-agent top 20 with others_unread).
* T5/TS8: surface hygiene - SURFACE_REVISION 24, growth ledger entry,
  exactly [coordination_health] new, budgets, no health resource URI,
  migration 021 index present + idempotent bootstrap.

TS9 is the MANUAL operator click-through of the dashboard section - tracked
on its own Pulse card (T6, on_hold), not automatable here.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json

import pytest

import okto_nexus.domain.health as health_mod
from okto_nexus.adapters.inbound.mcp.resources import resource_uris
from okto_nexus.adapters.inbound.mcp.server import (
    SURFACE_REVISION,
    bootstrap,
    register_tools,
)
from okto_nexus.adapters.inbound.mcp.surface_metrics import APPROVED_GROWTH
from okto_nexus.domain.handoff import (
    EVENT_CLAIMED,
    EVENT_COMPLETED,
    EVENT_CREATED,
    EVENT_REJECTED,
)
from okto_nexus.domain.health import (
    DEFAULT_THRESHOLDS,
    DEFAULT_WINDOW,
    HEALTH_WINDOWS,
    PER_AGENT_TOP,
    REJECTION_MIN_CREATED,
    AgentUnread,
    HandoffLifecycleEvent,
    HealthInputs,
    PresenceCounts,
    UnclaimedHandoff,
    compute_health,
    correlate_claim_to_complete,
    is_valid_window,
)


def _ev(handoff_id: str, event_type: str, at: float) -> HandoffLifecycleEvent:
    return HandoffLifecycleEvent(
        handoff_id=handoff_id, event_type=event_type, created_at_epoch=at
    )


def _mk_inputs(**overrides) -> HealthInputs:
    base = dict(
        workspace_id="ws-under-test",
        window="24h",
        message_count=0,
        event_count=0,
        lifecycle_events=(),
        lifecycle_truncated=False,
        unclaimed=(),
        unread=(),
        presence=PresenceCounts(),
    )
    base.update(overrides)
    return HealthInputs(**base)


# --------------------------------------------------------------------------- #
# T1 / TS0 - pure domain grammar (no I/O; import-boundary keeps the layer)
# --------------------------------------------------------------------------- #
class TestHealthDomainGrammar:
    def test_windows_enum_lock(self):
        assert HEALTH_WINDOWS == {"1h": 3_600, "24h": 86_400, "7d": 604_800}
        assert DEFAULT_WINDOW == "24h"
        for label in ("1h", "24h", "7d"):
            assert is_valid_window(label)
        # Hashable junk only: both surfaces hand this a string (or None).
        for bad in ("30d", "abc", "", "24H", " 24h", None, 3600):
            assert not is_valid_window(bad)

    def test_thresholds_lock(self):
        assert DEFAULT_THRESHOLDS == {
            "unclaimed_handoff_age_seconds": 1800,
            "avg_claim_to_complete_seconds": 3600,
            "rejection_rate": 0.25,
            "per_agent_unread": 25,
            "stale_agents": 0,
        }
        assert REJECTION_MIN_CREATED == 4
        assert PER_AGENT_TOP == 20

    def test_module_is_stdlib_pure(self):
        # test_import_boundary covers the layer; this locks THIS module too.
        src = inspect.getsource(health_mod)
        assert "sqlite3" not in src
        assert "import mcp" not in src and "from mcp" not in src

    def test_compute_health_is_deterministic(self):
        inputs = _mk_inputs(
            message_count=7,
            event_count=12,
            lifecycle_events=(
                _ev("h1", EVENT_CREATED, 1_000.0),
                _ev("h1", EVENT_CLAIMED, 1_100.0),
                _ev("h1", EVENT_COMPLETED, 1_400.0),
                _ev("h2", EVENT_CREATED, 1_200.0),
                _ev("h2", EVENT_REJECTED, 1_250.0),
            ),
            unclaimed=(UnclaimedHandoff(handoff_id="h3", created_at_epoch=9_000.0),),
            unread=(
                AgentUnread(agent_id="alpha", unread=3),
                AgentUnread(agent_id="beta", unread=5),
            ),
            presence=PresenceCounts(present=2, stale=0, offline=1),
        )
        first = compute_health(inputs, now_epoch=10_000.5)
        second = compute_health(inputs, now_epoch=10_000.5)
        assert first == second
        # Same inputs, injected clock also renders generated_at (no ambient
        # clock reads anywhere in the payload).
        assert first["generated_at"] == "1970-01-01T02:46:40.500000Z"
        assert first["workspace_id"] == "ws-under-test"
        assert first["window"] == "24h"
        assert first["window_seconds"] == 86_400
        assert set(first["metrics"]) == {
            "message_volume",
            "event_volume",
            "unclaimed_handoffs",
            "handoff_completion",
            "handoff_rejections",
            "inbox_backlog",
            "agent_presence",
        }

    def test_thresholds_echoed_as_a_copy(self):
        payload = compute_health(_mk_inputs(), now_epoch=1.0)
        assert payload["thresholds"] == DEFAULT_THRESHOLDS
        assert payload["thresholds"] is not DEFAULT_THRESHOLDS
        payload["thresholds"]["rejection_rate"] = 0.99
        assert DEFAULT_THRESHOLDS["rejection_rate"] == 0.25

    def test_unknown_window_fails_loud(self):
        with pytest.raises(ValueError, match="unknown health window"):
            compute_health(_mk_inputs(window="30d"), now_epoch=1.0)


# --------------------------------------------------------------------------- #
# T1 / TS1 - claimed->completed correlation, rejection rate, truncation
# --------------------------------------------------------------------------- #
class TestHandoffCorrelation:
    def test_complete_pairs_exact_average(self):
        events = (
            _ev("h1", EVENT_CLAIMED, 100.0),
            _ev("h1", EVENT_COMPLETED, 400.0),  # 300s
            _ev("h2", EVENT_CLAIMED, 200.0),
            _ev("h2", EVENT_COMPLETED, 250.0),  # 50s
        )
        assert sorted(correlate_claim_to_complete(events)) == [50.0, 300.0]
        payload = compute_health(_mk_inputs(lifecycle_events=events), now_epoch=1_000.0)
        block = payload["metrics"]["handoff_completion"]
        assert block["completed_pairs"] == 2
        assert block["avg_claim_to_complete_seconds"] == 175.0
        assert block["truncated"] is False

    def test_incomplete_pairs_excluded_never_approximated(self):
        events = (
            # Complete pair: the only one that may count.
            _ev("h1", EVENT_CLAIMED, 100.0),
            _ev("h1", EVENT_COMPLETED, 160.0),  # 60s
            # Claimed inside the window, never completed: excluded.
            _ev("h2", EVENT_CLAIMED, 500.0),
            # Completed inside the window, claim fell OUT of it: excluded.
            _ev("h3", EVENT_COMPLETED, 600.0),
            # Claim AFTER the completion instant: no candidate, excluded.
            _ev("h4", EVENT_COMPLETED, 350.0),
            _ev("h4", EVENT_CLAIMED, 400.0),
        )
        assert correlate_claim_to_complete(events) == [60.0]
        block = compute_health(_mk_inputs(lifecycle_events=events), now_epoch=1e3)[
            "metrics"
        ]["handoff_completion"]
        assert block["completed_pairs"] == 1
        assert block["avg_claim_to_complete_seconds"] == 60.0

    def test_reclaim_uses_latest_claim_before_completion(self):
        # Claimed, released, re-claimed: the LAST claim at or before the
        # earliest completion produced it (dec_e7bd8ac7).
        events = (
            _ev("h1", EVENT_CLAIMED, 100.0),
            _ev("h1", EVENT_CLAIMED, 300.0),
            _ev("h1", EVENT_COMPLETED, 350.0),
        )
        assert correlate_claim_to_complete(events) == [50.0]

    def test_no_pairs_yields_null_average_and_ok(self):
        block = compute_health(_mk_inputs(), now_epoch=1.0)["metrics"][
            "handoff_completion"
        ]
        assert block["completed_pairs"] == 0
        assert block["avg_claim_to_complete_seconds"] is None
        assert block["status"] == "ok"

    def test_average_rounds_to_one_decimal(self):
        events = (
            _ev("h1", EVENT_CLAIMED, 0.0),
            _ev("h1", EVENT_COMPLETED, 100.25),
            _ev("h2", EVENT_CLAIMED, 0.0),
            _ev("h2", EVENT_COMPLETED, 100.0),
        )
        block = compute_health(_mk_inputs(lifecycle_events=events), now_epoch=1e3)[
            "metrics"
        ]["handoff_completion"]
        assert block["avg_claim_to_complete_seconds"] == 100.1  # 100.125 -> .1

    def test_rejection_rate_exact_and_rounded(self):
        events = tuple(_ev(f"c{i}", EVENT_CREATED, float(i)) for i in range(8)) + (
            _ev("c0", EVENT_REJECTED, 50.0),
        )
        block = compute_health(_mk_inputs(lifecycle_events=events), now_epoch=1e3)[
            "metrics"
        ]["handoff_rejections"]
        assert (block["created"], block["rejected"]) == (8, 1)
        assert block["rejection_rate"] == 0.125

        # 1/3 rounds to exactly 4 decimals.
        events = (
            _ev("a", EVENT_CREATED, 1.0),
            _ev("b", EVENT_CREATED, 2.0),
            _ev("c", EVENT_CREATED, 3.0),
            _ev("a", EVENT_REJECTED, 4.0),
        )
        block = compute_health(_mk_inputs(lifecycle_events=events), now_epoch=1e3)[
            "metrics"
        ]["handoff_rejections"]
        assert block["rejection_rate"] == 0.3333

    def test_rejection_rate_null_when_nothing_created(self):
        # A stray rejected event without any created in the window still
        # yields a NULL rate (no denominator), never a division error.
        events = (_ev("x", EVENT_REJECTED, 1.0),)
        block = compute_health(_mk_inputs(lifecycle_events=events), now_epoch=1e3)[
            "metrics"
        ]["handoff_rejections"]
        assert (block["created"], block["rejected"]) == (0, 1)
        assert block["rejection_rate"] is None
        assert block["status"] == "ok"

    def test_truncated_input_propagates_to_both_windowed_blocks(self):
        payload = compute_health(_mk_inputs(lifecycle_truncated=True), now_epoch=1e3)
        assert payload["metrics"]["handoff_completion"]["truncated"] is True
        assert payload["metrics"]["handoff_rejections"]["truncated"] is True


# --------------------------------------------------------------------------- #
# Harness (the test_memory.py / test_verification.py shape): the REAL
# bootstrap in a temp home, tools registered through the same path both MCP
# transports mount, three registered agents. feature_health stays OFF by
# default here - the flag's real boot default - so gating tests exercise it.
# --------------------------------------------------------------------------- #
class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            if inspect.iscoroutinefunction(fn):

                @functools.wraps(fn)
                def _sync(*a, **k):
                    return asyncio.run(fn(*a, **k))

                self.tools[fn.__name__] = _sync
            else:
                self.tools[fn.__name__] = fn
            return fn

        return deco


def _ok(env: dict) -> dict:
    assert env["ok"] is True, f"expected ok envelope, got: {env}"
    return env["data"]


def _err(env: dict, code: str) -> dict:
    assert env["ok"] is False, f"expected error envelope, got: {env}"
    assert env["error"]["code"] == code, env["error"]
    return env["error"]


def make_env(tmp_path, *, health: bool = False, extra: dict | None = None):
    """Real bootstrap + alpha/beta/gamma over a temp home."""
    env = {"OKTO_NEXUS_HOME": str(tmp_path / "home")}
    if health:
        env["OKTO_NEXUS_FEATURE_HEALTH"] = "true"
    env.update(extra or {})
    deps = bootstrap(env, [])
    server = FakeServer()
    register_tools(server, deps)
    tools = server.tools
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    root = str(project)
    workspace_id = _ok(tools["workspace_resolve"](project_root=root))["workspace_id"]
    _ok(tools["agent_register"](agent_id="alpha", role="builder"))
    _ok(tools["agent_register"](agent_id="beta", role="executor"))
    _ok(tools["agent_register"](agent_id="gamma", role="reviewer"))
    return deps, tools, root, workspace_id


def _client(deps):
    """Operator-authenticated TestClient over the SAME deps."""
    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
    from okto_nexus.application.auth import AgentKeyAuthService

    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    issued = ensure_operator_key(deps, auth)
    assert issued is not None, "expected the cold-start operator key"
    _, operator_key = issued
    client = TestClient(build_app(deps))
    client.headers.update({"x-api-key": operator_key})
    return client


METRIC_BLOCKS = {
    "message_volume",
    "event_volume",
    "unclaimed_handoffs",
    "handoff_completion",
    "handoff_rejections",
    "inbox_backlog",
    "agent_presence",
}


def _sans_generated_at(data: dict) -> dict:
    """The payload minus the only per-call field (the clock stamp)."""
    return {k: v for k, v in data.items() if k != "generated_at"}


# --------------------------------------------------------------------------- #
# T2 / TS2 - feature_health gating: OFF rejects the tool, live flip, REST
# immune; the tool stays REGISTERED in both flag states (RD1)
# --------------------------------------------------------------------------- #
class TestFeatureGating:
    def test_flag_off_rejects_tool_with_canonical_details(self, tmp_path):
        deps, tools, root, _wid = make_env(tmp_path)  # real boot default: OFF
        assert deps.config.feature_health is False
        assert "coordination_health" in tools  # registered even when OFF
        err = _err(tools["coordination_health"](project_root=root), "VALIDATION_ERROR")
        assert err["details"] == {"feature_health": False}

    def test_flag_flips_live_without_restart(self, tmp_path):
        deps, tools, root, wid = make_env(tmp_path)
        _err(tools["coordination_health"](project_root=root), "VALIDATION_ERROR")
        # The dashboard PATCH /settings, simulated: same process, no restart,
        # no re-registration.
        deps.config.feature_health = True
        data = _ok(tools["coordination_health"](project_root=root))
        assert data["workspace_id"] == wid
        assert data["window"] == "24h"
        assert set(data["metrics"]) == METRIC_BLOCKS
        assert data["thresholds"] == DEFAULT_THRESHOLDS
        # Live in BOTH directions.
        deps.config.feature_health = False
        err = _err(tools["coordination_health"](project_root=root), "VALIDATION_ERROR")
        assert err["details"] == {"feature_health": False}

    def test_flag_on_at_boot_registers_and_serves(self, tmp_path):
        _deps, tools, root, wid = make_env(tmp_path, health=True)
        assert "coordination_health" in tools
        assert (
            _ok(tools["coordination_health"](project_root=root))["workspace_id"] == wid
        )

    def test_rest_read_is_immune_to_the_flag(self, tmp_path):
        deps, _tools, _root, wid = make_env(tmp_path)  # flag OFF
        client = _client(deps)
        r_off = client.get(f"/api/v1/workspaces/{wid}/health")
        assert r_off.status_code == 200, r_off.text
        deps.config.feature_health = True
        r_on = client.get(f"/api/v1/workspaces/{wid}/health")
        assert r_on.status_code == 200, r_on.text
        # Same data in both flag states (generated_at is the clock stamp).
        assert _sans_generated_at(r_off.json()["data"]) == _sans_generated_at(
            r_on.json()["data"]
        )


# --------------------------------------------------------------------------- #
# T2 / TS3 - fail-closed window grammar on BOTH surfaces, default 24h
# --------------------------------------------------------------------------- #
class TestWindowGrammar:
    def test_tool_rejects_unknown_windows_fail_closed(self, tmp_path):
        _deps, tools, root, _wid = make_env(tmp_path, health=True)
        for bad in ("30d", "abc"):
            err = _err(
                tools["coordination_health"](project_root=root, window=bad),
                "VALIDATION_ERROR",
            )
            assert err["details"] == {"window": bad, "allowed": ["1h", "24h", "7d"]}

    def test_tool_defaults_absent_or_blank_to_24h(self, tmp_path):
        _deps, tools, root, _wid = make_env(tmp_path, health=True)
        health = tools["coordination_health"]
        for env in (
            health(project_root=root),
            health(project_root=root, window=None),
            health(project_root=root, window=""),
            health(project_root=root, window="   "),
        ):
            data = _ok(env)
            assert data["window"] == "24h"
            assert data["window_seconds"] == 86_400

    def test_rest_rejects_unknown_windows_with_400(self, tmp_path):
        deps, _tools, _root, wid = make_env(tmp_path, health=True)
        client = _client(deps)
        for bad in ("30d", "abc"):
            r = client.get(f"/api/v1/workspaces/{wid}/health", params={"window": bad})
            assert r.status_code == 400, r.text
            err = r.json()["error"]
            assert err["code"] == "INVALID_WINDOW"
            assert "window must be one of 1h, 24h, 7d" in err["message"]

    def test_rest_defaults_absent_window_to_24h_and_honours_valid_labels(
        self, tmp_path
    ):
        deps, _tools, _root, wid = make_env(tmp_path, health=True)
        client = _client(deps)
        r = client.get(f"/api/v1/workspaces/{wid}/health")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["window"] == "24h"
        assert data["window_seconds"] == 86_400
        # Valid explicit labels pass through unchanged - never coerced.
        for label, seconds in (("1h", 3_600), ("7d", 604_800)):
            r = client.get(f"/api/v1/workspaces/{wid}/health", params={"window": label})
            assert r.status_code == 200, r.text
            assert r.json()["data"]["window"] == label
            assert r.json()["data"]["window_seconds"] == seconds


# --------------------------------------------------------------------------- #
# T3 / TS4 - seeded end-to-end scenario: exact per-metric values, workspace
# scoping, 1h vs 7d windows, presence via classify_presence
# --------------------------------------------------------------------------- #
def _iso(epoch: float) -> str:
    from datetime import datetime, timezone

    return (
        datetime.fromtimestamp(epoch, timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _install_clock(deps, start_epoch: float) -> dict:
    """Take over the SHARED SystemClock instance.

    Every repo and service holds a reference to this exact object, so
    instance-level method overrides steer ALL timestamps - seeding writes and
    the health read alike (iso and epoch move together, unlike the conftest
    FakeClock whose two faces are independent).
    """
    state = {"epoch": float(start_epoch)}
    deps.clock.now_epoch = lambda: state["epoch"]
    deps.clock.now_iso = lambda: _iso(state["epoch"])
    return state


def _sql_event_count(deps, workspace_id: str, since_iso: str) -> int:
    """An INDEPENDENT count over the events table (not the repo's query)."""
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM events WHERE workspace_id = ? AND created_at >= ?",
            (workspace_id, since_iso),
        ).fetchone()[0]
    finally:
        conn.close()


def _sql_message_count(deps, workspace_id: str, since_iso: str) -> int:
    """Independent windowed message count (the metric's other code path)."""
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM messages WHERE workspace_id = ? AND created_at >= ?",
            (workspace_id, since_iso),
        ).fetchone()[0]
    finally:
        conn.close()


def _sql_unread_by_agent(deps, workspace_id: str) -> list[dict]:
    """Independent per-agent unread breakdown (deliveries JOIN messages).

    Deliberately NOT the repo query object - a hand-written parallel over the
    same tables, so asserting the metric equals this proves the service carries
    the workspace-scoped aggregation through faithfully (order included).
    """
    conn = deps.connection_factory.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT d.recipient_agent_id AS agent_id, COUNT(*) AS n
            FROM message_deliveries d
            JOIN messages m ON m.message_id = d.message_id
            WHERE m.workspace_id = ? AND d.status = 'unread'
            GROUP BY d.recipient_agent_id
            ORDER BY n DESC, d.recipient_agent_id
            """,
            (workspace_id,),
        ).fetchall()
        return [{"agent_id": r["agent_id"], "unread": int(r["n"])} for r in rows]
    finally:
        conn.close()


def _direct(agent_id: str) -> dict:
    return {"strategy": "direct", "agent_id": agent_id}


# All seeded instants sit AFTER the real wall clock that stamped make_env's
# own bootstrap writes, so everything make_env created naturally falls OUT of
# every window at T_READ.
BASE = 1_800_000_000.0
T_READ = BASE + 800_000.0


def test_ts4_seeded_scenario_exact_values_and_scoping(tmp_path):
    # The seeded claim->complete gaps (300s and 3000s) must outlive the claim
    # lease (default 300s), or the handoffs silently reopen before completing.
    deps, tools, root, wid = make_env(
        tmp_path,
        health=True,
        extra={"OKTO_NEXUS_HANDOFF_LEASE_TTL_SECONDS": "36000"},
    )
    # A SECOND workspace whose activity must never leak into the target's.
    project2 = tmp_path / "project2"
    project2.mkdir()
    root2 = str(project2)
    _ok(tools["workspace_resolve"](project_root=root2))

    clk = _install_clock(deps, BASE)

    def _at(epoch: float, fn, **kwargs) -> dict:
        clk["epoch"] = epoch
        return _ok(fn(**kwargs))

    # @BASE (outside even the 7d window at T_READ): an old unread message in
    # the target (the SNAPSHOT backlog counts it; the WINDOWED volume must
    # not), the other workspace's message, and gamma's long-closed session.
    _at(
        BASE,
        tools["message_create"],
        project_root=root,
        from_agent_id="alpha",
        subject="old",
        body="outside every window",
        target=_direct("beta"),
    )
    _at(
        BASE,
        tools["message_create"],
        project_root=root2,
        from_agent_id="alpha",
        subject="other-ws",
        body="must never count in the target",
        target=_direct("beta"),
    )
    gamma_session = _at(BASE, tools["session_open"], agent_id="gamma", workspace_id=wid)
    _at(BASE, tools["session_close"], session_id=gamma_session["session_id"])

    # Inside 7d only (outside 24h/1h): one message to gamma.
    _at(
        T_READ - 100_000,
        tools["message_create"],
        project_root=root,
        from_agent_id="alpha",
        subject="7d",
        body="inside 7d only",
        target=_direct("gamma"),
    )

    # h_edge: claimed OUTSIDE the 1h window, completed inside it - a complete
    # pair for 7d (3000s), an INCOMPLETE one for 1h.
    h_edge = _at(
        T_READ - 5_100,
        tools["handoff_create"],
        project_root=root,
        from_agent_id="alpha",
        target=_direct("beta"),
        visibility="public",
        payload="edge",
    )["handoff_id"]
    _at(
        T_READ - 5_000,
        tools["handoff_claim"],
        project_root=root,
        handoff_id=h_edge,
        agent_id="beta",
    )
    # h_pair: fully inside 1h - claimed->completed in exactly 300s.
    h_pair = _at(
        T_READ - 3_000,
        tools["handoff_create"],
        project_root=root,
        from_agent_id="alpha",
        target=_direct("beta"),
        visibility="public",
        payload="pair",
    )["handoff_id"]
    h_rej = _at(
        T_READ - 2_600,
        tools["handoff_create"],
        project_root=root,
        from_agent_id="alpha",
        target=_direct("beta"),
        visibility="public",
        payload="reject-me",
    )["handoff_id"]
    _at(
        T_READ - 2_500,
        tools["handoff_claim"],
        project_root=root,
        handoff_id=h_pair,
        agent_id="beta",
    )
    _at(
        T_READ - 2_400,
        tools["handoff_reject"],
        project_root=root,
        handoff_id=h_rej,
        agent_id="beta",
        reason="busy",
    )
    _at(
        T_READ - 2_200,
        tools["handoff_complete"],
        project_root=root,
        handoff_id=h_pair,
        agent_id="beta",
        result={"ok": True},
    )
    _at(
        T_READ - 2_000,
        tools["handoff_complete"],
        project_root=root,
        handoff_id=h_edge,
        agent_id="beta",
        result={"ok": True},
    )
    _at(
        T_READ - 1_800,
        tools["message_create"],
        project_root=root,
        from_agent_id="alpha",
        subject="m1",
        body="inside 1h",
        target=_direct("beta"),
    )
    # Two OPEN unclaimed handoffs (broadcast: no synthetic notification).
    _at(
        T_READ - 1_000,
        tools["handoff_create"],
        project_root=root,
        from_agent_id="alpha",
        target={"strategy": "broadcast"},
        visibility="public",
        payload="open-a",
    )
    # h_inc: claimed inside 1h, never completed - excluded from the average.
    h_inc = _at(
        T_READ - 800,
        tools["handoff_create"],
        project_root=root,
        from_agent_id="alpha",
        target=_direct("beta"),
        visibility="public",
        payload="incomplete",
    )["handoff_id"]
    _at(
        T_READ - 700,
        tools["handoff_claim"],
        project_root=root,
        handoff_id=h_inc,
        agent_id="beta",
    )
    # beta's freshest signal (session heartbeat + last_seen via the claim)
    # is now 700s old at T_READ: stale (60 <= 700 < 1800).
    _at(T_READ - 700, tools["session_open"], agent_id="beta", workspace_id=wid)
    _at(
        T_READ - 500,
        tools["handoff_create"],
        project_root=root,
        from_agent_id="alpha",
        target={"strategy": "broadcast"},
        visibility="public",
        payload="open-b",
    )
    _at(
        T_READ - 400,
        tools["message_create"],
        project_root=root,
        from_agent_id="alpha",
        subject="m2",
        body="inside 1h too",
        target=_direct("beta"),
    )
    # alpha's heartbeat is 30s old at T_READ: present (< 60).
    _at(T_READ - 30, tools["session_open"], agent_id="alpha", workspace_id=wid)

    clk["epoch"] = T_READ
    h1 = _ok(tools["coordination_health"](project_root=root, window="1h"))
    h7 = _ok(tools["coordination_health"](project_root=root, window="7d"))
    m1, m7 = h1["metrics"], h7["metrics"]

    # Windowed volumes: exact against an INDEPENDENT recomputation (messages
    # and events both include synthetic handoff notifications, so the value is
    # asserted from the DB rather than hand-enumerated). The windowing itself
    # is proved by 1h < 7d and by the @BASE items falling out of even 7d.
    since_1h, since_7d = _iso(T_READ - 3_600), _iso(T_READ - 604_800)
    assert m1["message_volume"]["scope"] == "windowed"
    assert m1["message_volume"]["count"] == _sql_message_count(deps, wid, since_1h)
    assert m7["message_volume"]["count"] == _sql_message_count(deps, wid, since_7d)
    assert m1["message_volume"]["count"] < m7["message_volume"]["count"]
    # The @BASE message ('old') sits outside even the 7d window.
    assert _sql_message_count(deps, wid, _iso(0.0)) > m7["message_volume"]["count"]
    assert m1["event_volume"]["count"] == _sql_event_count(deps, wid, since_1h)
    assert m7["event_volume"]["count"] == _sql_event_count(deps, wid, since_7d)
    assert m1["event_volume"]["count"] < m7["event_volume"]["count"]
    # Bootstrap-era events exist but sit outside even the 7d window.
    assert _sql_event_count(deps, wid, _iso(0.0)) > m7["event_volume"]["count"]

    # Unclaimed handoffs: SNAPSHOT - identical across windows; the REJECTED,
    # CLAIMED and COMPLETED ones never show up.
    for m in (m1, m7):
        block = m["unclaimed_handoffs"]
        assert block["scope"] == "snapshot"
        assert block["count"] == 2
        assert block["oldest_age_seconds"] == 1_000.0
        assert block["status"] == "ok"  # 1000 <= 1800

    # Claim->complete: the window MOVES the correlation. 1h sees only the
    # 300s pair (h_edge's claim fell out); 7d sees both (300s + 3000s).
    assert m1["handoff_completion"]["completed_pairs"] == 1
    assert m1["handoff_completion"]["avg_claim_to_complete_seconds"] == 300.0
    assert m7["handoff_completion"]["completed_pairs"] == 2
    assert m7["handoff_completion"]["avg_claim_to_complete_seconds"] == 1_650.0
    for m in (m1, m7):
        assert m["handoff_completion"]["status"] == "ok"
        assert m["handoff_completion"]["truncated"] is False

    # Rejections: exact windowed counts and rate.
    assert m1["handoff_rejections"]["created"] == 5
    assert m1["handoff_rejections"]["rejected"] == 1
    assert m1["handoff_rejections"]["rejection_rate"] == 0.2
    assert m1["handoff_rejections"]["status"] == "ok"  # 0.2 <= 0.25, sample 5
    assert m7["handoff_rejections"]["created"] == 6
    assert m7["handoff_rejections"]["rejection_rate"] == 0.1667  # round(1/6, 4)

    # Inbox backlog: SNAPSHOT (identical across windows) - beta holds the
    # directed sends + directed-handoff notifications, alpha holds the
    # creator-outcome notifications, gamma holds the 7d message. Exact
    # per-agent breakdown asserted against the independent recomputation; the
    # other workspace's delivery for beta is EXCLUDED (its message is in ws2).
    expected_unread = _sql_unread_by_agent(deps, wid)
    assert expected_unread[0]["agent_id"] == "beta"  # most unread ranks first
    assert {row["agent_id"] for row in expected_unread} == {"alpha", "beta", "gamma"}
    for m in (m1, m7):
        backlog = m["inbox_backlog"]
        assert backlog["scope"] == "snapshot"
        assert backlog["per_agent"] == expected_unread  # order preserved
        assert backlog["total_unread"] == sum(r["unread"] for r in expected_unread)
        assert backlog["others_unread"] == 0  # < 20 agents, nothing folds
        assert backlog["status"] == "ok"  # max unread <= 25

    # Presence via classify_presence: alpha present (30s), beta stale (700s),
    # gamma offline (~800k s) - and ONE stale agent warns the aggregate.
    for m in (m1, m7):
        pres = m["agent_presence"]
        assert (pres["present"], pres["stale"], pres["offline"]) == (1, 1, 1)
        assert pres["status"] == "warn"  # 1 stale > threshold 0
    assert h1["status"] == "warn" and h7["status"] == "warn"

    # The second workspace sees ONLY its own activity: its lone delivery is
    # unread (snapshot) while its 7d message volume is zero (sent @BASE).
    other = _ok(tools["coordination_health"](project_root=root2, window="7d"))
    assert other["metrics"]["message_volume"]["count"] == 0
    assert other["metrics"]["inbox_backlog"]["total_unread"] == 1
    assert other["metrics"]["inbox_backlog"]["per_agent"] == [
        {"agent_id": "beta", "unread": 1}
    ]
    assert other["metrics"]["unclaimed_handoffs"]["count"] == 0
    assert other["status"] == "ok"


# --------------------------------------------------------------------------- #
# T3 / TS5 - exact threshold boundaries: ==threshold ok, >threshold warn,
# min-sample guard, aggregate status
# --------------------------------------------------------------------------- #
class TestThresholdBoundaries:
    NOW = 100_000.0

    def _one(self, **overrides) -> dict:
        return compute_health(_mk_inputs(**overrides), now_epoch=self.NOW)

    def test_unclaimed_age_boundary(self):
        def aged(age: float):
            return (UnclaimedHandoff(handoff_id="h", created_at_epoch=self.NOW - age),)

        ok = self._one(unclaimed=aged(1_800.0))["metrics"]["unclaimed_handoffs"]
        warn = self._one(unclaimed=aged(1_801.0))["metrics"]["unclaimed_handoffs"]
        assert ok["oldest_age_seconds"] == 1_800.0 and ok["status"] == "ok"
        assert warn["oldest_age_seconds"] == 1_801.0 and warn["status"] == "warn"

    def test_avg_claim_to_complete_boundary(self):
        def pair(duration: float):
            return (
                _ev("h", EVENT_CLAIMED, 0.0),
                _ev("h", EVENT_COMPLETED, duration),
            )

        ok = self._one(lifecycle_events=pair(3_600.0))["metrics"]["handoff_completion"]
        warn = self._one(lifecycle_events=pair(3_601.0))["metrics"][
            "handoff_completion"
        ]
        assert ok["avg_claim_to_complete_seconds"] == 3_600.0
        assert ok["status"] == "ok"
        assert warn["status"] == "warn"

    def test_rejection_boundary_and_min_sample_guard(self):
        def mix(created: int, rejected: int):
            evs = [_ev(f"c{i}", EVENT_CREATED, float(i)) for i in range(created)]
            evs += [_ev(f"c{i}", EVENT_REJECTED, 100.0 + i) for i in range(rejected)]
            return tuple(evs)

        at_thr = self._one(lifecycle_events=mix(4, 1))["metrics"]["handoff_rejections"]
        assert at_thr["rejection_rate"] == 0.25 and at_thr["status"] == "ok"
        above = self._one(lifecycle_events=mix(4, 2))["metrics"]["handoff_rejections"]
        assert above["rejection_rate"] == 0.5 and above["status"] == "warn"
        # Above the threshold but below the min sample: NEVER a warn.
        small = self._one(lifecycle_events=mix(3, 1))["metrics"]["handoff_rejections"]
        assert small["rejection_rate"] == 0.3333 and small["status"] == "ok"
        tiny = self._one(lifecycle_events=mix(3, 3))["metrics"]["handoff_rejections"]
        assert tiny["rejection_rate"] == 1.0 and tiny["status"] == "ok"

    def test_per_agent_unread_boundary_is_the_max_not_the_total(self):
        ok = self._one(unread=(AgentUnread("a", 25),))["metrics"]["inbox_backlog"]
        warn = self._one(unread=(AgentUnread("a", 26),))["metrics"]["inbox_backlog"]
        assert ok["status"] == "ok" and warn["status"] == "warn"
        spread = self._one(unread=(AgentUnread("a", 25), AgentUnread("b", 25)))[
            "metrics"
        ]["inbox_backlog"]
        assert spread["total_unread"] == 50 and spread["status"] == "ok"

    def test_stale_boundary_offline_never_warns(self):
        ok = self._one(presence=PresenceCounts(present=0, stale=0, offline=50))[
            "metrics"
        ]["agent_presence"]
        warn = self._one(presence=PresenceCounts(present=3, stale=1, offline=0))[
            "metrics"
        ]["agent_presence"]
        assert ok["status"] == "ok" and warn["status"] == "warn"

    def test_volumes_are_informational_never_warn(self):
        payload = self._one(message_count=10**9, event_count=10**9)
        assert payload["metrics"]["message_volume"]["status"] == "ok"
        assert payload["metrics"]["event_volume"]["status"] == "ok"

    def test_aggregate_status_warn_iff_any_metric_warns(self):
        assert self._one()["status"] == "ok"
        assert self._one(presence=PresenceCounts(stale=1))["status"] == "warn"
        many = self._one(
            presence=PresenceCounts(stale=2),
            unread=(AgentUnread("a", 99),),
            unclaimed=(
                UnclaimedHandoff(handoff_id="h", created_at_epoch=self.NOW - 9_999.0),
            ),
        )
        assert many["status"] == "warn"


def _all_events(deps) -> list[tuple]:
    """A stable snapshot of the ENTIRE event log (BR4 invariance probe)."""
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(
            "SELECT event_id, workspace_id, type, payload, created_at "
            "FROM events ORDER BY event_id"
        ).fetchall()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# T4 / TS6 - tool/REST data parity, canonical NOT_FOUND/404, pure reads (BR4)
# --------------------------------------------------------------------------- #
def test_ts6_tool_rest_parity_errors_and_pure_reads(tmp_path):
    deps, tools, root, wid = make_env(
        tmp_path,
        health=True,
        extra={"OKTO_NEXUS_HANDOFF_LEASE_TTL_SECONDS": "36000"},
    )
    clk = _install_clock(deps, BASE)

    def _at(epoch: float, fn, **kwargs) -> dict:
        clk["epoch"] = epoch
        return _ok(fn(**kwargs))

    # A little varied activity so the payload is non-trivial.
    _at(
        T_READ - 1_500,
        tools["message_create"],
        project_root=root,
        from_agent_id="alpha",
        subject="s",
        body="b",
        target=_direct("beta"),
    )
    h = _at(
        T_READ - 1_200,
        tools["handoff_create"],
        project_root=root,
        from_agent_id="alpha",
        target=_direct("beta"),
        visibility="public",
        payload="p",
    )["handoff_id"]
    _at(
        T_READ - 1_000,
        tools["handoff_claim"],
        project_root=root,
        handoff_id=h,
        agent_id="beta",
    )
    _at(
        T_READ - 800,
        tools["handoff_complete"],
        project_root=root,
        handoff_id=h,
        agent_id="beta",
        result={"ok": True},
    )
    _at(T_READ - 40, tools["session_open"], agent_id="alpha", workspace_id=wid)

    client = _client(deps)

    # Freeze the clock: both surfaces read the SAME now_epoch, so even
    # generated_at matches - full byte-identity, not merely sans-timestamp.
    clk["epoch"] = T_READ
    for window in ("1h", "24h", "7d"):
        tool_data = _ok(tools["coordination_health"](project_root=root, window=window))
        r = client.get(f"/api/v1/workspaces/{wid}/health", params={"window": window})
        assert r.status_code == 200, r.text
        rest_data = r.json()["data"]
        assert json.dumps(tool_data, sort_keys=True) == json.dumps(
            rest_data, sort_keys=True
        ), window
        # generated_at included in the identity above (frozen clock).
        assert tool_data["generated_at"] == rest_data["generated_at"]

    # Ghost workspace: canonical NOT_FOUND (tool) / 404 (REST). The dir must
    # EXIST (else the tool short-circuits on WORKSPACE_UNRESOLVED) but is
    # never workspace_resolve'd, so its hash is unknown to the store.
    ghost_dir = tmp_path / "ghost"
    ghost_dir.mkdir()
    ghost = tools["coordination_health"](project_root=str(ghost_dir))
    err = _err(ghost, "NOT_FOUND")
    assert "workspace_id" in err["details"]
    r = client.get("/api/v1/workspaces/deadbeefdeadbeef/health")
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"

    # BR4 - a health report is a PURE read: N calls across BOTH surfaces emit
    # NO events (the log is byte-identical before and after).
    before = _all_events(deps)
    for _ in range(3):
        _ok(tools["coordination_health"](project_root=root, window="24h"))
        assert client.get(f"/api/v1/workspaces/{wid}/health").status_code == 200
    after = _all_events(deps)
    assert [tuple(r) for r in before] == [tuple(r) for r in after]


# --------------------------------------------------------------------------- #
# T4 / TS7 - no-silent-caps: lifecycle LIMIT truncation flag + per-agent
# top-20 with others_unread folding the remainder (nothing silently dropped)
# --------------------------------------------------------------------------- #
def test_ts7_lifecycle_truncation_flag(tmp_path, monkeypatch):
    # Lower the LIMIT instead of seeding 5001 events. The constant is a module
    # global read at query time, so patching it steers the cap live.
    import okto_nexus.adapters.outbound.sqlite.observability_repo as obs_repo

    monkeypatch.setattr(obs_repo, "MAX_LIFECYCLE_EVENTS", 2)

    deps, tools, root, _wid = make_env(tmp_path, health=True)
    clk = _install_clock(deps, BASE)
    # Three handoff.created events in the window > the patched LIMIT of 2.
    for i in range(3):
        clk["epoch"] = T_READ - 500 + i
        _ok(
            tools["handoff_create"](
                project_root=root,
                from_agent_id="alpha",
                target={"strategy": "broadcast"},
                visibility="public",
                payload=f"h{i}",
            )
        )
    clk["epoch"] = T_READ
    metrics = _ok(tools["coordination_health"](project_root=root, window="24h"))[
        "metrics"
    ]
    # The flag surfaces on BOTH windowed handoff blocks - the operator sees
    # the numbers are a sample, never a silent cap.
    assert metrics["handoff_completion"]["truncated"] is True
    assert metrics["handoff_rejections"]["truncated"] is True


def test_ts7_per_agent_top_20_and_others_unread(tmp_path):
    deps, tools, root, wid = make_env(tmp_path, health=True)
    # 22 recipients with DISTINCT unread counts 1..22 (min-sum distinct set):
    # agent u{k} receives k+1 messages, so the top-20 cut is unambiguous.
    recipients = [f"u{k:02d}" for k in range(22)]
    for aid in recipients:
        _ok(tools["agent_register"](agent_id=aid, role="worker"))
    for k, aid in enumerate(recipients):
        for _ in range(k + 1):  # counts 1..22
            _ok(
                tools["message_create"](
                    project_root=root,
                    from_agent_id="alpha",
                    subject="x",
                    body="y",
                    target=_direct(aid),
                )
            )

    backlog = _ok(tools["coordination_health"](project_root=root, window="24h"))[
        "metrics"
    ]["inbox_backlog"]

    # Top-20 by unread DESC: counts 22..3 (agents u21..u02).
    assert len(backlog["per_agent"]) == PER_AGENT_TOP == 20
    assert [row["unread"] for row in backlog["per_agent"]] == list(range(22, 2, -1))
    assert backlog["per_agent"][0]["agent_id"] == "u21"
    # The 2 folded agents (counts 2 and 1) land in others_unread, not dropped.
    assert backlog["others_unread"] == 1 + 2
    # total_unread preserves the FULL sum - nothing silently vanishes.
    assert backlog["total_unread"] == sum(range(1, 23)) == 253
    assert backlog["total_unread"] == _sql_message_total_unread(deps, wid)


def _sql_message_total_unread(deps, workspace_id: str) -> int:
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute(
            """
            SELECT COUNT(*) FROM message_deliveries d
            JOIN messages m ON m.message_id = d.message_id
            WHERE m.workspace_id = ? AND d.status = 'unread'
            """,
            (workspace_id,),
        ).fetchone()[0]
    finally:
        conn.close()


def _has_index(deps, table: str, name: str) -> bool:
    conn = deps.connection_factory.get_connection()
    try:
        rows = conn.execute(f"PRAGMA index_list('{table}')").fetchall()
        return any(row["name"] == name for row in rows)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# T5 / TS8 - frozen MCP surface contract + migration 021 index & idempotency
# --------------------------------------------------------------------------- #
def test_ts8_surface_revision_ledger_and_budgets(tmp_path):
    assert SURFACE_REVISION == 31
    # The growth is ON the approved ledger (AC5 reduction test stays green with
    # it counted).
    assert APPROVED_GROWTH["health_i7"] > 0

    _deps, tools, _root, _wid = make_env(tmp_path, health=True)
    # EXACTLY one new tool from this slice; no health/coordination sibling
    # leaked onto the surface.
    assert "coordination_health" in tools
    assert sorted(n for n in tools if "coordination" in n) == ["coordination_health"]

    # The slice's composition root contributes exactly ONE @server.tool.
    import okto_nexus.adapters.inbound.mcp.tools.health as health_module

    solo = FakeServer()
    health_module.register(solo, _deps)
    assert sorted(solo.tools) == ["coordination_health"]

    # Inline docstring within the house budget (<=200 chars, single-line).
    doc = inspect.getdoc(tools["coordination_health"])
    assert doc and "\n" not in doc and len(doc) <= 200, len(doc or "")
    # Every _P_* parameter description: single-line, <=200 chars (AC9).
    for name, value in vars(health_module).items():
        if name.startswith("_P_"):
            assert isinstance(value, str) and "\n" not in value, name
            assert len(value) <= 200, f"{name} budget: {len(value)}"

    # No reference resource carries "health" - the inline description is
    # self-sufficient (mirrors the I6 memory decision; a URI later is a bump).
    assert not any("health" in uri for uri in resource_uris())


def test_ts8_migration_021_index_present_and_idempotent(tmp_path):
    home = {"OKTO_NEXUS_HOME": str(tmp_path / "home")}
    # Cold start on an EMPTY home: migration 021 lands the composite index the
    # windowed event scan rides on.
    deps1 = bootstrap(home, [])
    assert _has_index(deps1, "events", "idx_events_workspace_created")
    # Re-bootstrap the SAME (pre-existing) home: migrations re-run clean and
    # the index (CREATE INDEX IF NOT EXISTS) is still present - idempotent.
    deps2 = bootstrap(home, [])
    assert _has_index(deps2, "events", "idx_events_workspace_created")
