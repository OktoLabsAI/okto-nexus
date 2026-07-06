"""REST surface: observability read-model + agent/key management (C5/C6).

Every handler runs the sync application code in a worker thread
(``anyio.to_thread``) over a per-request unit of work - the SQLite repos are
untouched by async concerns (rule BR2). Responses use the documented
``{ok, data | error:{code,message}}`` envelope (TR8).
"""

from __future__ import annotations

import importlib.metadata
from typing import Any

import anyio.to_thread
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from ....config import FEATURE_FLAG_FIELDS
from ....application.capabilities import CapabilityCatalogService
from ....application.comm_preset_catalog import CommPresetCatalogService
from ....application.governance import GovernanceService
from ....application.memory import MemoryService
from ....application.observability import DEFAULT_GRAPH_WINDOW_HOURS
from ....application.policy_catalog import PolicyCatalogService
from ....application.search import EmbeddingsUnavailable
from ....application.tags import TagCatalogService
from ....application.workspace_analytics import DEFAULT_WINDOW, is_valid_window
from ....domain.health import DEFAULT_WINDOW as HEALTH_DEFAULT_WINDOW
from ....domain.health import is_valid_window as is_valid_health_window
from ....domain.approvals import (
    OPERATOR_AGENT_ID,
    is_reserved_agent_id,
    validate_status_filter,
)
from ....domain.base import new_id
from ....domain.permissions import (
    BUILTIN_PRESETS,
    PERMISSION_DESCRIPTIONS,
    PERMISSION_REGISTRY,
    builtin_preset,
    validate_permission_flags,
)
from ....domain.routing import normalize_capabilities
from ....domain.tag_selector import validate_comm_scope, validate_tags
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception
from ..mcp.tools.handoff import build_service as _build_handoff_service
from ..mcp.tools.messages import build_service as _build_message_service
from .identity_ctx import get_authenticated_agent


def _ok(data: Any) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data})


