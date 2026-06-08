"""Live MCP stdio client that exercises the Okto Nexus end-to-end flow.

This is NOT a unit test. It spawns the REAL Okto Nexus MCP server as a child
process over the REAL stdio transport (using the official MCP Python SDK:
``mcp.client.stdio.stdio_client`` + ``mcp.ClientSession``) and drives the full
coordination flow exactly as a third-party MCP client (e.g. an IDE/agent) would:

    initialize
      -> list_tools
      -> workspace_resolve        (resolve a temp project_root -> workspace_id)
      -> agent_register x2         (agent-alpha, agent-beta)
      -> session_open  x2          (one session per agent)
      -> channel_list              (locate the seeded ``general`` channel)
      -> message_create            (post on #general)
      -> event_wait(stream=workspace, cursor=0)   <-- OBSERVES message.created
      -> handoff_create            (direct -> agent-beta)
      -> handoff_claim             (by agent-beta)
      -> handoff_complete          (by agent-beta)
      -> artifact_put / artifact_get
      -> shared_md_render          (writes {home}/workspaces/{ws}/shared.md)

Isolation: the child server runs with ``OKTO_NEXUS_HOME`` pointed at a fresh
TEMP directory, so it never touches the real ``~/.okto_nexus`` store. Both the
temp home and the temp project_root are removed on exit.

The server bootstrap is fail-closed and ordered (load_config -> ensure home ->
migrations -> register tools), so a successful ``list_tools`` already proves the
SQLite store was migrated before any tool became callable.

Run it with the venv interpreter:

    D:\\Projetos\\Techridy\\okto_labs_okto_nexus\\.venv\\Scripts\\python.exe scripts/live_client.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

#: The server module is launched as ``python -m <PKG_MODULE>`` (its ``__main__``
#: guard calls ``main()``, which runs the fail-closed bootstrap then serves over
#: stdio). The console entry point ``okto-nexus`` resolves to the same ``main``.
PKG_MODULE = "okto_nexus.adapters.inbound.mcp.server"


def section(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def envelope_of(result: Any) -> Any:
    """Extract the canonical ``{ok, data|error}`` envelope from a CallToolResult.

    Prefers the typed ``structuredContent`` and falls back to JSON-decoding the
    text content block. If a transport wrapped the object under ``result``, unwrap
    it (defensive; FastMCP returns object dicts verbatim).
    """
    if getattr(result, "isError", False):
        print("  [server reported isError=True]")
    data = getattr(result, "structuredContent", None)
    if data is None:
        for block in getattr(result, "content", None) or []:
            text = getattr(block, "text", None)
            if text:
                try:
                    data = json.loads(text)
                    break
                except (ValueError, TypeError):
                    continue
    if isinstance(data, dict) and "ok" not in data and isinstance(data.get("result"), dict):
        data = data["result"]
    return data


def show(env: Any, maxlen: int = 1500) -> None:
    text = json.dumps(env, indent=2, ensure_ascii=False)
    if len(text) > maxlen:
        text = text[:maxlen] + "\n  ... [truncated]"
    print(text)


async def call(session: ClientSession, tool: str, /, **kwargs: Any) -> dict[str, Any]:
    """Invoke a tool over the live session and return its parsed envelope.

    ``session`` and ``tool`` are positional-only (``/``) so a tool argument named
    ``tool``/``session`` (e.g. ``artifact_put``'s ``name``) never collides.
    """
    result = await session.call_tool(tool, kwargs)
    env = envelope_of(result)
    print(f"\n>>> call_tool {tool}({', '.join(f'{k}=...' for k in kwargs)})")
    show(env)
    if not isinstance(env, dict):
        raise RuntimeError(f"{tool}: could not parse an envelope from the result")
    return env


def require_ok(env: dict[str, Any], name: str) -> dict[str, Any]:
    if env.get("ok") is not True:
        raise RuntimeError(f"{name} did not return ok=true: {env!r}")
    return env["data"]


async def run() -> int:
    py = sys.executable  # the venv interpreter running this script
    home = tempfile.mkdtemp(prefix="okto_nexus_home_")
    proj = tempfile.mkdtemp(prefix="okto_proj_")

    section("0) live MCP stdio session setup")
    print(f"command (venv python): {py}")
    print(f"server args          : -m {PKG_MODULE}")
    print(f"OKTO_NEXUS_HOME (temp): {home}")
    print(f"project_root    (temp): {proj}")

    child_env = dict(os.environ)
    child_env["OKTO_NEXUS_HOME"] = home  # isolate the store from ~/.okto_nexus

    params = StdioServerParameters(
        command=py,
        args=["-m", PKG_MODULE],
        env=child_env,
    )

    summary: dict[str, Any] = {
        "server_spawned": False,
        "initialize_ok": False,
        "tools_count": 0,
        "message_observed_via_event_wait": False,
        "shared_md_written": False,
        "all_envelopes_ok": False,
    }
    envelopes: list[dict[str, Any]] = []

    try:
        async with stdio_client(params) as (read, write):
            summary["server_spawned"] = True
            async with ClientSession(read, write) as session:
                # 1) initialize ------------------------------------------------
                section("1) initialize")
                init = await session.initialize()
                summary["initialize_ok"] = True
                print("server name    :", init.serverInfo.name)
                print("server version :", getattr(init.serverInfo, "version", None))
                print("protocol       :", init.protocolVersion)

                # 2) list_tools ------------------------------------------------
                section("2) list_tools")
                listed = await session.list_tools()
                names = sorted(t.name for t in listed.tools)
                summary["tools_count"] = len(names)
                summary["tool_names"] = names
                print("tools_count:", len(names))
                for n in names:
                    print("  -", n)

                # 3) workspace_resolve ----------------------------------------
                section("3) workspace_resolve")
                ws = await call(
                    session,
                    "workspace_resolve",
                    project_root=proj,
                    display_name="E2E Live Workspace",
                )
                envelopes.append(ws)
                workspace_id = require_ok(ws, "workspace_resolve")["workspace_id"]
                print("workspace_id:", workspace_id)

                # 4) agent_register x2 ----------------------------------------
                section("4) agent_register (agent-alpha, agent-beta)")
                a1 = await call(
                    session, "agent_register",
                    agent_id="agent-alpha", role="architect",
                    capabilities=["py", "review"],
                )
                a2 = await call(
                    session, "agent_register",
                    agent_id="agent-beta", role="builder",
                    capabilities=["py"],
                )
                envelopes += [a1, a2]
                require_ok(a1, "agent_register/alpha")
                require_ok(a2, "agent_register/beta")

                # 5) session_open x2 ------------------------------------------
                section("5) session_open (one session per agent)")
                s1 = await call(session, "session_open", agent_id="agent-alpha", workspace_id=workspace_id)
                s2 = await call(session, "session_open", agent_id="agent-beta", workspace_id=workspace_id)
                envelopes += [s1, s2]
                sid_alpha = require_ok(s1, "session_open/alpha")["session_id"]
                sid_beta = require_ok(s2, "session_open/beta")["session_id"]
                print("session alpha:", sid_alpha)
                print("session beta :", sid_beta)

                # 6) channel_list (find the seeded 'general' channel) ---------
                section("6) channel_list (resolve seeded 'general')")
                ch = await call(session, "channel_list", project_root=proj)
                envelopes.append(ch)
                channels = require_ok(ch, "channel_list")["channels"]
                general_id = next(c["channel_id"] for c in channels if c["name"] == "general")
                print("general channel_id:", general_id)

                # 7) message_create (on #general) -----------------------------
                section("7) message_create (channel=general)")
                msg = await call(
                    session, "message_create",
                    project_root=proj, from_agent_id="agent-alpha",
                    subject="Kickoff",
                    body="Hello team, alpha here on #general. Spinning up the E2E flow.",
                    channel_id=general_id, from_session_id=sid_alpha,
                )
                envelopes.append(msg)
                msg_data = require_ok(msg, "message_create")
                msg_id = msg_data["message_id"]
                print("message_id:", msg_id, "| event_id:", msg_data.get("event_id"))

                # 8) event_wait on the 'workspace' stream ---------------------
                # message.created is published on the 'workspace' stream, so a
                # consumer long-polling that stream from cursor=0 must observe it.
                section("8) event_wait(stream=workspace, cursor=0) -> observe message.created")
                ev = await call(
                    session, "event_wait",
                    project_root=proj, agent_id="agent-alpha",
                    stream="workspace", cursor=0, timeout_seconds=5,
                )
                envelopes.append(ev)
                events = require_ok(ev, "event_wait")["events"]
                observed = [
                    e for e in events
                    if e.get("type") == "message.created"
                    and (e.get("payload") or {}).get("message_id") == msg_id
                ]
                summary["message_observed_via_event_wait"] = bool(observed)
                print(f"events returned: {len(events)} | message.created matched: {bool(observed)}")

                # 9) handoff_create (direct -> agent-beta) --------------------
                section("9) handoff_create (direct -> agent-beta)")
                ho = await call(
                    session, "handoff_create",
                    project_root=proj, from_agent_id="agent-alpha",
                    target={"strategy": "direct", "agent_id": "agent-beta"},
                    visibility="public",
                    payload="Please review the kickoff and acknowledge.",
                    session_id=sid_alpha,
                )
                envelopes.append(ho)
                handoff_id = require_ok(ho, "handoff_create")["handoff_id"]
                print("handoff_id:", handoff_id)

                # 10) handoff_claim (by the 2nd agent) ------------------------
                section("10) handoff_claim (by agent-beta)")
                cl = await call(
                    session, "handoff_claim",
                    project_root=proj, handoff_id=handoff_id,
                    agent_id="agent-beta", session_id=sid_beta,
                )
                envelopes.append(cl)
                require_ok(cl, "handoff_claim")

                # 11) handoff_complete (by the owner/claimer) -----------------
                section("11) handoff_complete (by agent-beta)")
                co = await call(
                    session, "handoff_complete",
                    project_root=proj, handoff_id=handoff_id,
                    agent_id="agent-beta", result="Reviewed and acknowledged.",
                )
                envelopes.append(co)
                require_ok(co, "handoff_complete")

                # 12) artifact_put (small inline text) ------------------------
                section("12) artifact_put (text)")
                ap = await call(
                    session, "artifact_put",
                    project_root=proj, artifact_type="text",
                    name="e2e-summary.txt",
                    content="Okto Nexus live E2E summary: full flow exercised OK.",
                )
                envelopes.append(ap)
                artifact_id = require_ok(ap, "artifact_put")["artifact_id"]
                print("artifact_id:", artifact_id)

                # 13) artifact_get --------------------------------------------
                section("13) artifact_get")
                ag = await call(session, "artifact_get", project_root=proj, artifact_id=artifact_id)
                envelopes.append(ag)
                require_ok(ag, "artifact_get")

                # 14) shared_md_render ----------------------------------------
                section("14) shared_md_render")
                sm = await call(session, "shared_md_render", workspace_id=workspace_id, limit_events=50)
                envelopes.append(sm)
                sm_data = require_ok(sm, "shared_md_render")
                shared_path = sm_data.get("path")
                exists = bool(shared_path) and os.path.isfile(shared_path)
                summary["shared_md_written"] = exists
                print("shared.md path  :", shared_path)
                print("bytes_written   :", sm_data.get("bytes_written"))
                print("sections        :", sm_data.get("sections_rendered"))
                print("exists on disk  :", exists)
                if exists:
                    body = Path(shared_path).read_text(encoding="utf-8")
                    print("\n--- shared.md (first 1400 chars) ---")
                    print(body[:1400])

                summary["all_envelopes_ok"] = all(
                    isinstance(e, dict) and e.get("ok") is True for e in envelopes
                )

                section("SUMMARY")
                print(json.dumps(summary, indent=2, ensure_ascii=False))
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(proj, ignore_errors=True)

    ok = (
        summary["server_spawned"]
        and summary["initialize_ok"]
        and summary["tools_count"] >= 1
        and summary["message_observed_via_event_wait"]
        and summary["shared_md_written"]
        and summary["all_envelopes_ok"]
    )
    print("\nLIVE E2E RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
