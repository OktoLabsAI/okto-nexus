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
        ErrorCode.DB_ERROR: 503,
    }.get(exc.code, 500)
    return _err(status, str(exc.code), exc.message)


async def _run(request: Request, fn):
    """Execute ``fn(uow, state)`` in a worker thread with a fresh UoW."""
    deps = request.app.state.deps

    def _call():
        with deps.connection_factory.unit_of_work() as uow:
            return fn(uow)

    return await anyio.to_thread.run_sync(_call)


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #
class CreateAgentBody(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    role: str | None = None
    capabilities: dict[str, Any] | list[str] | None = None
    metadata: dict[str, Any] | None = None


class UpdateAgentBody(BaseModel):
    role: str | None = None
    capabilities: dict[str, Any] | list[str] | None = None
    metadata: dict[str, Any] | None = None
    is_active: bool | None = None


def _normalise_capabilities(value: dict | list | None) -> dict | None:
    # The V1 store models capabilities as a JSON object; accept the common
    # list spelling from clients and normalise it to {name: true}.
    if isinstance(value, list):
        return {str(item): True for item in value}
    return value


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

        schema_version = await _run(request, _info)
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
            snapshot = await _run(
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
    ) -> JSONResponse:
        observability = request.app.state.observability
        try:
            data = await _run(
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
                ),
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
            rows = await _run(
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
            rows = await _run(
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
            rows = await _run(
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
            agent = agents.upsert(
                uow,
                agent_id=body.agent_id,
                role=body.role,
                capabilities=_normalise_capabilities(body.capabilities),
                metadata=body.metadata,
            )
            plaintext = auth.issue_key(uow, agent_id=agent.agent_id)
            return agent, plaintext

        try:
            agent, plaintext = await _run(request, _create)
        except OktoNexusError as exc:
            if exc.code == ErrorCode.VALIDATION_ERROR:
                return _err(409, "CONFLICT", exc.message)
            return _map_error(exc)
        # The ONLY surface that ever carries the plaintext (BR7/AC3).
        return _ok(
            {
                "agent_id": agent.agent_id,
                "role": agent.role,
                "is_active": True,
                "created_at": agent.created_at,
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

        return _ok({"items": await _run(request, _list)})

    @router.get("/agents/{agent_id}")
    async def get_agent(request: Request, agent_id: str) -> JSONResponse:
        deps = request.app.state.deps
        agent = await _run(request, lambda uow: deps.repos.agents.get(uow, agent_id))
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
            return agents.get(uow, agent_id)

        agent = await _run(request, _update)
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
            items = await _run(request, lambda uow: service.describe(uow))
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
    }
