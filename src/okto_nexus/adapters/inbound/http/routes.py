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
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ....application.observability import DEFAULT_GRAPH_WINDOW_HOURS
from ....application.search import EmbeddingsUnavailable
from ....domain.base import new_id
from ....domain.permissions import (
    BUILTIN_PRESETS,
    PERMISSION_DESCRIPTIONS,
    PERMISSION_REGISTRY,
    builtin_preset,
    validate_permission_flags,
)
from ....errors import ErrorCode, OktoNexusError, db_error_from_exception


def _ok(data: Any) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data})


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": {"code": code, "message": message}}, status_code=status
    )


def _map_error(exc: OktoNexusError) -> JSONResponse:
    status = {
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.VALIDATION_ERROR: 422,
        ErrorCode.PERMISSION_DENIED: 403,
        ErrorCode.DB_ERROR: 503,
    }.get(exc.code, 500)
    return _err(status, str(exc.code), exc.message)


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
class CreateAgentBody(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    role: str | None = None
    capabilities: dict[str, Any] | list[str] | None = None
    metadata: dict[str, Any] | None = None
    # Permissions (migration 011): a preset to copy flags from and/or an
    # explicit flags object (explicit flags win - the Pulse semantics).
    preset_id: str | None = None
    permissions: dict[str, Any] | None = None


class UpdateAgentBody(BaseModel):
    role: str | None = None
    capabilities: dict[str, Any] | list[str] | None = None
    metadata: dict[str, Any] | None = None
    is_active: bool | None = None
    preset_id: str | None = None
    permissions: dict[str, Any] | None = None


class PresetBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    flags: dict[str, Any]


class PresetPatchBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    flags: dict[str, Any] | None = None


def _normalise_capabilities(value: dict | list | None) -> dict | None:
    # The V1 store models capabilities as a JSON object; accept the common
    # list spelling from clients and normalise it to {name: true}.
    if isinstance(value, list):
        return {str(item): True for item in value}
    return value


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
    async def conversation_peers(
        request: Request, agent: str
    ) -> JSONResponse:
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
        limit: int = 100,
    ) -> JSONResponse:
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
                ),
            )
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"items": rows, "next_cursor": rows[-1]["event_id"] if rows else after})

    # ------------------------------------------------------------------ #
    # Agent & key management (FR4/FR9)
    # ------------------------------------------------------------------ #
    @router.post("/agents")
    async def create_agent(request: Request, body: CreateAgentBody) -> JSONResponse:
        deps = request.app.state.deps
        auth = request.app.state.auth

        def _create(uow):
            agents = deps.repos.agents
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
            agent = agents.upsert(
                uow,
                agent_id=body.agent_id,
                role=body.role,
                capabilities=_normalise_capabilities(body.capabilities),
                metadata=body.metadata,
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
            agent, plaintext = await _run(request, _create)
        except OktoNexusError as exc:
            if exc.code == ErrorCode.VALIDATION_ERROR and "already exists" in exc.message:
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
                "api_key": plaintext,
            }
        )

    @router.get("/agents")
    async def list_agents(request: Request) -> JSONResponse:
        deps = request.app.state.deps

        def _list(uow):
            return [
                _public_agent(agent) for agent in deps.repos.agents.list(uow)
            ]

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
            agents.upsert(
                uow,
                agent_id=agent_id,
                role=body.role,
                capabilities=_normalise_capabilities(body.capabilities),
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
            return agents.get(uow, agent_id)

        try:
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
            return _err(
                403, "PERMISSION_DENIED", "Built-in presets cannot be deleted."
            )

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
            removed = await _run(request, _delete)
        except OktoNexusError as exc:
            return _map_error(exc)
        if not removed:
            return _err(404, "NOT_FOUND", "preset not found")
        return _ok({"preset_id": preset_id, "deleted": True})

    # ------------------------------------------------------------------ #
    # Admin actions (FR6 of spec S2 - confirmed in the UI before calling)
    # ------------------------------------------------------------------ #
    @router.post("/sessions/{session_id}/close")
    async def close_session(request: Request, session_id: str) -> JSONResponse:
        deps = request.app.state.deps

        def _close(uow):
            return deps.repos.sessions.close(uow, session_id=session_id)

        try:
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
        deps = request.app.state.deps

        def _cancel(uow):
            return deps.repos.handoffs.update_status(
                uow,
                workspace_id=workspace,
                handoff_id=handoff_id,
                status="CANCELLED",
            )

        try:
            handoff = await _run(request, _cancel)
        except OktoNexusError as exc:
            return _map_error(exc)
        return _ok({"handoff_id": handoff.handoff_id, "status": handoff.status})

    @router.post("/admin/prune")
    async def admin_prune(request: Request, dry_run: bool = True) -> JSONResponse:
        deps = request.app.state.deps

        def _prune(uow=None):
            from ....application.retention import RetentionService

            return RetentionService.from_deps(deps).prune(dry_run=dry_run)

        try:
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
    async def patch_settings(
        request: Request, body: dict[str, Any]
    ) -> JSONResponse:
        service = request.app.state.settings_service
        try:
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
    """The agent shape every non-issuing surface returns: NEVER the key."""
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
    }
