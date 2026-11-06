"""Operator attention projection and auxiliary preferences over canonical facts."""

from functools import partial

import anyio.to_thread
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from ....errors import ErrorCode, OktoNexusError
from .identity_ctx import runtime_request_context
from .routes import _err, _map_error, _ok


class SeenBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_revision: str = Field(min_length=1, max_length=512)
    preference_revision: int = Field(ge=0)
    seen: StrictBool = True


class SnoozeBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_revision: str = Field(min_length=1, max_length=512)
    preference_revision: int = Field(ge=0)
    until: str | None


def _filters(
    workspace_id: str | None = None,
    agent_id: str | None = None,
    category: str | None = None,
    kind: str | None = None,
    state: str = "active",
    priority: int | None = None,
    seen: str = "all",
):
    return {key: value for key, value in {
        "workspace_id": workspace_id, "agent_id": agent_id, "category": category,
        "kind": kind, "state": state, "priority": priority, "seen": seen,
    }.items() if value is not None}


def _query(request, allowed):
    keys = list(request.query_params)
    if any(key not in allowed | {"api_key"} or
           len(request.query_params.getlist(key)) != 1 for key in keys):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                             "The attention query contains an unknown or repeated parameter.", {})


async def _call(request, method, *, allowed_query=frozenset(), **kwargs):
    try:
        _query(request, allowed_query)
        result = await anyio.to_thread.run_sync(partial(
            getattr(request.app.state.attention, method),
            context=runtime_request_context(), **kwargs))
        response = _ok(result)
    except OktoNexusError as exc:
        special_status = {"FEATURE_DISABLED": 409, "ATTENTION_QUERY_BUDGET": 503}.get(exc.code)
        response = (_err(special_status, exc.code, exc.message) if special_status
                    else _map_error(exc))
    response.headers["Cache-Control"] = "no-store"
    return response


def build_router():
    router = APIRouter()
    filters_keys = frozenset({"workspace_id", "agent_id", "category", "kind", "state", "priority", "seen"})

    @router.get("/attention")
    async def attention_read(
        request: Request, filters: dict = Depends(_filters), cursor: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ):
        return await _call(request, "read", allowed_query=filters_keys | {"cursor", "limit"},
                           filters=filters, cursor=cursor, limit=limit)

    @router.get("/attention/summary")
    async def attention_summary(request: Request, filters: dict = Depends(_filters)):
        return await _call(request, "summary", allowed_query=filters_keys, filters=filters)

    @router.post("/attention/{attention_id}/seen")
    async def attention_seen(request: Request, attention_id: str, body: SeenBody):
        return await _call(request, "mark_seen", attention_id=attention_id, **body.model_dump())

    @router.post("/attention/{attention_id}/snooze")
    async def attention_snooze(request: Request, attention_id: str, body: SnoozeBody):
        return await _call(request, "snooze", attention_id=attention_id, **body.model_dump())

    return router
