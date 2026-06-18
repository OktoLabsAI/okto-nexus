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

from ....config import EMBEDDING_MODE_LOCAL
from ....errors import ErrorCode, OktoNexusError

DEFAULT_PORT = 8202
DEFAULT_HOST = "127.0.0.1"

#: Upper bound (seconds) on uvicorn's graceful shutdown wait. Long-lived
#: connections - the dashboard SSE feed and MCP streamable clients - never
#: complete on their own, so without a ceiling CTRL+C hangs "finalizing" until
#: the operator kills the terminal. The SSE generator self-exits on
#: ``server.should_exit`` (see http/stream.py), so this is only the backstop
#: for any other wedged connection, never the common path.
GRACEFUL_SHUTDOWN_SECONDS = 5.0

_PORT_ENV = "OKTO_NEXUS_PORT"
_HOST_ENV = "OKTO_NEXUS_HOST"
_LOG_LEVEL_ENV = "OKTO_NEXUS_LOG_LEVEL"

#: Default console verbosity: WARNING, so a normal serve shows only warnings and
#: errors. The operator opts into the chatty INFO/DEBUG (uvicorn access logs and
#: the ML/HTTP libraries during model load) with ``--log-level`` or the
#: ``OKTO_NEXUS_LOG_LEVEL`` env var.
DEFAULT_LOG_LEVEL = "warning"
_VALID_LOG_LEVELS = ("critical", "error", "warning", "info", "debug", "trace")


def _split_serve_args(
    args: list[str], env: Mapping[str, str]
) -> tuple[int, str, str, str, list[str]]:
    """Extract serve-specific flags; return (port, host, project_root,
    log_level, rest).

    ``rest`` is handed to ``load_config`` untouched, so every existing
    ``--home``/``--db-path``/TTL flag keeps working on the serve command.
    """
    port_raw = env.get(_PORT_ENV)
    host = env.get(_HOST_ENV) or DEFAULT_HOST
    project_root = "."
    log_level = env.get(_LOG_LEVEL_ENV) or DEFAULT_LOG_LEVEL
    rest: list[str] = []

    i = 0
    while i < len(args):
        token = args[i]
        flag, _, inline = token.partition("=")
        if flag in ("--port", "--host", "--project-root", "--log-level"):
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
            elif flag == "--project-root":
                project_root = value
            else:
                log_level = value
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

    log_level = str(log_level).strip().lower()
    if log_level not in _VALID_LOG_LEVELS:
        raise OktoNexusError(
            ErrorCode.CONFIG_ERROR,
            f"Invalid log level: {log_level!r} (expected one of "
            f"{', '.join(_VALID_LOG_LEVELS)}).",
            {"log_level": log_level},
        )
    return port, host, project_root, log_level, rest


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
  --log-level L       Console verbosity: critical|error|warning|info|debug|
                      trace (default warning; env OKTO_NEXUS_LOG_LEVEL). Only
                      warnings/errors show unless raised to info or higher.
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


#: Third-party loggers that flood the console at INFO - uvicorn's per-request
#: access log and the ML/HTTP stack chattering through the embedding model load
#: (download HEADs, "using cpu", session-manager start). Quieted to WARNING
#: unless the operator opts into >= info via --log-level.
_NOISY_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "httpx",
    "httpcore",
    "huggingface_hub",
    "transformers",
    "sentence_transformers",
    "filelock",
    "urllib3",
    "mcp",
    "asyncio",
)


