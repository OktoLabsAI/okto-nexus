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
from pathlib import Path
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


SERVE_USAGE = """\
okto-nexus serve - start the HTTP hub (MCP + REST + dashboard)

Usage:
  okto-nexus serve [options]

The zero-config default just works: data lives in ~/.okto_nexus, the
dashboard opens key-free on http://127.0.0.1:8202 and every runtime knob
can also be tuned later in the dashboard's Settings screen.

Options:
  --port N            Port to listen on (default 8202; env OKTO_NEXUS_PORT)
  --host ADDR         Bind address (default 127.0.0.1; binding beyond
                      loopback makes the dashboard/REST require an API key)
  --project-root P    Workspace the dashboard opens scoped to (default: .)
  --home P            Data directory (default ~/.okto_nexus)
  --db-path P         SQLite file (default {home}/nexus.db)
  --trust-mode M      open | strict
  -h, --help          Show this help

Any other --flag accepted by the okto-nexus configuration (TTLs, retention
windows, limits) is forwarded as-is; unknown flags fail closed.
"""


_BANNER_PATH = Path(__file__).parent / "banner.txt"


def _banner_version() -> str:
    """The installed package version for the banner line (Pulse grammar)."""
    import importlib.metadata

    try:
        return importlib.metadata.version("okto-nexus")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


def _print_banner() -> None:
    """Print the Okto Nexus ASCII banner to stderr (kept off stdout to
    avoid corrupting JSON pipes), followed by the installed version - the
    Pulse CLI pattern. Suppressed when ``OKTO_NEXUS_NO_BANNER`` is set or
    the banner file is missing."""
    if os.environ.get("OKTO_NEXUS_NO_BANNER"):
        return
    try:
        sys.stderr.write(_BANNER_PATH.read_text(encoding="utf-8"))
        sys.stderr.write("\n")
        sys.stderr.write(f"Version {_banner_version()}\n\n")
        sys.stderr.flush()
    except OSError:
        pass


def _watch_ready(server: "object", host: str, port: int) -> None:
    """Announce readiness ONLY once uvicorn flips ``started`` - which by
    construction means the lifespan completed (the MCP session manager is
    running) AND the socket is accepting connections. Pulse's
    ``_log_ready_servers`` grammar."""
    import time

    while not getattr(server, "started", False):
        if getattr(server, "should_exit", False):
            return
        time.sleep(0.1)
    print(
        f"[okto-nexus] MCP Server initialized successfully - "
        f"http://{host}:{port}/mcp",
        file=sys.stderr,
    )
    print(
        f"[okto-nexus] API Server initialized successfully - "
        f"http://{host}:{port}/api/v1",
        file=sys.stderr,
    )
    print(
        f"[okto-nexus] Dashboard initialized successfully - "
        f"http://{host}:{port}",
        file=sys.stderr,
    )
    print(
        "[okto-nexus] Startup complete - Okto Nexus is ready",
        file=sys.stderr,
    )


def run_serve(args: list[str], env: Mapping[str, str] | None = None) -> int:
    """Console entry for the ``serve`` subcommand. Returns an exit code."""
    env = env if env is not None else os.environ

    if any(token in ("-h", "--help") for token in args):
        print(SERVE_USAGE)
        return 0

    _print_banner()

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

    import threading

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

        local_open = host in ("127.0.0.1", "localhost", "::1")

        # Anti-lockout bootstrap, ONLY for non-loopback binds: there the
        # dashboard requires a key, and a keyless store would lock the
        # operator out entirely. On loopback (the default) no key is ever
        # needed locally, so nothing is issued and nothing is printed.
        if not local_open:
            auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
            issued = ensure_operator_key(deps, auth)
            if issued is not None:
                agent_id, plaintext = issued
                print(
                    f"\n[okto-nexus] Bind beyond loopback with NO issued keys: "
                    f"created agent '{agent_id}' so you can reach the remote "
                    f"dashboard. The key is shown ONCE - store it now:\n\n"
                    f"  {plaintext}\n\n"
                    f"MCP client snippet:\n"
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
        app.state.local_open = local_open
        if not local_open:
            print(
                f"[okto-nexus] host {host!r} is not loopback: the dashboard "
                "and REST will REQUIRE an agent API key.",
                file=sys.stderr,
            )

        server = uvicorn.Server(
            uvicorn.Config(app, host=host, port=port, log_level="info")
        )
        threading.Thread(
            target=_watch_ready, args=(server, host, port), daemon=True
        ).start()
        server.run()
        return 0
    finally:
        lock.release()