def _err(
    status: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse({"ok": False, "error": error}, status_code=status)


def _map_error(exc: OktoNexusError) -> JSONResponse:
    status = {
        ErrorCode.NOT_FOUND: 404,
        # A handoff that exists only in ANOTHER workspace is absent from the
        # addressed one - the REST resource does not exist there.
        ErrorCode.WORKSPACE_MISMATCH: 404,
        ErrorCode.VALIDATION_ERROR: 422,
        ErrorCode.PERMISSION_DENIED: 403,
        ErrorCode.POLICY_DENIED: 403,
        ErrorCode.QUOTA_EXCEEDED: 429,
        ErrorCode.TAG_IN_USE: 409,
        ErrorCode.CAPABILITY_IN_USE: 409,
        ErrorCode.POLICY_IN_USE: 409,
        ErrorCode.COMM_PRESET_IN_USE: 409,
        ErrorCode.CONFLICT: 409,
        ErrorCode.INVALID_TRANSITION: 409,
        # Handoff dependencies (I5, spec 6522ad1f): DEFENSIVE mappings - the
        # V1 surface of both codes is MCP-only (REST has no handoff create/
        # claim), but any future route reusing the service maps canonically:
        # an unmet dependency set is a state conflict; unknown dependency ids
        # are an unprocessable request.
        ErrorCode.DEPENDENCY_NOT_MET: 409,
        ErrorCode.DEPENDENCY_NOT_FOUND: 422,
        ErrorCode.DB_ERROR: 503,
    }.get(exc.code, 500)
    # TAG_IN_USE / CAPABILITY_IN_USE carry a NORMATIVE details payload
    # (key|capability / total_uses / uses) the Registry renders; POLICY_IN_USE
    # carries {policy_id, agents} (spec 80624c1a BR5 - who must detach first); the
    # governance denials carry {policy_id, action, limit_kind, limit?,
    # window?, current?} (spec ffef15bf - byte-parity with the stdio
    # envelope); an approval-decision CONFLICT carries the surviving first
    # decision ({approval_id, status, decided_by, decided_at} - spec
    # 2948b2a2 AC6); the I5 dependency refusals carry their aggregate
    # counts ({handoff_id, pending, failed} - BR8: never ids) / the missing
    # id list ({missing}); other codes keep the lean envelope.
    details = (
        exc.details
        if exc.code
        in (
            ErrorCode.TAG_IN_USE,
            ErrorCode.CAPABILITY_IN_USE,
            ErrorCode.POLICY_IN_USE,
            ErrorCode.COMM_PRESET_IN_USE,
            ErrorCode.POLICY_DENIED,
            ErrorCode.QUOTA_EXCEEDED,
            ErrorCode.CONFLICT,
            ErrorCode.DEPENDENCY_NOT_MET,
            ErrorCode.DEPENDENCY_NOT_FOUND,
        )
        else None
    )
    return _err(status, str(exc.code), exc.message, details)


async def _run(request: Request, fn, *, write: bool = True):
    """Execute ``fn(uow)`` in a worker thread with a fresh UoW.

    ``write`` defaults to True (``BEGIN IMMEDIATE``) for the mutating routes.
    Read-only routes MUST go through :func:`_read` (``write=False``): a
    DEFERRED WAL snapshot read never queues behind the agents' writers under
    the busy-timeout, which is what caused the dashboard's intermittent
    multi-second stalls (empty panels) while the bus was busy.
    """
    deps = request.app.state.deps

    def _call():
        with deps.connection_factory.unit_of_work(write=write) as uow:
            return fn(uow)

    return await anyio.to_thread.run_sync(_call)


async def _read(request: Request, fn):
    """``_run`` for a read-only route: a deferred WAL snapshot (no writer queue)."""
    return await _run(request, fn, write=False)


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #
# Migration 024: display color is a #RGB or #RRGGBB hex string (or null =
# auto-by-identity). Validated declaratively so a malformed value is a 422
# before anything persists; null passes (the reset-to-auto sentinel).
_COLOR_PATTERN = r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$"


class CreateAgentBody(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    role: str | None = None
    capabilities: dict[str, Any] | list[str] | None = None
    metadata: dict[str, Any] | None = None
    # Permissions (migration 011): a preset to copy flags from and/or an
    # explicit flags object (explicit flags win - the Pulse semantics).
    preset_id: str | None = None
    permissions: dict[str, Any] | None = None
    # Display color (migration 024): null = auto-by-identity.
    color: str | None = Field(default=None, pattern=_COLOR_PATTERN)


class UpdateAgentBody(BaseModel):
    role: str | None = None
    capabilities: dict[str, Any] | list[str] | None = None
    metadata: dict[str, Any] | None = None
    is_active: bool | None = None
    preset_id: str | None = None
    permissions: dict[str, Any] | None = None
    # Tag scoping (migration 013): both are full-overwrite when present in
    # the payload (explicit null resets). Values must be registered in the
    # central tag catalog (fail-closed).
    tags: dict[str, Any] | None = None
    comm_scope: dict[str, Any] | None = None
    # Display color (migration 024): full-overwrite when present in the
    # payload (explicit null resets to auto-by-identity).
    color: str | None = Field(default=None, pattern=_COLOR_PATTERN)


class PresetBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    flags: dict[str, Any]


class PresetPatchBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    flags: dict[str, Any] | None = None


class TagKeyBody(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    description: str | None = None


class TagValueBody(BaseModel):
    value: str = Field(min_length=1, max_length=100)
    description: str | None = None


class CapabilityBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class DecisionBody(BaseModel):
    decision: str = Field(min_length=1)
    justification: str | None = None


class SteeringBody(BaseModel):
    workspace: str = Field(min_length=1)
    to_agent_id: str = Field(min_length=1)
    subject: str | None = None
    body: str = Field(min_length=1)


class VerifyHandoffBody(BaseModel):
    # Grammar (pass|fail lowercase, feedback only with fail, <=2000 chars) is
    # the domain's validate_verdict - the route just forwards; violations map
    # to 422 through _map_error.
    verdict: str = Field(min_length=1)
    feedback: str | None = None


def _tag_service(deps) -> TagCatalogService:
    return TagCatalogService(catalog=deps.repos.tag_catalog, agents=deps.repos.agents)


def _capability_service(deps) -> CapabilityCatalogService:
    return CapabilityCatalogService(
        catalog=deps.repos.capability_catalog, agents=deps.repos.agents
    )


#: The closed field set of a governance policy payload (spec ffef15bf).
_POLICY_FIELDS = {
    "subject_kind",
    "subject_value",
    "action",
    "limit_kind",
    "limit_value",
    "window",
    "enabled",
}


def _governance_service(deps) -> GovernanceService:
    # The CRUD methods open their OWN unit of work (self._cf), so the
    # governance handlers call them straight through anyio.to_thread - never
    # inside _run/_read, which would nest a second transaction.
    return GovernanceService(
        connection_factory=deps.connection_factory,
        governance=deps.repos.governance,
        clock=deps.clock,
        config=deps.config,
        agents=deps.repos.agents,
        capability_catalog=deps.repos.capability_catalog,
        event_emitter=deps.event_emitter,
        policies=getattr(deps.repos, "policies", None),
        policy_bindings=getattr(deps.repos, "policy_bindings", None),
    )


#: The closed field set of a policy HEADER payload (POST/PATCH /policies).
_POLICY_HEADER_FIELDS = {"name", "description"}


def _policy_catalog_service(deps) -> PolicyCatalogService:
    # Named-policy CRUD (spec 80624c1a FR9). Like _governance_service, every
    # method opens its OWN unit of work, so the handlers call straight through
    # anyio.to_thread - never nested inside _run/_read. Bootstrap always wires
    # both repos (server.py), so no None-fallback is needed.
    return PolicyCatalogService(
        connection_factory=deps.connection_factory,
        policies=deps.repos.policies,
        policy_bindings=deps.repos.policy_bindings,
        agents=deps.repos.agents,
    )


#: The closed field set of a preset HEADER payload (POST/PATCH /comm-presets).
_COMM_PRESET_HEADER_FIELDS = {"name", "description"}


def _comm_preset_catalog_service(deps) -> "CommPresetCatalogService":
    # Communication-preset CRUD + single-source binding (spec 6f961722). Like
    # _policy_catalog_service, every method opens its OWN unit of work, so the
    # handlers call straight through anyio.to_thread - never nested inside
    # _run/_read. Bootstrap always wires both repos (server.py build_repos).
    return CommPresetCatalogService(
        connection_factory=deps.connection_factory,
        presets=deps.repos.comm_presets,
        comm_bindings=deps.repos.comm_bindings,
        agents=deps.repos.agents,
    )


def _memory_service(deps) -> MemoryService:
    # browse/get_raw/delete_memory open their OWN unit of work (self._cf), so
    # the memory handlers call them straight through anyio.to_thread - never
    # inside _run/_read, which would nest a second transaction. The embedding
    # capability resolved at bootstrap is unpacked into plain values (the
    # tools/memory.py wiring, kept in lockstep).
    embedding = getattr(deps, "embedding", None)
    return MemoryService(
        connection_factory=deps.connection_factory,
        memories=deps.repos.memories,
        workspaces=deps.repos.workspaces,
        agents=deps.repos.agents,
        sessions=deps.repos.sessions,
        event_emitter=deps.event_emitter,
        clock=deps.clock,
        config=deps.config,
        embedding_provider=embedding.provider if embedding is not None else None,
        memory_vectors=deps.repos.memory_vectors,
        semantic_search_enabled=bool(
            embedding is not None and embedding.search_enabled
        ),
    )


def _approval_service(deps):
    """The PROCESS-WIDE ApprovalService built in bootstrap (spec 2948b2a2).

    Never constructed here: the executors the messages/handoff slices
    registered on THIS instance are what ``decide`` re-executes through - a
    fresh instance would approve into a "no executor registered" error.
    """
    service = getattr(deps, "approvals", None)
    if service is None:  # pragma: no cover - build_app always registers tools
        raise OktoNexusError(
            ErrorCode.INTERNAL_ERROR,
            "The approval service is not wired on this process.",
            {},
        )
    return service


def _require_operator() -> None:
    """Operator-only gate for the HITL surfaces (FR8/BR4).

    Admits the same-machine trust path (loopback + ``local_open``: the
    middleware let the request through WITHOUT a key, so no agent is bound)
    and the authenticated ``operator`` agent; any other authenticated agent
    is refused - agents never read each other's intercepted content.
    """
    agent = get_authenticated_agent()
    if agent is None:
        return
    if agent.agent_id != OPERATOR_AGENT_ID:
        raise OktoNexusError(
            ErrorCode.PERMISSION_DENIED,
            "This surface is operator-only: authenticate as the operator "
            "or call from the serve machine (loopback).",
            {"agent_id": agent.agent_id, "required": OPERATOR_AGENT_ID},
        )


def _normalise_capabilities(value: dict | list | None) -> dict | None:
    # The V1 store models capabilities as a JSON object; accept the common
    # list spelling from clients and normalise it to {name: true}.
    if isinstance(value, list):
        return {str(item): True for item in value}
    return value


def _ensure_capabilities_registered(deps, uow, capabilities: Any) -> None:
    """Fail-closed EXISTENCE gate for an agent payload (migration 014).

    ``normalize_capabilities`` validates FORM (domain); every announced name
    must then already exist in the central catalog or the write is rejected
    with ``VALIDATION_ERROR`` listing the missing names.
    """
    announced = normalize_capabilities(capabilities)
    if announced:
        _capability_service(deps).ensure_registered(
            uow, announced, field="capabilities"
        )


def _preset_flags(deps, uow, preset_id: str) -> dict[str, Any]:
    """Resolve a preset id (builtin or custom) to its flags, or NOT_FOUND."""
    builtin = builtin_preset(preset_id)
    if builtin is not None:
        return builtin["flags"]
    custom = deps.repos.presets.get(uow, preset_id)
    if custom is None:
        raise OktoNexusError(
            ErrorCode.NOT_FOUND,
            f"preset_id '{preset_id}' does not reference a preset.",
            {"preset_id": preset_id},
        )
    return custom.flags


def _resolve_permission_payload(
    deps, uow, *, preset_id: str | None, permissions: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve (flags, preset_id) to store - the Pulse semantics.

    Explicit ``permissions`` win (validated against the registry); otherwise a
    ``preset_id`` copies the preset's flags; neither -> ``(None, None)`` =
    unrestricted default-allow.
    """
    if permissions is not None:
        return validate_permission_flags(permissions), preset_id
    if preset_id:
        return _preset_flags(deps, uow, preset_id), preset_id
    return None, None


def _public_preset(preset) -> dict[str, Any]:
    return {
        "preset_id": preset.preset_id,
        "name": preset.name,
        "description": preset.description,
        "is_builtin": False,
        "flags": preset.flags,
    }


def build_router() -> APIRouter:
    router = APIRouter()

    # ------------------------------------------------------------------ #
    # Meta
    # ------------------------------------------------------------------ #
    @router.get("/info")
    async def info(request: Request) -> JSONResponse:
        deps = request.app.state.deps

        def _info(uow):
            row = uow.connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()
            return int(row[0]) if row and row[0] is not None else 0

        schema_version = await _read(request, _info)
        try:
            package_version = importlib.metadata.version("okto-nexus")
        except importlib.metadata.PackageNotFoundError:
            package_version = "dev"
        return _ok(
            {
                "service": "okto-nexus",
                "package_version": package_version,
                "schema_version": schema_version,
                "trust_mode": deps.config.trust_mode,
                # Set by `serve --project-root`; the dashboard opens scoped
                # to this workspace by default (spec S2 AC1).
                "default_workspace_id": getattr(
                    request.app.state, "default_workspace_id", None
                ),
                # Live effective feature flags (mirrors the MCP nexus_info.features)
                # so the dashboard can self-gate opt-in surfaces (e.g. the I8
                # event-log export button reads features.feature_replay).
                "features": {
                    name: bool(getattr(deps.config, name))
                    for name in FEATURE_FLAG_FIELDS
                },
            }
        )

    # ------------------------------------------------------------------ #
    # Observability (read-only, FR5)
    # ------------------------------------------------------------------ #
    @router.get("/graph")
    async def graph(
        request: Request,
        workspace: str | None = None,
        window_hours: int = DEFAULT_GRAPH_WINDOW_HOURS,
    ) -> JSONResponse:
        observability = request.app.state.observability
        workspace_id = None if workspace in (None, "", "all") else workspace
        try:
            snapshot = await _read(
                request,
                lambda uow: observability.graph_snapshot(
                    uow, workspace_id=workspace_id, window_hours=window_hours
                ),
            )
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(snapshot)

    @router.get("/messages")
    async def messages(
        request: Request,
        workspace: str | None = None,
        agent: str | None = None,
        channel: str | None = None,
        lane: str | None = None,
        since: str | None = None,
        until: str | None = None,
        page: int = 1,
        page_size: int = 50,
        peer: str | None = None,
        from_agent: str | None = None,
        to_agent: str | None = None,
        undelivered: bool = False,
        include_body: bool = False,
    ) -> JSONResponse:
        observability = request.app.state.observability
        try:
            data = await _read(
                request,
                lambda uow: observability.messages_history(
                    uow,
                    workspace_id=workspace,
                    agent_id=agent,
                    channel_id=channel,
                    lane=lane,
                    since_iso=since,
                    until_iso=until,
                    page=page,
                    page_size=page_size,
                    peer_id=peer,
                    from_agent_id=from_agent,
                    to_agent_id=to_agent,
                    undelivered_only=undelivered,
                    include_body=include_body,
                ),
            )
        except ValueError as exc:
            return _err(422, "INVALID_PARAM", str(exc))
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(data)

    @router.get("/messages/search")
    async def messages_search(
        request: Request, q: str | None = None, k: str | None = None
    ) -> JSONResponse:
        """Semantic search over message content (cosine over embeddings).

        ``q`` is the query text (required); ``k`` defaults to 10 and is clamped
        to ``[1, 50]``. Read-only. Without a usable embedding provider the
        response is ``503 EMBEDDINGS_UNAVAILABLE`` and the rest of the system is
        unaffected. ``k`` is taken as a string so an out-of-range value is
        CLAMPED (not a framework 422); a non-integer ``k`` is a VALIDATION_ERROR.
        """
        search = request.app.state.search

        def _search():
            return search.search(query=q, k=k)

        try:
            data = await anyio.to_thread.run_sync(_search)
        except EmbeddingsUnavailable as exc:
            return _err(503, "EMBEDDINGS_UNAVAILABLE", str(exc))
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(data)

    @router.get("/conversations/peers")
    async def conversation_peers(request: Request, agent: str) -> JSONResponse:
        """The chat's peer picker: per-peer counts + last activity (O(peers))."""
        observability = request.app.state.observability
        try:
            data = await _read(
                request,
                lambda uow: observability.conversation_peers(uow, agent_id=agent),
            )
        except ValueError as exc:
            return _err(422, "INVALID_PARAM", str(exc))
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(data)

    @router.get("/handoffs")
    async def handoffs(
        request: Request, workspace: str | None = None, status: str | None = None
    ) -> JSONResponse:
        observability = request.app.state.observability
        try:
            rows = await _read(
                request,
                lambda uow: observability.handoffs(
                    uow, workspace_id=workspace, status=status
                ),
            )
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"items": rows})

    @router.get("/sessions")
    async def sessions(
        request: Request, workspace: str | None = None, status: str | None = None
    ) -> JSONResponse:
        observability = request.app.state.observability
        try:
            rows = await _read(
                request,
                lambda uow: observability.sessions(
                    uow, workspace_id=workspace, status=status
                ),
            )
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"items": rows})

    @router.get("/events")
    async def events(
        request: Request,
        after: int = 0,
        workspace: str | None = None,
        stream: str | None = None,
        type: str | None = None,
        agent: str | None = None,
        trace: str | None = None,
        limit: int = 100,
    ) -> JSONResponse:
        # type/agent/trace are optional equality filters (FR1/I1); omitting
        # them keeps the response byte-for-byte the prior behaviour (AC7).
        observability = request.app.state.observability
        try:
            rows = await _read(
                request,
                lambda uow: observability.events_page(
                    uow,
                    cursor=after,
                    workspace_id=workspace,
                    stream=stream,
                    limit=limit,
                    type_=type,
                    actor_agent_id=agent,
                    trace_id=trace,
                ),
            )
        except ValueError as exc:
            return _err(422, "INVALID_PARAM", str(exc))
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(
            {"items": rows, "next_cursor": rows[-1]["event_id"] if rows else after}
        )

    @router.get("/workspaces/{workspace_id}/events/export")
    async def export_events(
        request: Request,
        workspace_id: str,
        stream: str | None = None,
        trace: str | None = None,
        since_event_id: int = 0,
        until_event_id: int | None = None,
    ) -> Response:
        """Download the workspace event log as an NDJSON replay stream (I8).

        Two fail-closed gates BEFORE any store access: the ``feature_replay``
        opt-in (BR1 - a disabled hub answers 422 without touching SQLite) and
        the operator-only check (BR2 - agents never read the raw cross-agent
        log). The slice is then drained over ONE read snapshot in a worker
        thread and streamed as an attachment; the bytes are identical to the
        CLI ``admin export`` modulo the manifest's ``generated_at``.
        """
        deps = request.app.state.deps
        observability = request.app.state.observability

        # Gate 1: opt-in. VALIDATION_ERROR maps to 422 but its details are NOT
        # propagated (see _map_error), so the flag name rides the message TEXT.
        if not bool(getattr(deps.config, "feature_replay", False)):
            return _err(
                422,
                ErrorCode.VALIDATION_ERROR.value,
                "Event log export is disabled: enable feature_replay "
                "(OKTO_NEXUS_FEATURE_REPLAY=true) on the hub to use this "
                "endpoint.",
            )

        # Gate 2: operator-only (loopback or the operator agent).
        try:
            _require_operator()
        except OktoNexusError as exc:
            return _map_error(exc)

        from ....application.replay import ReplayExportService

        service = ReplayExportService(observability, deps.config)
        generated_at = deps.clock.now_iso()

        def _collect() -> list[str]:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                return list(
                    service.export_lines(
                        uow,
                        workspace_id=workspace_id,
                        generated_at=generated_at,
                        stream=stream,
                        trace_id=trace,
                        since_event_id=since_event_id,
                        until_event_id=until_event_id,
                    )
                )

        try:
            lines = await anyio.to_thread.run_sync(_collect)
        except ValueError as exc:
            return _err(422, "INVALID_PARAM", str(exc))
        except OktoNexusError as exc:
            return _map_error(exc)

        filename = f"okto-nexus-events-{workspace_id[:8]}.ndjson"

        def _stream():
            for line in lines:
                yield line + "\n"

        return StreamingResponse(
            _stream(),
            media_type="application/x-ndjson",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    # ------------------------------------------------------------------ #
    # Workspaces (operator overview + message-distribution analytics)
    # ------------------------------------------------------------------ #
    @router.get("/workspaces")
    async def workspaces(request: Request) -> JSONResponse:
        """Rich list of EVERY known workspace: identity + 24h rollups + health.

        Read-only operator surface (not the inter-agent visibility predicate).
        ``root_realpath`` is shown only when the ``expose_workspace_path``
        setting is on (default off -> redacted). The service owns its own
        read-only unit of work, so this runs straight on a worker thread.
        """
        service = request.app.state.workspace_list
        deps = request.app.state.deps
        default_ws = getattr(request.app.state, "default_workspace_id", None)
        expose = bool(getattr(deps.config, "expose_workspace_path", False))

        def _list():
            return service.list_workspaces(
                default_workspace_id=default_ws, expose_path=expose
            )

        try:
            items = await anyio.to_thread.run_sync(_list)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"workspaces": items})

    @router.get("/workspaces/{workspace_id}/analytics")
    async def workspace_analytics(
        request: Request, workspace_id: str, window: str = DEFAULT_WINDOW
    ) -> JSONResponse:
        """Message distribution over time x size(TOKENS), by sender, for ONE workspace.

        ``window`` is one of 24h/7d/30d (default 24h); anything else is a
        canonical ``INVALID_WINDOW`` (400). An unknown ``workspace_id`` is NOT
        an error: it returns 200 with zeroed buckets/summary (a workspace may
        exist with no messages). The analytics service owns its read uow.
        """
        if not is_valid_window(window):
            return _err(400, "INVALID_WINDOW", "window must be one of 24h, 7d, 30d")
        service = request.app.state.workspace_analytics

        def _analytics():
            return service.analytics(workspace_id=workspace_id, window=window)

        try:
            data = await anyio.to_thread.run_sync(_analytics)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(data)

    @router.get("/workspaces/{workspace_id}/health")
    async def workspace_health(
        request: Request, workspace_id: str, window: str = HEALTH_DEFAULT_WINDOW
    ) -> JSONResponse:
        """Windowed coordination-health report for ONE workspace (I7).

        Operator surface, NOT gated by ``feature_health`` (the I6 precedent:
        the flag gates the agent-facing tool only). ``window`` is one of
        1h/24h/7d (default 24h); anything else is a canonical
        ``INVALID_WINDOW`` (400, analytics parity). An unknown
        ``workspace_id`` IS a 404 here - health reports on a workspace that
        exists (unlike analytics' zeroed 200, a health verdict about a ghost
        would be misinformation). The service owns its read uow, so this runs
        straight on a worker thread; the ``data`` is byte-identical to the
        ``coordination_health`` tool's.
        """
        if not is_valid_health_window(window):
            return _err(400, "INVALID_WINDOW", "window must be one of 1h, 24h, 7d")
        service = request.app.state.workspace_health

        def _health():
            return service.health(workspace_id=workspace_id, window=window)

        try:
            data = await anyio.to_thread.run_sync(_health)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(data)

    @router.get("/events/types")
    async def event_types(
        request: Request, workspace: str | None = None
    ) -> JSONResponse:
        # Distinct event types (FR2) to populate the dashboard type filter.
        observability = request.app.state.observability
        try:
            items = await _read(
                request,
                lambda uow: observability.event_types(uow, workspace_id=workspace),
            )
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"items": items})

    # ------------------------------------------------------------------ #
    # Agent & key management (FR4/FR9)
    # ------------------------------------------------------------------ #
    @router.post("/agents")
    async def create_agent(request: Request, body: CreateAgentBody) -> JSONResponse:
        deps = request.app.state.deps
        auth = request.app.state.auth

        def _create(uow):
            agents = deps.repos.agents
            # Reserved operator identity (spec 2948b2a2 BR4, fail-closed, no
            # flag): checked BEFORE the exists-lookup so every spelling of
            # the reserved name (case/whitespace variants included) is a 422,
            # never a 409 or a fresh look-alike row.
            if is_reserved_agent_id(body.agent_id):
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"agent_id '{body.agent_id}' is reserved for the human "
                    "operator and cannot be created.",
                    {"agent_id": body.agent_id, "reserved": OPERATOR_AGENT_ID},
                )
            if agents.get(uow, body.agent_id) is not None:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    "agent already exists; use PATCH to update or "
                    "regenerate-key to rotate its key.",
                    {"agent_id": body.agent_id},
                )
            flags, preset_id = _resolve_permission_payload(
                deps, uow, preset_id=body.preset_id, permissions=body.permissions
            )
            capabilities = _normalise_capabilities(body.capabilities)
            # Capability catalog gate (migration 014): fail-closed BEFORE the
            # upsert so nothing persists on an unregistered name.
            _ensure_capabilities_registered(deps, uow, capabilities)
            agent = agents.upsert(
                uow,
                agent_id=body.agent_id,
                role=body.role,
                capabilities=capabilities,
                metadata=body.metadata,
                color=body.color,
            )
            if flags is not None or preset_id is not None:
                agents.set_permissions(
                    uow,
                    agent_id=agent.agent_id,
                    permissions=flags,
                    preset_id=preset_id,
                )
            plaintext = auth.issue_key(uow, agent_id=agent.agent_id)
            return agents.get(uow, agent.agent_id), plaintext

        try:
            _require_operator()
            agent, plaintext = await _run(request, _create)
        except OktoNexusError as exc:
            if (
                exc.code == ErrorCode.VALIDATION_ERROR
                and "already exists" in exc.message
            ):
                return _err(409, "CONFLICT", exc.message)
            return _map_error(exc)
        # The ONLY surface that ever carries the plaintext (BR7/AC3).
        return _ok(
            {
                "agent_id": agent.agent_id,
                "role": agent.role,
                "is_active": True,
                "created_at": agent.created_at,
                "preset_id": agent.preset_id,
                "permissions": agent.permissions,
                "color": agent.color,
                "api_key": plaintext,
            }
        )

    @router.get("/agents")
    async def list_agents(request: Request) -> JSONResponse:
        deps = request.app.state.deps

        def _list(uow):
            return [_public_agent(agent) for agent in deps.repos.agents.list(uow)]

        return _ok({"items": await _read(request, _list)})

    @router.get("/agents/{agent_id}")
    async def get_agent(request: Request, agent_id: str) -> JSONResponse:
        deps = request.app.state.deps
        agent = await _read(request, lambda uow: deps.repos.agents.get(uow, agent_id))
        if agent is None:
            return _err(404, "NOT_FOUND", "agent not found")
        return _ok(_public_agent(agent))

    @router.patch("/agents/{agent_id}")
    async def update_agent(
        request: Request, agent_id: str, body: UpdateAgentBody
    ) -> JSONResponse:
        deps = request.app.state.deps
        auth = request.app.state.auth

        def _update(uow):
            agents = deps.repos.agents
            existing = agents.get(uow, agent_id)
            if existing is None:
                return None
            capabilities = _normalise_capabilities(body.capabilities)
            # Capability catalog gate (migration 014): fail-closed BEFORE the
            # upsert so nothing persists on an unregistered name.
            _ensure_capabilities_registered(deps, uow, capabilities)
            agents.upsert(
                uow,
                agent_id=agent_id,
                role=body.role,
                capabilities=capabilities,
                metadata=body.metadata,
            )
            if body.is_active is not None:
                auth.set_active(uow, agent_id=agent_id, is_active=body.is_active)
            # Permission semantics (the Pulse AgentUpdate contract):
            # * permissions in the payload -> custom flags (validated); the
            #   preset reference is whatever the payload says (or kept);
            # * preset_id alone -> RESET the flags from that preset;
            # * explicit preset_id null -> reset to unrestricted.
            sent = body.model_fields_set
            if "permissions" in sent:
                if body.permissions is None:
                    # Explicit null = reset to unrestricted.
                    agents.set_permissions(
                        uow, agent_id=agent_id, permissions=None, preset_id=None
                    )
                else:
                    agents.set_permissions(
                        uow,
                        agent_id=agent_id,
                        permissions=validate_permission_flags(body.permissions),
                        preset_id=(
                            body.preset_id
                            if "preset_id" in sent
                            else existing.preset_id
                        ),
                    )
            elif "preset_id" in sent:
                if body.preset_id:
                    agents.set_permissions(
                        uow,
                        agent_id=agent_id,
                        permissions=_preset_flags(deps, uow, body.preset_id),
                        preset_id=body.preset_id,
                    )
                else:
                    agents.set_permissions(
                        uow, agent_id=agent_id, permissions=None, preset_id=None
                    )
            # Tag scoping (migration 013): FORM via the domain grammar,
            # EXISTENCE via the central catalog (fail-closed), then a full
            # overwrite (explicit null resets). Nothing unregistered persists.
            if "tags" in sent:
                tags = validate_tags(body.tags)
                _tag_service(deps).ensure_registered(uow, tags, field="tags")
                agents.set_tags(uow, agent_id=agent_id, tags=tags)
            if "comm_scope" in sent:
                scope = validate_comm_scope(body.comm_scope)
                if scope is not None:
                    service = _tag_service(deps)
                    for direction in ("outbound", "inbound"):
                        service.ensure_registered(
                            uow,
                            scope.get(direction),
                            field=f"comm_scope.{direction}",
                        )
                agents.set_comm_scope(uow, agent_id=agent_id, comm_scope=scope)
            # Display color (migration 024): full overwrite when present in the
            # payload (explicit null resets to auto-by-identity). Format is
            # already validated by the request model.
            if "color" in sent:
                agents.set_color(uow, agent_id=agent_id, color=body.color)
            return agents.get(uow, agent_id)

        try:
            _require_operator()
            agent = await _run(request, _update)
        except OktoNexusError as exc:
            return _map_error(exc)
        if agent is None:
            return _err(404, "NOT_FOUND", "agent not found")
        return _ok(_public_agent(agent))

    @router.post("/agents/{agent_id}/regenerate-key")
    async def regenerate_key(request: Request, agent_id: str) -> JSONResponse:
        deps = request.app.state.deps
        auth = request.app.state.auth

        def _rotate(uow):
            return auth.issue_key(uow, agent_id=agent_id)

        try:
            _require_operator()
            plaintext = await _run(request, _rotate)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(
            {
                "agent_id": agent_id,
                "api_key": plaintext,  # new plaintext, shown exactly once
                "rotated_at": deps.clock.now_iso(),
            }
        )

    @router.delete("/agents/{agent_id}")
    async def delete_agent(request: Request, agent_id: str) -> JSONResponse:
        deps = request.app.state.deps
        auth = request.app.state.auth

        def _delete(uow):
            removed = deps.repos.agents.delete(uow, agent_id=agent_id)
            if removed:
                auth.invalidate_agent(agent_id)
            return removed

        try:
            _require_operator()
            removed = await _run(request, _delete)
        except OktoNexusError as exc:
            return _map_error(exc)
        if not removed:
            return _err(404, "NOT_FOUND", "agent not found")
        return _ok({"agent_id": agent_id, "deleted": True})

    # ------------------------------------------------------------------ #
    # Permission presets (migration 011): built-ins from code (read-only)
    # + operator-authored custom presets (CRUD).
    # ------------------------------------------------------------------ #
    @router.get("/presets")
    async def list_presets(request: Request) -> JSONResponse:
        deps = request.app.state.deps

        def _list(uow):
            return [_public_preset(p) for p in deps.repos.presets.list(uow)]

        try:
            custom = await _read(request, _list)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(
            {
                "items": [dict(p) for p in BUILTIN_PRESETS] + custom,
                # The registry + descriptions let the dashboard build the
                # flags editor without duplicating the catalogue.
                "registry": PERMISSION_REGISTRY,
                "descriptions": PERMISSION_DESCRIPTIONS,
            }
        )

    @router.post("/presets")
    async def create_preset(request: Request, body: PresetBody) -> JSONResponse:
        deps = request.app.state.deps

        def _create(uow):
            for builtin in BUILTIN_PRESETS:
                if builtin["name"].lower() == body.name.strip().lower():
                    raise OktoNexusError(
                        ErrorCode.VALIDATION_ERROR,
                        f"'{body.name}' is a built-in preset name; pick another.",
                        {"name": body.name},
                    )
            return deps.repos.presets.create(
                uow,
                preset_id=new_id("prs"),
                name=body.name.strip(),
                description=body.description,
                flags=validate_permission_flags(body.flags),
            )

        try:
            _require_operator()
            preset = await _run(request, _create)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(_public_preset(preset))

    @router.patch("/presets/{preset_id}")
    async def update_preset(
        request: Request, preset_id: str, body: PresetPatchBody
    ) -> JSONResponse:
        deps = request.app.state.deps
        if builtin_preset(preset_id) is not None:
            return _err(
                403,
                "PERMISSION_DENIED",
                "Built-in presets are read-only; clone them into a custom preset.",
            )

        def _update(uow):
            sent = body.model_fields_set
            return deps.repos.presets.update(
                uow,
                preset_id=preset_id,
                name=body.name.strip() if body.name else None,
                description=(
                    body.description if "description" in sent else "__unset__"
                ),
                flags=(
                    validate_permission_flags(body.flags)
                    if body.flags is not None
                    else None
                ),
            )

        try:
            _require_operator()
            preset = await _run(request, _update)
        except OktoNexusError as exc:
            return _map_error(exc)
        if preset is None:
            return _err(404, "NOT_FOUND", "preset not found")
        return _ok(_public_preset(preset))

    @router.delete("/presets/{preset_id}")
    async def delete_preset(request: Request, preset_id: str) -> JSONResponse:
        deps = request.app.state.deps
        if builtin_preset(preset_id) is not None:
            return _err(403, "PERMISSION_DENIED", "Built-in presets cannot be deleted.")

        def _delete(uow):
            removed = deps.repos.presets.delete(uow, preset_id=preset_id)
            if removed:
                # Agents keep their materialised flags; only the dangling
                # preset REFERENCE is cleared (flags stay enforced as-is).
                uow.connection.execute(
                    "UPDATE agents SET preset_id = NULL WHERE preset_id = ?",
                    (preset_id,),
                )
            return removed

        try:
            _require_operator()
            removed = await _run(request, _delete)
        except OktoNexusError as exc:
            return _map_error(exc)
        if not removed:
            return _err(404, "NOT_FOUND", "preset not found")
        return _ok({"preset_id": preset_id, "deleted": True})

    # ------------------------------------------------------------------ #
    # Tag catalog (migration 013): the central, fail-closed tag registry.
    # Operator-only surface backing the dashboard Tag Registry screen.
    # ------------------------------------------------------------------ #
    @router.get("/tags")
    async def list_tags(request: Request) -> JSONResponse:
        deps = request.app.state.deps
        service = _tag_service(deps)
        try:
            items = await _read(request, lambda uow: service.snapshot(uow))
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"items": items})

    @router.post("/tags")
    async def create_tag_key(request: Request, body: TagKeyBody) -> JSONResponse:
        deps = request.app.state.deps
        service = _tag_service(deps)

        def _create(uow):
            return service.register_key(uow, key=body.key, description=body.description)

        try:
            _require_operator()
            created = await _run(request, _create)
        except OktoNexusError as exc:
            if (
                exc.code == ErrorCode.VALIDATION_ERROR
                and "already registered" in exc.message
            ):
                return _err(409, "CONFLICT", exc.message)
            return _map_error(exc)
        return _ok(created)

    @router.post("/tags/{key}/values")
    async def create_tag_value(
        request: Request, key: str, body: TagValueBody
    ) -> JSONResponse:
        deps = request.app.state.deps
        service = _tag_service(deps)

        def _create(uow):
            return service.register_value(
                uow, key=key, value=body.value, description=body.description
            )

        try:
            _require_operator()
            created = await _run(request, _create)
        except OktoNexusError as exc:
            if (
                exc.code == ErrorCode.VALIDATION_ERROR
                and "already registered" in exc.message
            ):
                return _err(409, "CONFLICT", exc.message)
            return _map_error(exc)
        return _ok(created)

    @router.delete("/tags/{key}")
    async def delete_tag_key(request: Request, key: str) -> JSONResponse:
        deps = request.app.state.deps
        service = _tag_service(deps)
        try:
            _require_operator()
            result = await _run(request, lambda uow: service.delete_key(uow, key=key))
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(result)

    @router.delete("/tags/{key}/values/{value}")
    async def delete_tag_value(request: Request, key: str, value: str) -> JSONResponse:
        deps = request.app.state.deps
        service = _tag_service(deps)

        def _delete(uow):
            return service.delete_value(uow, key=key, value=value)

        try:
            _require_operator()
            result = await _run(request, _delete)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(result)

    # ------------------------------------------------------------------ #
    # Capability catalog (migration 014): the central, fail-closed registry
    # of capability names. Operator-only surface backing the dashboard
    # Registry screen; agents announce names, only operators define them.
    # ------------------------------------------------------------------ #
    @router.get("/capabilities")
    async def list_capabilities(request: Request) -> JSONResponse:
        deps = request.app.state.deps
        service = _capability_service(deps)
        try:
            items = await _read(request, lambda uow: service.snapshot(uow))
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"items": items})

    @router.post("/capabilities")
    async def create_capability(request: Request, body: CapabilityBody) -> JSONResponse:
        deps = request.app.state.deps
        service = _capability_service(deps)

        def _create(uow):
            return service.register(uow, name=body.name, description=body.description)

        try:
            _require_operator()
            created = await _run(request, _create)
        except OktoNexusError as exc:
            if (
                exc.code == ErrorCode.VALIDATION_ERROR
                and "already registered" in exc.message
            ):
                return _err(409, "CONFLICT", exc.message)
            return _map_error(exc)
        return _ok(created)

    @router.delete("/capabilities/{name}")
    async def delete_capability(request: Request, name: str) -> JSONResponse:
        deps = request.app.state.deps
        service = _capability_service(deps)
        try:
            _require_operator()
            result = await _run(request, lambda uow: service.delete(uow, name=name))
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(result)

    # ------------------------------------------------------------------ #
    # Workspace memory (spec 8928b320): the operator's audit surface over
    # the shared memory store, backing the dashboard Memory screen. Reads
    # and curation are deliberately NOT gated by feature_memory (FR7/FR8) -
    # the operator always sees the state; only the agent-facing MCP verbs
    # are flag-gated. DELETE is operator-only physical curation (no event,
    # BR9).
    # ------------------------------------------------------------------ #
    @router.get("/memory")
    async def browse_memory(
        request: Request,
        workspace: str,
        q: str | None = None,
        topic: str | None = None,
        author: str | None = None,
        include_superseded: bool = False,
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        """List/search ONE workspace's memories; with ``q`` the response
        declares the effective ``search_mode`` (semantic|lexical), without it
        this is a paginated recency browse. ``limit`` is taken as a string so
        an out-of-range value is CLAMPED into 1..50 (not a framework 422); a
        non-integer is a VALIDATION_ERROR."""
        service = _memory_service(request.app.state.deps)

        def _browse():
            return service.browse(
                workspace_id=workspace,
                query=q,
                topic=topic,
                author=author,
                include_superseded=include_superseded,
                limit=limit,
                offset=offset,
            )

        try:
            data = await anyio.to_thread.run_sync(_browse)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(data)

    @router.get("/memory/{memory_id}")
    async def get_memory_detail(
        request: Request, memory_id: str, workspace: str
    ) -> JSONResponse:
        service = _memory_service(request.app.state.deps)

        def _get():
            return service.get_raw(workspace_id=workspace, memory_id=memory_id)

        try:
            data = await anyio.to_thread.run_sync(_get)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(data)

    @router.delete("/memory/{memory_id}")
    async def delete_memory(
        request: Request, memory_id: str, workspace: str
    ) -> JSONResponse:
        service = _memory_service(request.app.state.deps)

        def _delete():
            return service.delete_memory(workspace_id=workspace, memory_id=memory_id)

        try:
            _require_operator()
            result = await anyio.to_thread.run_sync(_delete)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(result)

    # ------------------------------------------------------------------ #
    # Governance policies (spec ffef15bf): LEGACY GLOBAL deny rules and quotas,
    # operator-only CRUD over the governance_policies table. Migration 022 has
    # already mirrored these rows into detached global policies; this surface is
    # kept until the /policies surface (B1) supersedes it. Enforcement itself no
    # longer reads this table - it composes the actor's attached policies.
    # ------------------------------------------------------------------ #
    @router.get("/governance/policies")
    async def list_governance_policies(request: Request) -> JSONResponse:
        service = _governance_service(request.app.state.deps)
        try:
            _require_operator()
            items = await anyio.to_thread.run_sync(service.list_policies)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"items": items})

    @router.post("/governance/policies")
    async def create_governance_policy(
        request: Request, body: dict[str, Any]
    ) -> JSONResponse:
        service = _governance_service(request.app.state.deps)

        def _create():
            unknown = sorted(set(body) - _POLICY_FIELDS)
            if unknown:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"Unknown policy field(s): {', '.join(unknown)}.",
                    {"unknown": unknown, "supported": sorted(_POLICY_FIELDS)},
                )
            return service.create_policy(
                subject_kind=body.get("subject_kind"),
                subject_value=body.get("subject_value"),
                action=body.get("action"),
                limit_kind=body.get("limit_kind"),
                limit_value=body.get("limit_value"),
                window=body.get("window"),
                enabled=body.get("enabled", True),
            )

        try:
            _require_operator()
            created = await anyio.to_thread.run_sync(_create)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(created)

    @router.patch("/governance/policies/{policy_id}")
    async def update_governance_policy(
        request: Request, policy_id: str, body: dict[str, Any]
    ) -> JSONResponse:
        service = _governance_service(request.app.state.deps)

        def _update():
            return service.update_policy(policy_id=policy_id, patch=body)

        try:
            _require_operator()
            updated = await anyio.to_thread.run_sync(_update)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(updated)

    @router.delete("/governance/policies/{policy_id}")
    async def delete_governance_policy(
        request: Request, policy_id: str
    ) -> JSONResponse:
        service = _governance_service(request.app.state.deps)

        def _delete():
            return service.delete_policy(policy_id=policy_id)

        try:
            _require_operator()
            result = await anyio.to_thread.run_sync(_delete)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(result)

    # ------------------------------------------------------------------ #
    # Named, versioned policies (spec 80624c1a, migration 022): the operator
    # surface for the UNIFIED policy (audience + governance in one versionable
    # object). CRUD over the header + append-only version publishing. Pure
    # STAGING - creating/editing/publishing attaches to no one and enforces
    # nothing (BR4); DELETE is guarded by the in-use check (BR5). Operator-only,
    # canonical _ok/_err envelope; each method opens its own UoW.
    # ------------------------------------------------------------------ #
    @router.post("/policies")
    async def create_policy(request: Request, body: dict[str, Any]) -> JSONResponse:
        service = _policy_catalog_service(request.app.state.deps)

        def _create():
            unknown = sorted(set(body) - _POLICY_HEADER_FIELDS)
            if unknown:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"Unknown policy field(s): {', '.join(unknown)}.",
                    {"unknown": unknown, "supported": sorted(_POLICY_HEADER_FIELDS)},
                )
            return service.create(
                name=body.get("name"), description=body.get("description")
            )

        try:
            _require_operator()
            created = await anyio.to_thread.run_sync(_create)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(created)

    @router.get("/policies")
    async def list_policies(request: Request) -> JSONResponse:
        service = _policy_catalog_service(request.app.state.deps)
        try:
            _require_operator()
            items = await anyio.to_thread.run_sync(service.list)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"items": items})

    @router.get("/policies/{policy_id}")
    async def get_policy(request: Request, policy_id: str) -> JSONResponse:
        service = _policy_catalog_service(request.app.state.deps)

        def _get():
            return service.get(policy_id=policy_id)

        try:
            _require_operator()
            record = await anyio.to_thread.run_sync(_get)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(record)

    @router.patch("/policies/{policy_id}")
    async def update_policy(
        request: Request, policy_id: str, body: dict[str, Any]
    ) -> JSONResponse:
        service = _policy_catalog_service(request.app.state.deps)

        def _update():
            unknown = sorted(set(body) - _POLICY_HEADER_FIELDS)
            if unknown:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"Unknown policy field(s): {', '.join(unknown)}.",
                    {"unknown": unknown, "supported": sorted(_POLICY_HEADER_FIELDS)},
                )
            return service.update(policy_id=policy_id, patch=body)

        try:
            _require_operator()
            updated = await anyio.to_thread.run_sync(_update)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(updated)

    @router.delete("/policies/{policy_id}")
    async def delete_policy(request: Request, policy_id: str) -> JSONResponse:
        service = _policy_catalog_service(request.app.state.deps)

        def _delete():
            return service.delete(policy_id=policy_id)

        try:
            _require_operator()
            result = await anyio.to_thread.run_sync(_delete)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(result)

    @router.post("/policies/{policy_id}/versions")
    async def publish_policy_version(
        request: Request, policy_id: str, body: dict[str, Any]
    ) -> JSONResponse:
        service = _policy_catalog_service(request.app.state.deps)

        def _publish():
            unknown = sorted(set(body) - {"audience", "governance"})
            if unknown:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"Unknown policy version field(s): {', '.join(unknown)}.",
                    {"unknown": unknown, "supported": ["audience", "governance"]},
                )
            return service.publish_version(
                policy_id=policy_id,
                audience=body.get("audience"),
                governance=body.get("governance"),
            )

        try:
            _require_operator()
            published = await anyio.to_thread.run_sync(_publish)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(published)

    @router.get("/policies/{policy_id}/versions")
    async def list_policy_versions(request: Request, policy_id: str) -> JSONResponse:
        service = _policy_catalog_service(request.app.state.deps)

        def _list():
            return service.list_versions(policy_id=policy_id)

        try:
            _require_operator()
            items = await anyio.to_thread.run_sync(_list)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"items": items})

    @router.get("/agents/{agent_id}/policies")
    async def get_agent_policies(request: Request, agent_id: str) -> JSONResponse:
        # FR10/FR12 (spec 80624c1a): the current binding set of an agent, reshaped
        # into the {globals, inline} contract the PUT accepts (round-trip-friendly)
        # so the C2 editor pre-populates without a blind overwrite. Operator-only,
        # like every /policies surface (this is the operator dashboard, so the
        # inline audience is visible here just as _public_agent carries comm_scope).
        service = _policy_catalog_service(request.app.state.deps)

        def _get():
            return service.get_agent_bindings(agent_id=agent_id)

        try:
            _require_operator()
            result = await anyio.to_thread.run_sync(_get)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(result)

    @router.put("/agents/{agent_id}/policies")
    async def set_agent_policies(
        request: Request, agent_id: str, body: dict[str, Any]
    ) -> JSONResponse:
        # FR10 (spec 80624c1a, contract api_101afea2): replace an agent's full
        # binding set - N globals ({policy_id, mode, pinned_version?}) + one
        # optional inline ({audience, governance}). Operator-only; fail-closed
        # existence checks live in the service (unknown agent/policy -> 404,
        # missing pin -> 422).
        service = _policy_catalog_service(request.app.state.deps)

        def _set():
            unknown = sorted(set(body) - {"globals", "inline"})
            if unknown:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"Unknown binding field(s): {', '.join(unknown)}.",
                    {"unknown": unknown, "supported": ["globals", "inline"]},
                )
            return service.set_agent_bindings(
                agent_id=agent_id,
                globals_=body.get("globals"),
                inline=body.get("inline"),
            )

        try:
            _require_operator()
            result = await anyio.to_thread.run_sync(_set)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(result)

    # ------------------------------------------------------------------ #
    # Communication presets (spec 6f961722, migration 023): the operator
    # surface for the NAMED, versioned communication style. CRUD over the
    # header + append-only version publishing, plus the SINGLE-SOURCE per-agent
    # binding (inline XOR global). Pure STAGING - creating/editing/publishing
    # attaches to no one and surfaces nothing (the whoami block appears only
    # once an agent binds); DELETE is guarded by the in-use check
    # (COMM_PRESET_IN_USE -> 409). Operator-only, canonical _ok/_err envelope;
    # each method opens its own UoW. NOT MCP tools (stdio/http parity intact).
    # ------------------------------------------------------------------ #
    @router.post("/comm-presets")
    async def create_comm_preset(
        request: Request, body: dict[str, Any]
    ) -> JSONResponse:
        service = _comm_preset_catalog_service(request.app.state.deps)

        def _create():
            unknown = sorted(set(body) - _COMM_PRESET_HEADER_FIELDS)
            if unknown:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"Unknown communication preset field(s): {', '.join(unknown)}.",
                    {
                        "unknown": unknown,
                        "supported": sorted(_COMM_PRESET_HEADER_FIELDS),
                    },
                )
            return service.create(
                name=body.get("name"), description=body.get("description")
            )

        try:
            _require_operator()
            created = await anyio.to_thread.run_sync(_create)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(created)

    @router.get("/comm-presets")
    async def list_comm_presets(request: Request) -> JSONResponse:
        service = _comm_preset_catalog_service(request.app.state.deps)
        try:
            _require_operator()
            items = await anyio.to_thread.run_sync(service.list)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"items": items})

    @router.get("/comm-presets/{preset_id}")
    async def get_comm_preset(request: Request, preset_id: str) -> JSONResponse:
        service = _comm_preset_catalog_service(request.app.state.deps)

        def _get():
            return service.get(preset_id=preset_id)

        try:
            _require_operator()
            record = await anyio.to_thread.run_sync(_get)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(record)

    @router.patch("/comm-presets/{preset_id}")
    async def update_comm_preset(
        request: Request, preset_id: str, body: dict[str, Any]
    ) -> JSONResponse:
        service = _comm_preset_catalog_service(request.app.state.deps)

        def _update():
            unknown = sorted(set(body) - _COMM_PRESET_HEADER_FIELDS)
            if unknown:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"Unknown communication preset field(s): {', '.join(unknown)}.",
                    {
                        "unknown": unknown,
                        "supported": sorted(_COMM_PRESET_HEADER_FIELDS),
                    },
                )
            return service.update(preset_id=preset_id, patch=body)

        try:
            _require_operator()
            updated = await anyio.to_thread.run_sync(_update)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(updated)

    @router.delete("/comm-presets/{preset_id}")
    async def delete_comm_preset(request: Request, preset_id: str) -> JSONResponse:
        service = _comm_preset_catalog_service(request.app.state.deps)

        def _delete():
            return service.delete(preset_id=preset_id)

        try:
            _require_operator()
            result = await anyio.to_thread.run_sync(_delete)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(result)

    @router.post("/comm-presets/{preset_id}/versions")
    async def publish_comm_preset_version(
        request: Request, preset_id: str, body: dict[str, Any]
    ) -> JSONResponse:
        service = _comm_preset_catalog_service(request.app.state.deps)

        def _publish():
            unknown = sorted(set(body) - {"content"})
            if unknown:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"Unknown communication preset version field(s): "
                    f"{', '.join(unknown)}.",
                    {"unknown": unknown, "supported": ["content"]},
                )
            return service.publish_version(
                preset_id=preset_id, content=body.get("content")
            )

        try:
            _require_operator()
            published = await anyio.to_thread.run_sync(_publish)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(published)

    @router.get("/comm-presets/{preset_id}/versions")
    async def list_comm_preset_versions(
        request: Request, preset_id: str
    ) -> JSONResponse:
        service = _comm_preset_catalog_service(request.app.state.deps)

        def _list():
            return service.list_versions(preset_id=preset_id)

        try:
            _require_operator()
            items = await anyio.to_thread.run_sync(_list)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"items": items})

    @router.get("/agents/{agent_id}/communication")
    async def get_agent_communication(request: Request, agent_id: str) -> JSONResponse:
        # The agent's CURRENT single binding, reshaped into the {inline, global}
        # contract the PUT accepts (round-trip-friendly) plus the RESOLVED block
        # the whoami would show, so the editor pre-populates and previews.
        # Operator-only, like every /comm-presets surface.
        service = _comm_preset_catalog_service(request.app.state.deps)

        def _get():
            return service.get_agent_binding(agent_id=agent_id)

        try:
            _require_operator()
            result = await anyio.to_thread.run_sync(_get)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(result)

    @router.put("/agents/{agent_id}/communication")
    async def set_agent_communication(
        request: Request, agent_id: str, body: dict[str, Any]
    ) -> JSONResponse:
        # Replace an agent's SINGLE communication binding: inline content
        # ({tone, format, ...}) XOR a global reference ({preset_id, mode,
        # pinned_version?}). Passing neither CLEARS it. Operator-only;
        # fail-closed existence checks live in the service (unknown agent/preset
        # -> 404, missing pin -> 422, both sides -> 422).
        service = _comm_preset_catalog_service(request.app.state.deps)

        def _set():
            unknown = sorted(set(body) - {"inline", "global"})
            if unknown:
                raise OktoNexusError(
                    ErrorCode.VALIDATION_ERROR,
                    f"Unknown communication binding field(s): {', '.join(unknown)}.",
                    {"unknown": unknown, "supported": ["inline", "global"]},
                )
            return service.set_agent_binding(
                agent_id=agent_id,
                inline=body.get("inline"),
                global_=body.get("global"),
            )

        try:
            _require_operator()
            result = await anyio.to_thread.run_sync(_set)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(result)

    # ------------------------------------------------------------------ #
    # HITL approvals + steering (spec 2948b2a2): operator-only surfaces
    # backing the dashboard Approvals screen and the Steer modal. Queue
    # reads and decisions work with feature_hitl OFF (BR6) - only the
    # INTERCEPTION is gated by the flag.
    # ------------------------------------------------------------------ #
    @router.get("/approvals")
    async def list_approvals(
        request: Request, workspace: str, status: str = "", limit: int = 100
    ) -> JSONResponse:
        deps = request.app.state.deps
        try:
            _require_operator()
            status_filter = validate_status_filter(status)
            service = _approval_service(deps)
        except OktoNexusError as exc:
            return _map_error(exc)

        def _list():
            return service.list_approvals(
                workspace_id=workspace, status=status_filter, limit=limit
            )

        try:
            items = await anyio.to_thread.run_sync(_list)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"items": items})

    @router.get("/approvals/{approval_id}")
    async def get_approval_detail(request: Request, approval_id: str) -> JSONResponse:
        deps = request.app.state.deps
        try:
            _require_operator()
            service = _approval_service(deps)
        except OktoNexusError as exc:
            return _map_error(exc)

        def _get():
            return service.get_approval(approval_id=approval_id)

        try:
            detail = await anyio.to_thread.run_sync(_get)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(detail)

    @router.post("/approvals/{approval_id}/decision")
    async def decide_approval(
        request: Request, approval_id: str, body: DecisionBody
    ) -> JSONResponse:
        deps = request.app.state.deps
        try:
            _require_operator()
            service = _approval_service(deps)
        except OktoNexusError as exc:
            return _map_error(exc)
        agent = get_authenticated_agent()
        decided_by = agent.agent_id if agent is not None else OPERATOR_AGENT_ID

        def _decide():
            return service.decide(
                approval_id=approval_id,
                decision=body.decision,
                decided_by=decided_by,
                justification=body.justification,
            )

        try:
            result = await anyio.to_thread.run_sync(_decide)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(result)

    @router.post("/steering/messages")
    async def steer_message(request: Request, body: SteeringBody) -> JSONResponse:
        deps = request.app.state.deps
        try:
            _require_operator()
        except OktoNexusError as exc:
            return _map_error(exc)
        service = _build_message_service(deps)

        def _send():
            # The dashboard addresses workspaces by id; the use case takes a
            # path - resolve through the registered root (same derivation:
            # workspace_id = sha256(realpath)).
            with deps.connection_factory.unit_of_work(write=False) as uow:
                ws = deps.repos.workspaces.get(uow, body.workspace)
            if ws is None or not ws.root_realpath:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    f"workspace '{body.workspace}' is not registered.",
                    {"workspace": body.workspace},
                )
            # The NORMAL use case, no bypass (BR9): permissions, governance
            # deny/quota and even HITL interception all apply to the
            # operator's own sends - steering has no delivery privilege.
            return service.create_message(
                project_root=ws.root_realpath,
                from_agent_id=OPERATOR_AGENT_ID,
                subject=body.subject or "Operator steering",
                body=body.body,
                target={"strategy": "direct", "agent_id": body.to_agent_id},
            )

        try:
            result = await anyio.to_thread.run_sync(_send)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(result)

    # ------------------------------------------------------------------ #
    # Admin actions (FR6 of spec S2 - confirmed in the UI before calling)
    # ------------------------------------------------------------------ #
    @router.post("/sessions/{session_id}/close")
    async def close_session(request: Request, session_id: str) -> JSONResponse:
        deps = request.app.state.deps

        def _close(uow):
            return deps.repos.sessions.close(uow, session_id=session_id)

        try:
            _require_operator()
            session = await _run(request, _close)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(
            {
                "session_id": session.session_id,
                "status": session.status,
                "closed_at": session.closed_at,
            }
        )

    @router.post("/handoffs/{handoff_id}/cancel")
    async def cancel_handoff(
        request: Request, handoff_id: str, workspace: str
    ) -> JSONResponse:
        """ADMIN cancel: a raw ``update_status`` write, NOT the service path.

        Known caveat (I5 spec 6522ad1f, S2): because this bypasses
        ``HandoffService.handoff_cancel``, dependents of this handoff get NO
        ``handoff.dependency_failed`` event and no inbox notice - their edges
        still read CANCELLED on the next claim/list (the DAG gates derive
        state from the dependency table on read), so correctness holds; only
        the push-style notification is skipped. Use the MCP ``handoff_cancel``
        when the notification matters.
        """
        deps = request.app.state.deps

        def _cancel(uow):
            return deps.repos.handoffs.update_status(
                uow,
                workspace_id=workspace,
                handoff_id=handoff_id,
                status="CANCELLED",
            )

        try:
            _require_operator()
            handoff = await _run(request, _cancel)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"handoff_id": handoff.handoff_id, "status": handoff.status})

    @router.post("/workspaces/{workspace_id}/handoffs/{handoff_id}/verify")
    async def verify_handoff(
        request: Request, workspace_id: str, handoff_id: str, body: VerifyHandoffBody
    ) -> JSONResponse:
        """Verdict on a VERIFYING handoff (spec c692da7e, contract api_dd9afb33).

        VERIFIER-only, deliberately NOT operator-only (br_15bf60e6/D5): the
        authenticated key IS the caller (loopback + ``local_open``, where the
        middleware binds no agent, acts as the ``operator``) and authorization
        is the SAME domain rule the MCP verify applies - dynamic verifier
        resolution + the anti-self-verification ban. There is no privileged
        path: the operator passes only when it is the eligible verifier.
        """
        deps = request.app.state.deps
        agent = get_authenticated_agent()
        caller = agent.agent_id if agent is not None else OPERATOR_AGENT_ID
        service = _build_handoff_service(deps)

        def _verify():
            # The dashboard addresses workspaces by id; the use case takes a
            # path - resolve through the registered root (same derivation:
            # workspace_id = sha256(realpath), the steering precedent).
            with deps.connection_factory.unit_of_work(write=False) as uow:
                ws = deps.repos.workspaces.get(uow, workspace_id)
            if ws is None or not ws.root_realpath:
                raise OktoNexusError(
                    ErrorCode.NOT_FOUND,
                    f"workspace '{workspace_id}' is not registered.",
                    {"workspace": workspace_id},
                )
            return service.handoff_verify(
                project_root=ws.root_realpath,
                handoff_id=handoff_id,
                agent_id=caller,
                verdict=body.verdict,
                feedback=body.feedback,
            )

        try:
            result = await anyio.to_thread.run_sync(_verify)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(result)

    @router.post("/admin/prune")
    async def admin_prune(request: Request, dry_run: bool = True) -> JSONResponse:
        deps = request.app.state.deps

        def _prune(uow=None):
            from ....application.retention import RetentionService

            return RetentionService.from_deps(deps).prune(dry_run=dry_run)

        try:
            _require_operator()
            report = await anyio.to_thread.run_sync(_prune)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok(report)

    @router.get("/license")
    async def license_text(request: Request):
        """The FULL licence text (public; rendered by the About modal)."""
        from pathlib import Path

        from fastapi.responses import PlainTextResponse

        path = Path(__file__).parent / "LICENSE.txt"
        try:
            return PlainTextResponse(path.read_text(encoding="utf-8"))
        except OSError:
            return PlainTextResponse(
                "Elastic License 2.0 - full text unavailable in this build.",
                status_code=200,
            )

    # ------------------------------------------------------------------ #
    # Runtime settings (Settings screen; precedence CLI > env > stored)
    # ------------------------------------------------------------------ #
    @router.get("/settings")
    async def get_settings(request: Request) -> JSONResponse:
        service = request.app.state.settings_service
        try:
            items = await _read(request, lambda uow: service.describe(uow))
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"items": items})

    @router.patch("/settings")
    async def patch_settings(request: Request, body: dict[str, Any]) -> JSONResponse:
        service = request.app.state.settings_service
        try:
            _require_operator()
            applied = await _run(request, lambda uow: service.update(uow, body))
        except OktoNexusError as exc:
            if exc.code == ErrorCode.CONFIG_ERROR:
                return _err(422, "INVALID_SETTING", exc.message)
            return _map_error(exc)
        return _ok({"applied": applied})

    @router.post("/settings/reset")
    async def reset_settings(request: Request) -> JSONResponse:
        service = request.app.state.settings_service
        try:
            _require_operator()
            cleared = await _run(request, lambda uow: service.reset(uow))
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"cleared": cleared})

    @router.post("/admin/reset")
    async def admin_reset(request: Request, keep_agents: bool = True) -> JSONResponse:
        """Wipe the operational store (Settings > "Zerar banco de dados").

        Deletes ALL messages/deliveries/handoffs/sessions/events/channels/
        tasks/workspaces in one transaction. ``keep_agents=true`` (default)
        preserves agent identities and their API keys - the dashboard and
        every connected MCP client keep working; ``false`` razes agents too
        (a fresh serve will then re-issue the operator key on cold start).
        VACUUM afterwards so the file actually shrinks on disk.
        """
        deps = request.app.state.deps

        def _reset():
            import sqlite3

            # Enumerate tables FROM THE SCHEMA instead of hardcoding them: a
            # fixed list silently misses tables (the original bug: `artifacts`
            # stayed out, its workspace FK broke the wipe at commit time) and
            # would break again on every future migration. Preserved tables:
            # migration bookkeeping, runtime settings and - by default - the
            # agent identities/keys.
            preserved = {"schema_migrations", "settings"}
            if keep_agents:
                preserved.add("agents")
            counts: dict[str, int] = {}
            try:
                with deps.connection_factory.unit_of_work() as uow:
                    # FK checks deferred to commit: with every non-preserved
                    # table emptied in the same transaction, the end state is
                    # consistent regardless of deletion order.
                    uow.connection.execute("PRAGMA defer_foreign_keys=ON")
                    rows = uow.connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                    for row in rows:
                        table = row["name"]
                        if table in preserved:
                            continue
                        cur = uow.connection.execute(f'DELETE FROM "{table}"')
                        counts[table] = cur.rowcount
            except sqlite3.Error as exc:
                raise db_error_from_exception("wiping the store", exc) from exc
            # VACUUM is best-effort: it needs a moment without readers (the
            # SSE poller and the lock heartbeat read constantly), and a
            # skipped VACUUM only means the file shrinks later - the DATA is
            # already gone either way.
            vacuumed = False
            try:
                conn = deps.connection_factory.get_connection()
                try:
                    conn.execute("VACUUM")
                    vacuumed = True
                finally:
                    conn.close()
            except sqlite3.Error:
                pass
            return counts, vacuumed

        try:
            _require_operator()
            counts, vacuumed = await anyio.to_thread.run_sync(_reset)
        except OktoNexusError as exc:
            return _map_error(exc)
        if not keep_agents:
            request.app.state.auth.invalidate_all()
        return _ok(
            {"deleted": counts, "kept_agents": keep_agents, "vacuumed": vacuumed}
        )

    return router


def _public_agent(agent) -> dict[str, Any]:
    """The agent shape every non-issuing surface returns: NEVER the key.

    This is the OPERATOR dashboard surface, so it carries ``comm_scope``
    (the operator sets it here). Agent-facing discovery (MCP agent_list/
    agent_get) exposes ``tags`` but NEVER ``comm_scope``.
    """
    return {
        "agent_id": agent.agent_id,
        "role": agent.role,
        "capabilities": agent.capabilities,
        "metadata": agent.metadata,
        "is_active": agent.is_active,
        "has_key": agent.api_key_hash is not None,
        "created_at": agent.created_at,
        "last_seen_at": agent.last_seen_at,
        "permissions": agent.permissions,
        "preset_id": agent.preset_id,
        "tags": agent.tags,
        "comm_scope": agent.comm_scope,
        "color": agent.color,
    }