def _configure_logging(level: str) -> None:
    """Apply the serve console verbosity. Default WARNING shows only warnings
    and errors; the operator raises it with ``--log-level info|debug|trace``.

    Besides the root level, this quiets the chatty ML/HTTP libraries that dump
    INFO while the embedding model loads and disables their progress bars - the
    library knobs are env-driven and read at import time, and the model loads
    lazily in the warm-up thread, so setting them here still takes effect."""
    import logging

    numeric = {
        "critical": logging.CRITICAL,
        "error": logging.ERROR,
        "warning": logging.WARNING,
        "info": logging.INFO,
        "debug": logging.DEBUG,
        "trace": logging.DEBUG,
    }.get(level, logging.WARNING)
    logging.getLogger().setLevel(numeric)

    verbose = level in ("info", "debug", "trace")
    floor = numeric if verbose else logging.WARNING
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(floor)
    if not verbose:
        os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
        os.environ.setdefault("HF_HUB_VERBOSITY", "error")
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _watch_ready(
    server: "object", host: str, port: int, embeddings_done: "object"
) -> None:
    """Announce readiness ONLY once uvicorn flips ``started`` - which by
    construction means the lifespan completed (the MCP session manager is
    running) AND the socket is accepting connections. Pulse's
    ``_log_ready_servers`` grammar.

    The final "ready" line waits on ``embeddings_done`` so completion is never
    announced before the embedding warm-up resolves (the warm-up thread sets
    the event immediately when there is nothing to load)."""
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
    # Hold "ready" until the embedding warm-up resolves; bail out promptly if
    # the operator CTRL+C's during a long first-run model download.
    while not embeddings_done.wait(timeout=0.5):
        if getattr(server, "should_exit", False):
            return
    print(
        "[okto-nexus] Startup complete - Okto Nexus is ready",
        file=sys.stderr,
    )


def _warm_embeddings(deps: "object", done_event: "object") -> None:
    """Eagerly load the local embedding model at startup (mirrors the Pulse KG
    warm-up) so the model is hot BEFORE the first message/search and the
    operator sees it come up - instead of the model lazy-loading silently on
    the first request.

    No-op for off/stub or a degraded local (the extra is absent and generation
    fell back to the stub). Best-effort: a warm-up failure is logged and
    swallowed so the serve stays up and the model lazy-loads on first use.
    Runs on a daemon thread so model load (and a possible first-run download)
    never blocks the serve from accepting connections. ALWAYS signals
    ``done_event`` on exit (no-op, success or failure) so the readiness watcher
    never blocks waiting for the model."""
    import time

    try:
        embedding = getattr(deps, "embedding", None)
        provider = getattr(embedding, "provider", None)
        if embedding is None or provider is None:
            return
        if embedding.mode != EMBEDDING_MODE_LOCAL or embedding.degraded:
            return
        print(
            f"[okto-nexus] Loading embedding model {provider.model} "
            f"(first run may download the model) ...",
            file=sys.stderr,
        )
        started = time.monotonic()
        try:
            provider.encode("warmup")  # forces the lazy load + one forward pass
        except Exception as exc:  # noqa: BLE001 - warm-up must never crash serve
            print(
                f"[okto-nexus] Embedding model warm-up FAILED "
                f"({type(exc).__name__}: {exc}); it will lazy-load on first use.",
                file=sys.stderr,
            )
            return
        print(
            f"[okto-nexus] Embedding model loaded: {provider.model} "
            f"({time.monotonic() - started:.1f}s)",
            file=sys.stderr,
        )
    finally:
        done_event.set()


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
        port, host, project_root, log_level, rest = _split_serve_args(
            list(args), env
        )
        _configure_logging(log_level)
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
            uvicorn.Config(
                app,
                host=host,
                port=port,
                log_level=log_level,
                timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
            )
        )
        # The SSE feed reads this to end its otherwise-infinite generator the
        # moment CTRL+C flips should_exit, so an open dashboard never holds the
        # graceful-shutdown wait open (the "stuck finalizing" report).
        app.state.server = server
        # Warm the embedding model in the background (mirrors Pulse) so it is
        # hot before the first request; no-op unless embedding_mode=local with
        # the extra present. build_app already re-resolved deps.embedding from
        # the effective (override-applied) mode. The readiness watcher waits on
        # this event so the final "ready" line prints AFTER the model is loaded.
        embeddings_done = threading.Event()
        threading.Thread(
            target=_warm_embeddings, args=(deps, embeddings_done), daemon=True
        ).start()
        threading.Thread(
            target=_watch_ready,
            args=(server, host, port, embeddings_done),
            daemon=True,
        ).start()
        try:
            server.run()
        except KeyboardInterrupt:
            # uvicorn already completed its graceful shutdown and re-raised
            # the captured CTRL+C (its signal-forwarding contract). The work
            # is DONE at this point - swallowing it turns a scary multi-page
            # traceback into the calm goodbye the operator expects.
            print("[okto-nexus] Shutdown complete.", file=sys.stderr)
        return 0
    finally:
        lock.release()
