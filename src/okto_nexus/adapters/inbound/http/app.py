"""FastAPI application factory for `okto-nexus serve` (spec S1, C3/C4).

One process, three surfaces (decision D1):

* ``/mcp``      - the 35 MCP tools over streamable-http (same ``register``
  functions as stdio: parity by construction), gated by per-agent API keys.
* ``/api/v1``   - REST: observability read-model + agent/key management.
* ``/``         - the dashboard SPA (static; spec S2) + health/info.

Authentication (decision D5): every non-public route requires an API key
resolved to an ACTIVE agent. Extraction order matches the Pulse middleware:
query ``api_key`` -> header ``x-api-key`` -> ``Authorization: Bearer``. A
failed resolve is a uniform 401 with no side effects (AC2); a successful one
binds the agent into :mod:`identity_ctx` for the request.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

import anyio.to_thread
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ....application.auth import AgentKeyAuthService
from ....application.health import HealthService
from ....application.observability import ObservabilityService
from ....application.search import MessageSearchService
from ....application.settings import SettingsService, detect_pinned_fields
from ....application.workspace_analytics import WorkspaceAnalyticsService
from ....application.workspace_overview import WorkspaceListService
from ....domain.approvals import OPERATOR_AGENT_ID
from ....errors import OktoNexusError
from ...outbound.embedding import resolve_embedding_provider
from ...outbound.sqlite.embeddings_repo import SqliteMessageVectorStore
from ...outbound.sqlite.observability_repo import SqliteObservabilityQueries
from ...outbound.tokenizer import resolve_tokenizer
from ..mcp.server import (
    SERVER_INSTRUCTIONS,
    Deps,
    register_meta_tools,
    register_resources,
    register_tools,
)
from . import routes, stream
from .identity_ctx import current_agent
from .lock import HEARTBEAT_INTERVAL_SECONDS, ServeLock

#: Paths reachable WITHOUT an API key. Everything else is key-gated.
#: The SPA shell and its bundles are public by design - they contain no
#: data; every byte of data still rides the key-gated /api/v1 surface.
PUBLIC_PATHS = frozenset(
    {"/", "/healthz", "/api/v1/info", "/api/v1/license", "/favicon.ico"}
)
PUBLIC_PREFIXES = ("/assets/", "/logos/")


def ok(data: Any) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data})


def err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": {"code": code, "message": message}}, status_code=status
    )


def extract_api_key(request: Request) -> str | None:
    """Pulse-order credential extraction: query -> x-api-key -> Bearer."""
    key = request.query_params.get("api_key")
    if key:
        return key
    key = request.headers.get("x-api-key")
    if key:
        return key
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


#: Hosts considered "same machine" for the operator convenience rule.
_LOOPBACK_CLIENTS = frozenset({"127.0.0.1", "::1", "localhost"})


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Resolve the inbound key to an agent or fail uniformly with 401.

    Runs for EVERY route - including the mounted MCP sub-app - except the
    public allowlist. The resolved agent is parked in ``identity_ctx`` so
    handlers and tools can read the caller identity. The resolve itself
    performs the only write of the read path (``last_seen_at`` touch).

    Operator convenience (same-machine trust, the stdio rationale): when the
    serve is bound to loopback (``app.state.local_open``) AND the request
    comes from a loopback client, the REST/dashboard surfaces open WITHOUT a
    key - whoever sits on this machine already owns nexus.db on disk. The
    ``/mcp`` surface is exempt from this rule: an MCP connection IS an agent
    identity (D5), so it requires a key on every transport, always.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path.rstrip("/") or "/"
        if (
            path in PUBLIC_PATHS
            or request.url.path.startswith(PUBLIC_PREFIXES)
            or request.method == "OPTIONS"
        ):
            return await call_next(request)

        is_mcp = request.url.path.startswith("/mcp")
        if (
            not is_mcp
            and getattr(request.app.state, "local_open", False)
            and request.client is not None
            and request.client.host in _LOOPBACK_CLIENTS
        ):
            return await call_next(request)

        auth: AgentKeyAuthService = request.app.state.auth
        deps: Deps = request.app.state.deps
        api_key = extract_api_key(request)

        def _resolve():
            with deps.connection_factory.unit_of_work() as uow:
                return auth.resolve(uow, api_key)

        try:
            agent = await anyio.to_thread.run_sync(_resolve)
        except OktoNexusError as exc:
            return err(503, exc.code, exc.message)
        if agent is None:
            return err(
                401, "AUTH_FAILED", "Authentication failed: unknown or inactive api_key"
            )

        token = current_agent.set(agent)
        try:
            return await call_next(request)
        finally:
            current_agent.reset(token)


def create_http_mcp_server(deps: Deps) -> Any:
    """A FastMCP instance serving the SAME tool AND resource surface over
    streamable-http.

    Parity by construction: the exact ``register_tools`` /
    ``register_meta_tools`` / ``register_resources`` used by the stdio server run
    against this instance - there is no second table to drift (rule br_167701f9;
    verified by the parity test). ``register_resources`` is essential here: an
    agent connects over THIS HTTP transport, and the inline instructions point it
    at ``okto-nexus://reference/*`` docs (monitoring, preflight, target-grammar,
    tool-docs/*) that must therefore resolve on a ``resources/read``.
    """
    from mcp.server.fastmcp import FastMCP  # lazy: SDK only needed at serve time

    server = FastMCP(
        "okto-nexus",
        instructions=SERVER_INSTRUCTIONS,
        streamable_http_path="/",
        stateless_http=True,
    )
    register_tools(server, deps)
    register_meta_tools(server, deps)
    register_resources(server)
    return server


def ensure_operator_key(
    deps: Deps, auth: AgentKeyAuthService
) -> tuple[str, str] | None:
    """Cold-start bootstrap: guarantee at least one key exists.

    When NO agent holds a key yet (fresh install or a V1 store before
    `admin issue-keys`), register the ``operator`` agent and issue its key,
    returning ``(agent_id, plaintext)`` for the CLI to print ONCE. Returns
    ``None`` when any key already exists - never reissues silently (BR7).
    """
    with deps.connection_factory.unit_of_work() as uow:
        agents = deps.repos.agents
        if any(a.api_key_hash for a in agents.list(uow)):
            return None
        agents.upsert(uow, agent_id=OPERATOR_AGENT_ID, role="operator")
        plaintext = auth.issue_key(uow, agent_id=OPERATOR_AGENT_ID)
        return OPERATOR_AGENT_ID, plaintext


def build_app(deps: Deps, *, lock: ServeLock | None = None) -> FastAPI:
    """Assemble the serve application (REST + SSE + MCP mount + static)."""
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    observability = ObservabilityService(
        SqliteObservabilityQueries(), deps.clock, deps.config
    )
    # Runtime settings FIRST: stored (dashboard-managed) overrides must land on
    # deps.config BEFORE anything reads it - critically embedding_mode, which
    # bootstrap resolved from the un-overridden config. Without this ordering a
    # dashboard-set embedding_mode stayed inert across restarts (the capability
    # was resolved before its override was applied).
    settings_service = SettingsService(
        deps.config, deps.clock, detect_pinned_fields(deps.config)
    )
    with deps.connection_factory.unit_of_work() as uow:
        settings_service.apply_overrides(uow)
    # Re-resolve the embedding capability from the NOW-effective mode so a
    # stored embedding_mode (off/stub/local) actually takes effect. Cheap: the
    # real model is lazy-loaded (serve warms it separately). Skip when the
    # bootstrap-resolved mode already matches (keeps any test-injected value).
    if deps.embedding is None or deps.embedding.mode != deps.config.embedding_mode:
        deps.embedding = resolve_embedding_provider(deps.config.embedding_mode)
    embedding = deps.embedding
    # Semantic search (Frente 3): the resolved embedding capability gates both
    # the query provider and whether search answers at all. The vector store is
    # always present (built in bootstrap; constructed here defensively).
    if deps.repos.message_vectors is None:
        deps.repos.message_vectors = SqliteMessageVectorStore(deps.clock)
    search_service = MessageSearchService(
        connection_factory=deps.connection_factory,
        provider=embedding.provider,
        vectors=deps.repos.message_vectors,
        messages=deps.repos.messages,
        search_enabled=bool(embedding.search_enabled),
    )
    # Workspace overview + message analytics (serve-only). The tokenizer is the
    # real tiktoken o200k_base on a full serve build (resolve_tokenizer probes
    # it lazily; the encoding loads from the vendored blob on first count) and
    # the dependency-free heuristic only if tiktoken is somehow absent.
    observability_queries = SqliteObservabilityQueries()
    workspace_analytics = WorkspaceAnalyticsService(
        connection_factory=deps.connection_factory,
        queries=observability_queries,
        tokenizer=resolve_tokenizer().tokenizer,
        clock=deps.clock,
    )
    workspace_list = WorkspaceListService(
        connection_factory=deps.connection_factory,
        queries=observability_queries,
        workspaces=deps.repos.workspaces,
        observability=observability,
        clock=deps.clock,
        config=deps.config,
    )
    # Coordination health (I7): the SAME service class the MCP tool builds,
    # with the same collaborators - tool/REST payload parity by construction.
    workspace_health = HealthService(
        connection_factory=deps.connection_factory,
        queries=observability_queries,
        workspaces=deps.repos.workspaces,
        observability=observability,
        clock=deps.clock,
        config=deps.config,
    )

    mcp_server = create_http_mcp_server(deps)
    mcp_app = mcp_server.streamable_http_app()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        # Quiet a benign Windows ProactorEventLoop teardown race: when a client
        # RSTs a connection, asyncio's _call_connection_lost calls sock.shutdown
        # on the already-reset socket and the resulting ConnectionResetError
        # (WinError 10054) is logged at ERROR by the loop's default handler -
        # pure noise (the connection is already gone). Filter exactly that at
        # the loop level; everything else keeps default handling.
        loop = asyncio.get_running_loop()
        _prev_handler = loop.get_exception_handler()

        def _filter_conn_reset(active_loop, context):
            if isinstance(context.get("exception"), ConnectionResetError):
                return
            if _prev_handler is not None:
                _prev_handler(active_loop, context)
            else:
                active_loop.default_exception_handler(context)

        loop.set_exception_handler(_filter_conn_reset)

        # The mounted MCP sub-app's own lifespan never runs under a parent
        # FastAPI, so its session manager is driven from here (SDK-documented
        # mounting pattern). The lock heartbeat keeps takeover honest (D4).
        heartbeat_task: asyncio.Task | None = None
        if lock is not None:

            async def _beat() -> None:
                while True:
                    await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS / 2)
                    lock.heartbeat()

            heartbeat_task = asyncio.create_task(_beat())
        try:
            async with mcp_server.session_manager.run():
                yield
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat_task
            if lock is not None:
                lock.release()

    app = FastAPI(
        title="Okto Nexus",
        version="2.0",
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
    )

    # Safety net: NO unhandled exception may leave the API as a plain-text
    # 500 ("Internal Server Error" breaks every JSON client). Everything
    # becomes the documented envelope.
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc: Exception):
        return JSONResponse(
            {
                "ok": False,
                "error": {
                    "code": "INTERNAL",
                    "message": f"{type(exc).__name__}: {exc}",
                },
            },
            status_code=500,
        )

    app.state.deps = deps
    app.state.auth = auth
    app.state.observability = observability
    app.state.search = search_service
    app.state.settings_service = settings_service
    app.state.workspace_analytics = workspace_analytics
    app.state.workspace_list = workspace_list
    app.state.workspace_health = workspace_health
    app.state.sse_poll_seconds = 1.0  # TR7 fallback cadence (tests shrink it)
    app.state.sse_ping_seconds = 15.0
    # Same-machine trust for REST/dashboard; the serve CLI sets this to
    # False when bound beyond loopback (--host on the LAN -> key required).
    app.state.local_open = True

    app.add_middleware(ApiKeyAuthMiddleware)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:  # public liveness probe
        return ok({"status": "alive"})

    # Dashboard SPA (spec S2): the frontend build ships INSIDE the package
    # (frontend/ -> static/, the Pulse pattern) so installing okto-nexus
    # never requires Node. Falls back to a JSON index when no build exists
    # (e.g. a source checkout before `npm run build`).
    static_dir = Path(__file__).parent / "static"
    index_html = static_dir / "index.html"

    if index_html.is_file():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
        logos_dir = static_dir / "logos"
        if logos_dir.is_dir():
            app.mount("/logos", StaticFiles(directory=logos_dir), name="logos")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(index_html)

    else:

        @app.get("/")
        async def index() -> JSONResponse:
            return ok(
                {
                    "service": "okto-nexus",
                    "note": "dashboard build not present in this checkout",
                    "surfaces": {
                        "mcp": "/mcp",
                        "api": "/api/v1",
                        "docs": "/api/v1/docs",
                    },
                }
            )

    app.include_router(routes.build_router(), prefix="/api/v1")
    app.include_router(stream.build_router(), prefix="/api/v1")
    app.mount("/mcp", mcp_app)
    return app
