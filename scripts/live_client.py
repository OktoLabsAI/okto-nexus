"""Real HTTP MCP smoke with two isolated, locally provisioned agent identities.

Uses the installed interpreter, a foreground loopback Server and the official
MCP SDK. It never executes a harness or contacts a model provider. Temporary
agent keys stay in memory; Server state contains their canonical hashes only.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

PKG_MODULE = "okto_nexus.adapters.inbound.mcp.server"


def isolated_environment(root: Path) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(
            ("OKTO_", "NEXUS_", "OPENAI", "ANTHROPIC", "CLAUDE", "CODEX")
        )
        and key.upper()
        not in {"PYTHONPATH", "PYTHONHOME", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}
        and not any(
            part in key.upper()
            for part in ("API_KEY", "ACCESS_TOKEN", "AUTH_TOKEN", "PASSWORD", "SECRET")
        )
    }
    for name, relative in (
        ("HOME", "profile"),
        ("USERPROFILE", "profile"),
        ("APPDATA", "profile/roaming"),
        ("LOCALAPPDATA", "profile/local"),
        ("PATH", "empty-path"),
    ):
        directory = root / relative
        directory.mkdir(parents=True, exist_ok=True)
        env[name] = str(directory)
    env.update(PYTHONUTF8="1", OKTO_NEXUS_NO_BANNER="1", OKTO_NEXUS_LOG_LEVEL="warning")
    return env


def serve_command(home: Path, project: Path, port: int) -> list[str]:
    return [
        sys.executable,
        "-I",
        "-m",
        PKG_MODULE,
        "serve",
        "--home",
        str(home),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--project-root",
        str(project),
        "--embedding-mode",
        "off",
    ]


def remove_owned_root(root: Path, snapshot: Path, temporary_parent: Path) -> None:
    """Fence the exact root allocated by this run before recursive cleanup."""
    resolved = root.resolve()
    if (
        root.is_symlink()
        or resolved != snapshot
        or resolved.parent != temporary_parent
        or not resolved.name.startswith("okto-live-http-mcp-")
    ):
        raise RuntimeError("Temporary cleanup refused a changed or out-of-scope root.")
    import shutil

    shutil.rmtree(resolved)


def bootstrap_agents(home: Path, project: Path) -> tuple[str, dict[str, str]]:
    from okto_nexus.bootstrap.dependencies import bootstrap
    from okto_nexus.adapters.inbound.mcp.tools.identity import build_service
    from okto_nexus.application.auth import AgentKeyAuthService

    deps = bootstrap({}, ["--home", str(home), "--embedding-mode", "off"])
    try:
        identity = build_service(deps)
        workspace = identity.workspace_resolve(
            project_root=str(project), display_name="Isolated live HTTP MCP"
        )
        for agent, role in (("agent-alpha", "architect"), ("agent-beta", "builder")):
            identity.agent_register(agent_id=agent, role=role)
        auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
        with deps.connection_factory.unit_of_work() as uow:
            keys = {
                agent: auth.issue_key(uow, agent_id=agent)
                for agent in ("agent-alpha", "agent-beta")
            }
        return workspace["workspace_id"], keys
    finally:
        # The factory pools connections even after a unit of work closes.
        # Release this provisioning process's handles before starting serve.
        deps.connection_factory.close()


async def wait_ready(process: subprocess.Popen, origin: str) -> None:
    deadline = time.monotonic() + 30
    async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("The isolated Server exited before readiness.")
            try:
                if (await client.get(origin + "/healthz")).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.1)
    raise RuntimeError("The isolated Server did not become ready within 30 seconds.")


def stop_server(
    process: subprocess.Popen, home: Path, env: dict[str, str], port: int
) -> dict[str, Any]:
    if process.poll() is not None:
        return {
            "physical_exit": True,
            "exit_code": process.returncode,
            "already_exited": True,
        }
    command = [
        sys.executable,
        "-I",
        "-m",
        PKG_MODULE,
        "service",
        "stop",
        "--home",
        str(home),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--timeout",
        "15",
        "--json",
    ]
    result = subprocess.run(
        command, cwd=home.parent, env=env, capture_output=True, text=True, timeout=25
    )
    try:
        code = process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        # The caller retains the temporary root on this failure. Never erase
        # a live owner's files or terminate another process by a cached PID.
        raise RuntimeError(
            "The owned Server did not exit after canonical stop; temporary state is preserved."
        ) from None
    return {
        "physical_exit": True,
        "exit_code": code,
        "canonical_stop_exit_code": result.returncode,
    }


def envelope_of(result: Any) -> dict[str, Any]:
    if getattr(result, "isError", False):
        raise RuntimeError("MCP reported a tool error.")
    value = getattr(result, "structuredContent", None)
    if value is None:
        for block in getattr(result, "content", None) or []:
            if getattr(block, "text", None):
                try:
                    value = json.loads(block.text)
                    break
                except ValueError:
                    pass
    if (
        isinstance(value, dict)
        and "ok" not in value
        and isinstance(value.get("result"), dict)
    ):
        value = value["result"]
    if not isinstance(value, dict):
        raise RuntimeError("MCP returned a non-envelope result.")
    return value


async def call(session: ClientSession, tool: str, **arguments: Any) -> dict[str, Any]:
    value = envelope_of(await session.call_tool(tool, arguments))
    if value.get("ok") is not True:
        code = (value.get("error") or {}).get("code", "INVALID_ENVELOPE")
        raise RuntimeError(f"{tool} refused the isolated flow ({code}).")
    print(f"MCP {tool}: OK")
    return value["data"]


async def exercise(
    origin: str, project: Path, home: Path, workspace: str, keys: dict[str, str]
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "transport": "HTTP /mcp/",
        "authenticated_agents": 2,
        "provider_calls": 0,
        "real_harnesses_tested": False,
    }
    async with AsyncExitStack() as stack:
        sessions = {}
        for agent in ("agent-alpha", "agent-beta"):
            client = await stack.enter_async_context(
                httpx.AsyncClient(
                    headers={"Authorization": "Bearer " + keys[agent]},
                    trust_env=False,
                    timeout=httpx.Timeout(35, read=35),
                )
            )
            read, write, _ = await stack.enter_async_context(
                streamable_http_client(origin + "/mcp/", http_client=client)
            )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            sessions[agent] = session
        alpha, beta = sessions["agent-alpha"], sessions["agent-beta"]
        tools = await alpha.list_tools()
        summary["tools_count"] = len(tools.tools)
        actual = await call(
            alpha,
            "workspace_resolve",
            project_root=str(project),
            display_name="Isolated live HTTP MCP",
        )
        assert actual["workspace_id"] == workspace
        await call(alpha, "agent_register", agent_id="agent-alpha", role="architect")
        await call(beta, "agent_register", agent_id="agent-beta", role="builder")
        who_alpha = await call(alpha, "agent_whoami")
        who_beta = await call(beta, "agent_whoami")
        assert (
            who_alpha["agent_id"] == "agent-alpha"
            and who_beta["agent_id"] == "agent-beta"
        )
        sid_alpha = (
            await call(
                alpha, "session_open", agent_id="agent-alpha", workspace_id=workspace
            )
        )["session_id"]
        sid_beta = (
            await call(
                beta, "session_open", agent_id="agent-beta", workspace_id=workspace
            )
        )["session_id"]
        channels = (await call(alpha, "channel_list", project_root=str(project)))[
            "channels"
        ]
        general = next(
            row["channel_id"] for row in channels if row["name"] == "general"
        )
        msg = await call(
            alpha,
            "message_create",
            project_root=str(project),
            from_agent_id="agent-alpha",
            subject="Live HTTP coordination",
            body="Isolated SDK message; no provider inference.",
            channel_id=general,
            from_session_id=sid_alpha,
        )
        events = (
            await call(
                beta,
                "event_wait",
                project_root=str(project),
                agent_id="agent-beta",
                stream="workspace",
                cursor=0,
                timeout_seconds=5,
            )
        )["events"]
        assert any(
            event.get("type") == "message.created"
            and (event.get("payload") or {}).get("message_id") == msg["message_id"]
            for event in events
        )
        summary["message_observed_via_event_wait"] = True
        handoff = await call(
            alpha,
            "handoff_create",
            project_root=str(project),
            from_agent_id="agent-alpha",
            target={"strategy": "direct", "agent_id": "agent-beta"},
            visibility="public",
            payload="Synthetic coordination-only acknowledgement.",
            session_id=sid_alpha,
        )
        await call(
            beta,
            "handoff_claim",
            project_root=str(project),
            handoff_id=handoff["handoff_id"],
            agent_id="agent-beta",
            session_id=sid_beta,
        )
        await call(
            beta,
            "handoff_complete",
            project_root=str(project),
            handoff_id=handoff["handoff_id"],
            agent_id="agent-beta",
            result="Synthetic acknowledgement; no harness executed.",
        )
        artifact = await call(
            alpha,
            "artifact_put",
            project_root=str(project),
            artifact_type="text",
            name="live-http-summary.txt",
            content="Real HTTP MCP SDK flow; no provider call.",
        )
        await call(
            alpha,
            "artifact_get",
            project_root=str(project),
            artifact_id=artifact["artifact_id"],
        )
        shared = await call(
            alpha, "shared_md_render", workspace_id=workspace, limit_events=50
        )
        shared_path = Path(shared["path"]).resolve()
        assert shared_path.is_relative_to(home.resolve()) and shared_path.is_file()
        summary.update(
            handoff_completed=True,
            artifact_round_trip=True,
            shared_md_written=True,
            workspace_id=workspace,
            all_envelopes_ok=True,
        )
    return summary


async def run() -> int:
    logging.basicConfig(level=logging.WARNING)
    root = Path(tempfile.mkdtemp(prefix="okto-live-http-mcp-")).resolve()
    root_snapshot = root
    temporary_parent = Path(tempfile.gettempdir()).resolve()
    home, project = root / "home", root / "project"
    project.mkdir()
    env = isolated_environment(root)
    workspace, keys = bootstrap_agents(home, project)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = None
    clean = False
    summary: dict[str, Any] = {}
    try:
        with (root / "server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                serve_command(home, project, port),
                cwd=root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            await wait_ready(process, f"http://127.0.0.1:{port}")
            async with asyncio.timeout(90):
                summary = await exercise(
                    f"http://127.0.0.1:{port}", project, home, workspace, keys
                )
    finally:
        keys.clear()
        if process is not None:
            summary["cleanup"] = await asyncio.to_thread(
                stop_server, process, home, env, port
            )
        clean = process is None or process.poll() is not None
        if clean:
            remove_owned_root(root, root_snapshot, temporary_parent)
        else:
            print("Owned Server state preserved at:", root, file=sys.stderr)
    print(json.dumps(summary, indent=2))
    print("LIVE E2E RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
