"""`okto-nexus serve` - the single-process HTTP runtime (spec S1, C3).

Fail-closed bootstrap order (FR1):

1. parse serve flags (``--port``/``--host``/``--project-root``); remaining
   flags go through the standard fail-closed ``load_config`` parser
2. ``bootstrap`` (config -> home dir -> connections -> migrations -> repos)
3. single-server lock (decision D4) - BEFORE anything else can mutate state
4. cold-start key bootstrap: print the operator key + .mcp.json snippet ONCE
5. uvicorn serves /mcp + /api/v1 + the dashboard root

The HTTP extra is optional: a missing FastAPI/uvicorn aborts with an install
hint instead of a traceback.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Mapping

from ....errors import ErrorCode, OktoNexusError

DEFAULT_PORT = 8202
DEFAULT_HOST = "127.0.0.1"

_PORT_ENV = "OKTO_NEXUS_PORT"
_HOST_ENV = "OKTO_NEXUS_HOST"


def _split_serve_args(
    args: list[str], env: Mapping[str, str]
) -> tuple[int, str, str, list[str]]:
    """Extract serve-specific flags; return (port, host, project_root, rest).

    ``rest`` is handed to ``load_config`` untouched, so every existing
    ``--home``/``--db-path``/TTL flag keeps working on the serve command.
    """
    port_raw = env.get(_PORT_ENV)
    host = env.get(_HOST_ENV) or DEFAULT_HOST
    project_root = "."
    rest: list[str] = []

    i = 0
    while i < len(args):
        token = args[i]
        flag, _, inline = token.partition("=")
        if flag in ("--port", "--host", "--project-root"):
            if inline:
                value = inline
            else:
                if i + 1 >= len(args):
                    raise OktoNexusError(
                        ErrorCode.CONFIG_ERROR,
                        f"Missing value for flag {flag!r}",
                        {"flag": flag},
                    )
                value = args[i + 1]
                i += 1
            if flag == "--port":
                port_raw = value
            elif flag == "--host":
                host = value
            else:
                project_root = value
        else:
            rest.append(token)
        i += 1

    if port_raw is None:
        port = DEFAULT_PORT
    else:
        try:
            port = int(str(port_raw).strip())
            if not (0 < port < 65536):
                raise ValueError
        except (TypeError, ValueError):
            raise OktoNexusError(
                ErrorCode.CONFIG_ERROR,
                f"Invalid port: {port_raw!r} (expected 1-65535).",
                {"port": port_raw},
            ) from None
    return port, host, project_root, rest


def _mcp_json_snippet(host: str, port: int, api_key: str) -> str:
    return json.dumps(
        {
            "mcpServers": {
                "okto-nexus": {"url": f"http://{host}:{port}/mcp?api_key={api_key}"}
            }
        },
        indent=2,
    )


def run_serve(args: list[str], env: Mapping[str, str] | None = None) -> int:
    """Console entry for the ``serve`` subcommand. Returns an exit code."""
    env = env if env is not None else os.environ

    try:
        import uvicorn  # noqa: F401 - probe the optional extra first
        from fastapi import FastAPI  # noqa: F401
    except ImportError:
        print(
            "[okto-nexus] `serve` needs the HTTP extra. Install it with: "
            "pip install 'okto-nexus[serve]'",
            file=sys.stderr,
        )
        return 1

    from ..mcp.server import bootstrap, maybe_auto_prune
    from ....application.auth import AgentKeyAuthService
    from ....domain.ids import resolve_workspace_id
    from ..http.app import build_app, ensure_operator_key
    from ..http.lock import ServeLock

    try:
        port, host, project_root, rest = _split_serve_args(list(args), env)
        deps = bootstrap(env, rest)
    except OktoNexusError as exc:
        print(
            f"[okto-nexus] serve bootstrap failed: {exc.code}: {exc.message}",
            file=sys.stderr,
        )
        return 1

    lock = ServeLock(deps.config.home_dir)
    try:
        lock.acquire()
    except OktoNexusError as exc:
        print(f"[okto-nexus] {exc.message}", file=sys.stderr)
        return 1

    try:
        maybe_auto_prune(deps)

        auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
        issued = ensure_operator_key(deps, auth)
        if issued is not None:
            agent_id, plaintext = issued
            print(
                f"\n[okto-nexus] First run: issued an API key for agent "
                f"'{agent_id}'. It is shown ONCE - store it now:\n\n"
                f"  {plaintext}\n\n"
                f"Add the MCP server to a client with this .mcp.json:\n"
                f"{_mcp_json_snippet(host, port, plaintext)}\n",
                file=sys.stderr,
            )

        try:
            default_workspace = resolve_workspace_id(project_root)
        except OktoNexusError:
            default_workspace = None  # dashboard falls back to "all workspaces"

        app = build_app(deps, lock=lock)
        app.state.default_workspace_id = default_workspace
        app.state.project_root = project_root
        # Same-machine trust: dashboard/REST open without a key ONLY when
        # bound to loopback; any wider bind re-enables the key gate.
        app.state.local_open = host in ("127.0.0.1", "localhost", "::1")
        if not app.state.local_open:
            print(
                f"[okto-nexus] host {host!r} is not loopback: the dashboard "
                "and REST will REQUIRE an agent API key.",
                file=sys.stderr,
            )

        print(
            f"[okto-nexus] serving on http://{host}:{port}  "
            f"(mcp: /mcp - api: /api/v1 - docs: /api/v1/docs)",
            file=sys.stderr,
        )
        uvicorn.run(app, host=host, port=port, log_level="info")
        return 0
    finally:
        lock.release()
