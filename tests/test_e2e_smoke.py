"""End-to-end smoke test for the fully wired Okto Nexus MCP server.

Exercises a realistic multi-slice flow over the REAL bootstrap (real migrated
SQLite store in a temp home, real ``WorkspaceFileStore``, real
``SqliteEventEmitter``) through the canonical tool envelopes:

    workspace_resolve -> agent_register -> session_open
      -> message_create (emits message.created)
      -> handoff_create (emits handoff.created)
      -> event_get / event_wait observe the handoff event on the "handoff" stream
      -> handoff_claim -> handoff_complete
      -> artifact_put (inline text < 64KB) + artifact_put (path ref)
      -> artifact_get
      -> shared_md_render writes {home}/workspaces/{ws}/shared.md

Every step asserts the ``{"ok": true, "data": ...}`` envelope and the append
only event log is checked directly. This is the integration-level proof that
``bootstrap()`` wires every repo + the event emitter and that tool
auto-discovery registers every tool against a single coherent backing store.

Note on streams: ``event_get``/``event_wait`` are scoped to the coordination
streams (``workspace``/``agent``/``task``/``handoff``). ``handoff.created`` is
observed on the ``handoff`` stream; ``message.created`` and ``artifact.created``
are PUBLISHED on the ``workspace`` stream (the base observable stream of the
whole workspace) and are observed there via ``event_get``/``event_wait`` - in
addition to being verified directly against the append-only log.
"""

from __future__ import annotations

import os

from okto_nexus.adapters.inbound.mcp.server import bootstrap, register_tools


