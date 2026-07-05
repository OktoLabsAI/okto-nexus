"""Tests for R-I1: trajectory trace_id propagation (spec a9a2c856).

Covers scenarios TS1..TS7 over the REAL bootstrap (migrated temp SQLite home)
through the shared tool registry - the same registration path both the stdio
and HTTP MCP transports mount, plus explicit cross-transport parity via
``create_server`` / ``create_http_mcp_server`` and the REST surface.

Gating contract (decisions D3/D4/D6 of the spec):

* flag ON  - explicit trace validated (1..128 chars), replies inherit the
  parent's trace, otherwise one is generated as ``trc_<32 hex>``; the id is
  persisted on the row, stamped into event payloads and echoed in responses.
* flag OFF - the ``trace_id`` parameter is accepted-and-ignored IN FULL (no
  validation, no persistence, no echo): byte-identical to the pre-I1 surface.
  This is the canonical gating pattern for the whole meta-harness program.
* the flag is read LIVE at the start of each use case: a settings PATCH
  applies to the very next call, no restart.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import re
import shutil

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap, register_tools
from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.migrations import (
    MigrationRunner,
    _default_migrations_dir,
)
from okto_nexus.config import NexusConfig
from okto_nexus.domain.trace import (
    TRACE_ID_MAX_LEN,
    new_trace_id,
    resolve_trace,
    validate_trace_id,
)
from okto_nexus.errors import ErrorCode, OktoNexusError

TRACE_RE = re.compile(r"^trc_[0-9a-f]{32}$")


# --------------------------------------------------------------------------- #
# Harness (the e2e smoke pattern: real bootstrap + shared tool registry)
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


def make_env(tmp_path, *, feature_trace: bool):
    """Real bootstrap in a temp home + two registered agents + a workspace."""
    env = {"OKTO_NEXUS_HOME": str(tmp_path / "home")}
    if feature_trace:
        env["OKTO_NEXUS_FEATURE_TRACE"] = "true"
    deps = bootstrap(env, [])
    server = FakeServer()
    register_tools(server, deps)
    tools = server.tools
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    root = str(project)
    _ok(tools["workspace_resolve"](project_root=root))
    _ok(tools["agent_register"](agent_id="alpha", role="builder"))
    _ok(tools["agent_register"](agent_id="beta", role="reviewer"))
    return deps, tools, root


def _column(deps, table: str, key_col: str, key: str, col: str = "trace_id"):
    conn = deps.connection_factory.get_connection()
    try:
        row = conn.execute(
            f"SELECT {col} FROM {table} WHERE {key_col} = ?", (key,)
        ).fetchone()
        assert row is not None, f"{table} row {key} not found"
        return row[0]
    finally:
        conn.close()


def _message_count(deps) -> int:
    conn = deps.connection_factory.get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    finally:
        conn.close()


def _event_rows(deps) -> list[dict]:
    """The raw append-only event log with decoded payloads (test inspection)."""
    conn = deps.connection_factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT event_id, type, payload FROM events ORDER BY event_id"
        ).fetchall()
        out = []
        for row in rows:
            payload = json.loads(row["payload"]) if row["payload"] else None
            out.append(
                {"event_id": row["event_id"], "type": row["type"], "payload": payload}
            )
        return out
    finally:
        conn.close()


def _events_of(deps, type_: str) -> list[dict]:
    return [e for e in _event_rows(deps) if e["type"] == type_]


def _direct(agent_id: str) -> dict:
    return {"strategy": "direct", "agent_id": agent_id}


# --------------------------------------------------------------------------- #
# Domain: trc_ format + the D3 precedence matrix (backs TS1/TS2)
# --------------------------------------------------------------------------- #
def test_new_trace_id_format_and_uniqueness():
    generated = {new_trace_id() for _ in range(64)}
    assert len(generated) == 64
    for trace in generated:
        assert TRACE_RE.match(trace)


def test_validate_trace_id_bounds():
    assert validate_trace_id("t") == "t"
    assert validate_trace_id("x" * TRACE_ID_MAX_LEN) == "x" * TRACE_ID_MAX_LEN
    for bad in ("", "x" * (TRACE_ID_MAX_LEN + 1)):
        with pytest.raises(OktoNexusError) as ei:
            validate_trace_id(bad)
        assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


def test_resolve_trace_precedence_matrix():
    # OFF: always None, even with explicit/inherited candidates (D4).
    assert resolve_trace(explicit="e", inherited="i", feature_on=False) is None
    assert resolve_trace(explicit=None, inherited=None, feature_on=False) is None
    # ON: explicit > inherited > generated (D3).
    assert resolve_trace(explicit="e", inherited="i", feature_on=True) == "e"
    assert resolve_trace(explicit=None, inherited="i", feature_on=True) == "i"
    assert TRACE_RE.match(resolve_trace(explicit=None, inherited=None, feature_on=True))


# --------------------------------------------------------------------------- #
# TS1 - generation with the flag ON: persistence, stamp and echo (AC1)
# --------------------------------------------------------------------------- #
def test_ts1_generated_trace_persists_stamps_and_echoes(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_trace=True)
    msg = _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="kickoff",
            body="starting",
            target=_direct("beta"),
        )
    )
    trace = msg["trace_id"]
    assert TRACE_RE.match(trace), trace
    # Persisted on the row.
    assert _column(deps, "messages", "message_id", msg["message_id"]) == trace
    # Stamped into the message.created payload.
    created = _events_of(deps, "message.created")
    assert created and created[-1]["payload"]["trace_id"] == trace


# --------------------------------------------------------------------------- #
# TS2 - reply inheritance + explicit precedence (AC2)
# --------------------------------------------------------------------------- #
def test_ts2_reply_inherits_and_explicit_wins(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_trace=True)
    t1 = "trc-parent-t1"
    parent = _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="root",
            body="root",
            target=_direct("beta"),
            trace_id=t1,
        )
    )
    assert parent["trace_id"] == t1

    # (a) reply WITHOUT an explicit trace inherits the parent's.
    reply_a = _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="beta",
            subject="re: root",
            body="ack",
            target=_direct("alpha"),
            parent_message_id=parent["message_id"],
        )
    )
    assert reply_a["trace_id"] == t1
    assert _column(deps, "messages", "message_id", reply_a["message_id"]) == t1
    created = _events_of(deps, "message.created")
    assert created[-1]["payload"]["trace_id"] == t1

    # (b) an explicit divergent trace WINS over the inherited one.
    t2 = "trc-explicit-t2"
    reply_b = _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="beta",
            subject="re: root (fork)",
            body="forking",
            target=_direct("alpha"),
            parent_message_id=parent["message_id"],
            trace_id=t2,
        )
    )
    assert reply_b["trace_id"] == t2
    assert _column(deps, "messages", "message_id", reply_b["message_id"]) == t2
    # The parent keeps ITS trace untouched.
    assert _column(deps, "messages", "message_id", parent["message_id"]) == t1


# --------------------------------------------------------------------------- #
# TS3 - handoff chain: one trace across create->claim->complete + synthetic
# inbox notifications (AC3)
# --------------------------------------------------------------------------- #
def test_ts3_handoff_chain_stamps_one_trace(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_trace=True)
    t = "trc-handoff-chain"
    handoff = _ok(
        tools["handoff_create"](
            project_root=root,
            from_agent_id="alpha",
            target=_direct("beta"),
            visibility="public",
            payload="please take over",
            trace_id=t,
        )
    )
    handoff_id = handoff["handoff_id"]
    assert handoff["trace_id"] == t
    assert _column(deps, "handoffs", "handoff_id", handoff_id) == t

    # Synthetic creation notification to the directed target carries the trace
    # (persisted column + inbox item echo).
    pulled_b = _ok(tools["inbox_pull"](agent_id="beta"))
    notif = [m for m in pulled_b["messages"] if m.get("trace_id") == t]
    assert notif, pulled_b["messages"]
    assert _column(deps, "messages", "message_id", notif[0]["message_id"]) == t

    claimed = _ok(
        tools["handoff_claim"](
            project_root=root, handoff_id=handoff_id, agent_id="beta"
        )
    )
    assert claimed["status"] == "CLAIMED"
    completed = _ok(
        tools["handoff_complete"](
            project_root=root,
            handoff_id=handoff_id,
            agent_id="beta",
            result={"summary": "done"},
        )
    )
    assert completed["status"] == "COMPLETED"

    # Every lifecycle event carries the SAME trace in its payload.
    for type_ in ("handoff.created", "handoff.claimed", "handoff.completed"):
        events = _events_of(deps, type_)
        assert events, f"missing {type_}"
        assert events[-1]["payload"]["trace_id"] == t

    # The outcome notification back to the creator carries the trace too.
    pulled_a = _ok(tools["inbox_pull"](agent_id="alpha"))
    assert any(m.get("trace_id") == t for m in pulled_a["messages"])


# --------------------------------------------------------------------------- #
# TS4 - conditional echo on inbox_pull/peek/history (AC4)
# --------------------------------------------------------------------------- #
def test_ts4_inbox_echo_is_conditional(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_trace=True)
    t = "trc-inbox-echo"
    m1 = _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="traced",
            body="traced body",
            target=_direct("beta"),
            trace_id=t,
        )
    )
    # M2 is created with the flag OFF (live read, D6): no trace persisted -
    # the pre-I1 row shape, exactly like a pre-migration message.
    deps.config.feature_trace = False
    m2 = _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="untraced",
            body="untraced body",
            target=_direct("beta"),
        )
    )
    deps.config.feature_trace = True
    assert _column(deps, "messages", "message_id", m2["message_id"]) is None

    def check(items: list[dict]) -> None:
        by_id = {m["message_id"]: m for m in items}
        assert by_id[m1["message_id"]]["trace_id"] == t
        assert "trace_id" not in by_id[m2["message_id"]]  # key absent, not null
        assert all(m.get("trace_id", "sentinel") is not None for m in items)

    check(_ok(tools["inbox_peek"](agent_id="beta"))["messages"])
    pulled = _ok(tools["inbox_pull"](agent_id="beta"))
    check(pulled["messages"])
    _ok(
        tools["inbox_ack"](
            agent_id="beta",
            message_ids=[m1["message_id"], m2["message_id"]],
        )
    )
    check(_ok(tools["inbox_history"](agent_id="beta"))["messages"])


# --------------------------------------------------------------------------- #
# TS6 - flag OFF byte-identical (D4 accept-and-ignore IN FULL) + validation
# with the flag ON + live toggle via PATCH /settings (AC6/AC7)
# --------------------------------------------------------------------------- #
def test_ts6_flag_off_ignores_everything_then_live_toggle(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_trace=False)

    # (a) a VALID explicit trace is accepted-and-ignored: no echo, no column,
    # no payload key, no inbox key - byte-identical to the pre-I1 surface.
    msg = _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="off",
            body="off body",
            target=_direct("beta"),
            trace_id="trc-ignored",
        )
    )
    assert "trace_id" not in msg
    assert _column(deps, "messages", "message_id", msg["message_id"]) is None
    assert "trace_id" not in _events_of(deps, "message.created")[-1]["payload"]

    handoff = _ok(
        tools["handoff_create"](
            project_root=root,
            from_agent_id="alpha",
            target=_direct("beta"),
            visibility="public",
            payload="off handoff",
            trace_id="trc-ignored",
        )
    )
    assert "trace_id" not in handoff
    assert _column(deps, "handoffs", "handoff_id", handoff["handoff_id"]) is None
    assert "trace_id" not in _events_of(deps, "handoff.created")[-1]["payload"]

    pulled = _ok(tools["inbox_pull"](agent_id="beta"))
    assert pulled["messages"] and all("trace_id" not in m for m in pulled["messages"])

    # (a2) D4 is TOTAL: even a malformed trace is ignored while OFF - the
    # parameter simply does not exist for the gate (no validation either).
    over = _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="off malformed",
            body="still fine",
            target=_direct("beta"),
            trace_id="x" * (TRACE_ID_MAX_LEN + 1),
        )
    )
    assert "trace_id" not in over

    # (c) live toggle: PATCH /settings flips the SAME NexusConfig in place -
    # the very next call already enforces and stamps, no restart.
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app

    assert fastapi is not None
    app = build_app(deps)
    with TestClient(app, client=("127.0.0.1", 50110)) as client:
        response = client.patch("/api/v1/settings", json={"feature_trace": True})
        assert response.status_code == 200
    assert deps.config.feature_trace is True

    # (b) with the flag ON the format gate rejects bad ids WITHOUT persisting.
    count_before = _message_count(deps)
    for bad in ("", "x" * (TRACE_ID_MAX_LEN + 1)):
        env = tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="bad trace",
            body="must not persist",
            target=_direct("beta"),
            trace_id=bad,
        )
        _err(env, ErrorCode.VALIDATION_ERROR.value)
    env = tools["handoff_create"](
        project_root=root,
        from_agent_id="alpha",
        target=_direct("beta"),
        visibility="public",
        payload="bad trace",
        trace_id="",
    )
    _err(env, ErrorCode.VALIDATION_ERROR.value)
    assert _message_count(deps) == count_before

    # The next valid call stamps a generated trace - live-tunable, no restart.
    stamped = _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="on now",
            body="stamped",
            target=_direct("beta"),
        )
    )
    assert TRACE_RE.match(stamped["trace_id"])


# --------------------------------------------------------------------------- #
# TS5 - event_get/event_wait filter by trace with stdio/HTTP parity (AC5)
# --------------------------------------------------------------------------- #
pytest.importorskip("fastapi")
pytest.importorskip("mcp")
from fastapi.testclient import TestClient  # noqa: E402

from okto_nexus.adapters.inbound.http.app import (  # noqa: E402
    build_app,
    create_http_mcp_server,
)
from okto_nexus.adapters.inbound.mcp.server import create_server  # noqa: E402


def _call(server, name: str, arguments: dict | None = None) -> dict:
    result = asyncio.run(server.call_tool(name, arguments or {}))
    if isinstance(result, tuple):
        return result[1]
    return json.loads(result[0].text)


def _build_trajectory(tools, root: str, trace: str) -> None:
    """One full trajectory (message + handoff chain) plus off-trace noise."""
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="alpha",
            subject="trajectory start",
            body="traced",
            target=_direct("beta"),
            trace_id=trace,
        )
    )
    handoff = _ok(
        tools["handoff_create"](
            project_root=root,
            from_agent_id="alpha",
            target=_direct("beta"),
            visibility="public",
            payload="traced handoff",
            trace_id=trace,
        )
    )
    _ok(
        tools["handoff_claim"](
            project_root=root, handoff_id=handoff["handoff_id"], agent_id="beta"
        )
    )
    _ok(
        tools["handoff_complete"](
            project_root=root,
            handoff_id=handoff["handoff_id"],
            agent_id="beta",
            result={"summary": "done"},
        )
    )
    # Noise: a different (generated) trace and an off-trace handoff.
    _ok(
        tools["message_create"](
            project_root=root,
            from_agent_id="beta",
            subject="noise",
            body="other trajectory",
            target=_direct("alpha"),
        )
    )
    _ok(
        tools["handoff_create"](
            project_root=root,
            from_agent_id="beta",
            target={"strategy": "broadcast"},
            visibility="public",
            payload="noise handoff",
        )
    )


def test_ts5_event_filter_by_trace_with_transport_parity(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_trace=True)
    t = "trc-trajectory-t"
    _build_trajectory(tools, root, t)

    stdio = create_server(deps)
    http = create_http_mcp_server(deps)

    for stream, expected_types in (
        ("workspace", {"message.created"}),
        ("handoff", {"handoff.created", "handoff.claimed", "handoff.completed"}),
    ):
        args = {
            "project_root": root,
            "agent_id": "beta",
            "stream": stream,
            "filters": {"trace_id": t},
        }
        stdio_env = _call(stdio, "event_get", args)
        http_env = _call(http, "event_get", args)
        assert stdio_env == http_env  # strict cross-transport parity
        events = _ok(stdio_env)["events"]
        assert events, f"no events for stream {stream}"
        ids = [e["event_id"] for e in events]
        assert ids == sorted(ids)  # ascending event_id order
        assert all(e["trace_id"] == t for e in events)  # top-level exposure
        assert expected_types <= {e["type"] for e in events}

    # event_wait accepts the same filter (events already exist -> immediate).
    waited = _call(
        stdio,
        "event_wait",
        {
            "project_root": root,
            "agent_id": "beta",
            "stream": "handoff",
            "filters": {"trace_id": t},
            "timeout_seconds": 1,
        },
    )
    data = _ok(waited)
    assert data["timed_out"] is False
    assert all(e["trace_id"] == t for e in data["events"])


def test_ts1_parity_message_create_stamps_on_both_transports(tmp_path):
    """TS1 (transport half): the SAME registry serves stdio and HTTP - a
    message created over each transport gets a generated trc_ trace."""
    deps, _, root = make_env(tmp_path, feature_trace=True)
    for server in (create_server(deps), create_http_mcp_server(deps)):
        envelope = _call(
            server,
            "message_create",
            {
                "project_root": root,
                "from_agent_id": "alpha",
                "subject": "parity",
                "body": "parity body",
                "target": _direct("beta"),
            },
        )
        assert TRACE_RE.match(_ok(envelope)["trace_id"])


# --------------------------------------------------------------------------- #
# TS7 - REST timeline + serializers + migration 015 on a populated DB (AC8)
# --------------------------------------------------------------------------- #
def test_ts7_rest_trace_timeline_and_serializers(tmp_path):
    deps, tools, root = make_env(tmp_path, feature_trace=True)
    t = "trc-rest-timeline"
    _build_trajectory(tools, root, t)

    app = build_app(deps)
    with TestClient(app, client=("127.0.0.1", 50111)) as client:
        # (a) the trace timeline, ordered by event_id, only trajectory events.
        data = client.get(f"/api/v1/events?trace={t}").json()["data"]
        items = data["items"]
        assert items and all(e["trace_id"] == t for e in items)
        ids = [e["event_id"] for e in items]
        assert ids == sorted(ids)
        types = {e["type"] for e in items}
        assert {"message.created", "handoff.created", "handoff.completed"} <= types

        # A malformed trace filter is a 422 INVALID_PARAM, not a 500.
        bad = client.get("/api/v1/events?trace=" + "x" * (TRACE_ID_MAX_LEN + 1))
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "INVALID_PARAM"

        # Messages expose trace_id top-level (null on untraced rows).
        messages = client.get("/api/v1/messages").json()["data"]["items"]
        assert messages and all("trace_id" in m for m in messages)
        assert any(m["trace_id"] == t for m in messages)
        assert any(m["trace_id"] != t for m in messages)  # the noise rows

        # Handoffs expose trace_id too.
        handoffs = client.get("/api/v1/handoffs").json()["data"]["items"]
        assert handoffs and all("trace_id" in h for h in handoffs)
        assert any(h["trace_id"] == t for h in handoffs)


def test_ts7_migration_015_idempotent_on_populated_db(tmp_path):
    """Migration half of TS7: 015 lands on a POPULATED pre-015 database,
    preserves the legacy rows as trace_id NULL, and re-running is a no-op."""
    real_dir = _default_migrations_dir()
    partial = tmp_path / "partial"
    partial.mkdir()
    for sql in sorted(real_dir.glob("0*.sql")):
        if not sql.name.startswith("015"):
            shutil.copy(sql, partial)

    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path / "home"))
    applied = MigrationRunner(factory, migrations_dir=partial).apply()
    assert applied and 15 not in applied

    # Populate legacy rows against the pre-015 schema (no trace_id column).
    conn = factory.get_connection()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
        assert "trace_id" not in cols
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO workspaces (workspace_id, created_at)"
            " VALUES ('ws-legacy', '2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO messages (message_id, workspace_id, from_agent_id,"
            " created_at) VALUES ('msg-legacy', 'ws-legacy', 'alpha',"
            " '2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO handoffs (handoff_id, workspace_id, status, created_at)"
            " VALUES ('hof-legacy', 'ws-legacy', 'OPEN', '2026-01-01T00:00:00Z')"
        )
        conn.execute("COMMIT")
    finally:
        conn.close()

    # The full runner applies EXACTLY the pending 015.
    assert MigrationRunner(factory).apply() == [15]

    conn = factory.get_connection()
    try:
        for table in ("messages", "handoffs"):
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            assert "trace_id" in cols, table
        # Legacy rows preserved, reading as trace_id NULL.
        row = conn.execute(
            "SELECT trace_id FROM messages WHERE message_id = 'msg-legacy'"
        ).fetchone()
        assert row is not None and row[0] is None
        row = conn.execute(
            "SELECT trace_id FROM handoffs WHERE handoff_id = 'hof-legacy'"
        ).fetchone()
        assert row is not None and row[0] is None
        # The partial indexes exist.
        indexes = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
        }
        assert {"idx_messages_trace", "idx_handoffs_trace"} <= indexes
    finally:
        conn.close()

    # Idempotent: a second run applies nothing.
    assert MigrationRunner(factory).apply() == []