class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _event_rows(deps) -> list[dict]:
    """Read the raw append-only event log directly (test-only inspection)."""
    conn = deps.connection_factory.get_connection()
    try:
        rows = conn.execute(
            "SELECT event_id, stream, type FROM events ORDER BY event_id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _ok(env: dict) -> dict:
    assert env["ok"] is True, f"expected ok envelope, got: {env}"
    return env["data"]


def test_e2e_full_flow(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    project_root = str(project)

    # --- Wire the whole server through the real bootstrap. ----------------- #
    deps = bootstrap({"OKTO_NEXUS_HOME": str(home)}, [])
    server = FakeServer()
    registered = register_tools(server, deps)
    assert registered, "no tool modules registered"

    tools = server.tools
    expected = {
        "workspace_resolve", "agent_register", "session_open", "session_heartbeat",
        "event_get", "event_wait",
        "message_create", "channel_create", "channel_list",
        "inbox_pull", "inbox_ack", "inbox_peek", "inbox_count", "inbox_history",
        "handoff_create", "handoff_list_available", "handoff_claim",
        "handoff_complete", "handoff_reject",
        "artifact_put", "artifact_get",
        "shared_md_render",
    }
    assert expected <= set(tools), f"missing tools: {expected - set(tools)}"

    # Every repo + the emitter must be populated by bootstrap (not lazily).
    for field in (
        "workspaces", "agents", "sessions", "events", "channels",
        "messages", "tasks", "handoffs", "artifacts", "files",
    ):
        assert getattr(deps.repos, field) is not None, f"repo {field} not wired"
    assert deps.event_emitter is not None

    # --- 1. workspace_resolve --------------------------------------------- #
    ws = _ok(tools["workspace_resolve"](project_root=project_root))
    workspace_id = ws["workspace_id"]
    assert len(workspace_id) == 64 and workspace_id == workspace_id.lower()

    # --- 2. agent_register (two agents) ----------------------------------- #
    builder = _ok(
        tools["agent_register"](
            agent_id="builder", role="builder", capabilities=["py"]
        )
    )
    assert builder["agent_id"] == "builder"
    _ok(tools["agent_register"](agent_id="reviewer", role="reviewer"))

    # --- 3. session_open + heartbeat -------------------------------------- #
    session = _ok(
        tools["session_open"](agent_id="builder", workspace_id=workspace_id)
    )
    assert session["status"] == "active"
    session_id = session["session_id"]
    hb = _ok(tools["session_heartbeat"](session_id=session_id))
    assert hb["status"] == "active"

    # --- 4. message_create -> emits message.created ----------------------- #
    msg = _ok(
        tools["message_create"](
            project_root=project_root,
            from_agent_id="builder",
            subject="kickoff",
            body="starting the build",
        )
    )
    assert msg["subject"] == "kickoff"
    assert isinstance(msg["event_id"], int) and msg["event_id"] >= 1

    # --- 4b. inbox delivery (ADR 0001): a direct message lands in the global
    # inbox and is pulled/acked index-free (reviewer needs no session). ------- #
    dm = _ok(
        tools["message_create"](
            project_root=project_root,
            from_agent_id="builder",
            subject="please review",
            body="PR #1 is ready",
            target={"strategy": "direct", "agent_id": "reviewer"},
        )
    )
    assert dm["recipients"] == ["reviewer"] and dm["delivered_count"] == 1
    assert _ok(tools["inbox_count"](agent_id="reviewer"))["unread"] == 1
    pulled = _ok(tools["inbox_pull"](agent_id="reviewer"))
    assert [m["body"] for m in pulled["messages"]] == ["PR #1 is ready"]
    assert _ok(tools["inbox_ack"](agent_id="reviewer", message_ids=[dm["message_id"]])) == {
        "acknowledged": 1
    }
    assert _ok(tools["inbox_count"](agent_id="reviewer")) == {
        "unread": 0,
        "in_flight": 0,
        "read": 1,
    }

    # message.created is observable on the workspace stream via event_get /
    # event_wait (published there for cross-slice observability).
    ws_after_msg = _ok(
        tools["event_get"](
            project_root=project_root, agent_id="reviewer", stream="workspace"
        )
    )
    assert any(e["type"] == "message.created" for e in ws_after_msg["events"])
    waited_msg = _ok(
        tools["event_wait"](
            project_root=project_root,
            agent_id="reviewer",
            stream="workspace",
            timeout_seconds=2,
        )
    )
    assert waited_msg["timed_out"] is False
    assert any(e["type"] == "message.created" for e in waited_msg["events"])

    # channel_list returns the seeded channels.
    channels = _ok(tools["channel_list"](project_root=project_root))
    assert channels["channels"], "expected seeded channels"

    # --- 5. handoff_create -> emits handoff.created (stream='handoff') ----- #
    created = _ok(
        tools["handoff_create"](
            project_root=project_root,
            from_agent_id="builder",
            target={"strategy": "broadcast"},
            visibility="public",
            payload="please review",
        )
    )
    handoff_id = created["handoff_id"]
    assert created["status"] == "OPEN"

    # --- 6. event_get + event_wait observe the handoff event -------------- #
    page = _ok(
        tools["event_get"](
            project_root=project_root, agent_id="reviewer", stream="handoff"
        )
    )
    types = [e["type"] for e in page["events"]]
    assert "handoff.created" in types
    assert page["timed_out"] is False

    # event_wait returns immediately because the event already exists.
    waited = _ok(
        tools["event_wait"](
            project_root=project_root,
            agent_id="reviewer",
            stream="handoff",
            timeout_seconds=2,
        )
    )
    assert waited["timed_out"] is False
    assert any(e["type"] == "handoff.created" for e in waited["events"])

    # --- 7. handoff_claim + handoff_complete ------------------------------ #
    avail = _ok(
        tools["handoff_list_available"](
            project_root=project_root, agent_id="reviewer"
        )
    )
    assert any(h["handoff_id"] == handoff_id for h in avail["handoffs"])

    claimed = _ok(
        tools["handoff_claim"](
            project_root=project_root, handoff_id=handoff_id, agent_id="reviewer"
        )
    )
    assert claimed["status"] == "CLAIMED" and claimed["claimed_by"] == "reviewer"

    completed = _ok(
        tools["handoff_complete"](
            project_root=project_root,
            handoff_id=handoff_id,
            agent_id="reviewer",
            result={"summary": "looks good"},
        )
    )
    assert completed["status"] == "COMPLETED"

    # --- 8. artifact_put (inline text < 64KB) + (path ref) ---------------- #
    text_art = _ok(
        tools["artifact_put"](
            project_root=project_root,
            artifact_type="text",
            name="report.txt",
            content="x" * 1024,  # 1 KB, well under the 64KB inclusive limit
            metadata={"kind": "report"},
        )
    )
    assert text_art["stored"] == "inline" and text_art["size_bytes"] == 1024
    text_artifact_id = text_art["artifact_id"]

    # A real file inside the workspace root, referenced by path.
    (project / "notes.md").write_text("# notes\n", encoding="utf-8")
    path_art = _ok(
        tools["artifact_put"](
            project_root=project_root,
            artifact_type="markdown",
            name="notes.md",
            path="notes.md",
        )
    )
    assert path_art["stored"] == "path"

    # --- 9. artifact_get round-trips the inline content ------------------- #
    fetched = _ok(
        tools["artifact_get"](
            project_root=project_root, artifact_id=text_artifact_id
        )
    )
    assert fetched["content"] == "x" * 1024
    assert fetched["metadata"] == {"kind": "report"}

    # artifact.created is observable on the workspace stream too.
    ws_after_art = _ok(
        tools["event_get"](
            project_root=project_root, agent_id="reviewer", stream="workspace"
        )
    )
    assert any(e["type"] == "artifact.created" for e in ws_after_art["events"])

    # --- 10. shared_md_render writes the derived view file ---------------- #
    rendered = _ok(tools["shared_md_render"](workspace_id=workspace_id))
    shared_path = rendered["path"]
    assert os.path.isfile(shared_path), f"shared.md not written at {shared_path}"
    assert rendered["sections_rendered"] == 4
    assert rendered["bytes_written"] > 0
    body = open(shared_path, encoding="utf-8").read()
    assert workspace_id in body  # the workspace id is embedded in the view

    # --- 11. The append-only event log contains the lifecycle events ------ #
    rows = _event_rows(deps)
    by_type = {r["type"] for r in rows}
    assert "session.opened" in by_type
    assert "message.created" in by_type
    assert "handoff.created" in by_type
    assert "handoff.claimed" in by_type
    assert "handoff.completed" in by_type
    assert "artifact.created" in by_type
    # event_id is global, monotonic and gapless from 1.
    ids = [r["event_id"] for r in rows]
    assert ids == sorted(ids) == list(range(1, len(ids) + 1))


def test_e2e_failures_surface_as_envelopes(tmp_path):
    """No exception ever escapes the adapter: failures come back as envelopes."""
    home = tmp_path / "home"
    deps = bootstrap({"OKTO_NEXUS_HOME": str(home)}, [])
    server = FakeServer()
    register_tools(server, deps)
    tools = server.tools

    missing_ws = tools["handoff_claim"](
        project_root="", handoff_id="hof_x", agent_id="a"
    )
    assert missing_ws["ok"] is False
    assert missing_ws["error"]["code"] == "WORKSPACE_REQUIRED"

    bad_stream = tools["event_get"](
        project_root=str(tmp_path), agent_id="a", stream="nope"
    )
    assert bad_stream["ok"] is False
    assert bad_stream["error"]["code"] == "INVALID_STREAM"
