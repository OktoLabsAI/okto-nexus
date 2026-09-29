"""Ticket-authenticated NXL R4 control link, fenced before execution."""

from __future__ import annotations

import asyncio
import ipaddress
import secrets
from urllib.parse import urlsplit

import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from nexus_connector_core import (
    CoreError, R4_PREVIEW_REVISION, decode_r4_frame, encode_r4_frame,
)

from ....adapters.outbound.execution.core_inventory import protocol_info
from ....adapters.outbound.sqlite.execution_identity import (
    ensure_execution_installation,
)
from ....adapters.outbound.sqlite.execution_tickets import (
    verify_execution_ticket,
)
from ....errors import OktoNexusError


SUBPROTOCOL = "nxl.v1"
MAX_FRAME_BYTES = 64 * 1024


def _loopback(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def _safe_transport(ws: WebSocket) -> bool:
    # A reverse proxy must provide a trusted WSS ASGI scheme. Forwarded
    # headers supplied by a client do not turn an insecure socket into TLS.
    if ws.url.scheme != "wss" and not (
            ws.url.scheme == "ws" and _loopback(ws.url.hostname) and
            _loopback(ws.client.host if ws.client else None)):
        return False
    origin = ws.headers.get("origin")
    if origin is None:
        return True  # Non-browser Connector clients need not send Origin.
    parsed = urlsplit(origin)
    expected_scheme = "https" if ws.url.scheme == "wss" else "http"
    expected_port = ws.url.port or (443 if ws.url.scheme == "wss" else 80)
    return (parsed.scheme == expected_scheme and
            parsed.hostname == ws.url.hostname and
            (parsed.port or (443 if parsed.scheme == "https" else 80)) ==
            expected_port and not parsed.username and not parsed.password and
            parsed.path in ("", "/") and not parsed.query and not parsed.fragment)


def _bearer(ws: WebSocket) -> str | None:
    value = ws.headers.get("authorization", "")
    if not value.startswith("Bearer "):
        return None
    token = value[7:]
    return token if token and " " not in token else None


def build_router() -> APIRouter:
    router = APIRouter()

    @router.websocket("/runtime/executors/{executor_id}/link")
    async def executor_link(ws: WebSocket, executor_id: str) -> None:
        if (not _safe_transport(ws) or
                SUBPROTOCOL not in ws.scope.get("subprotocols", ())):
            await ws.close(code=4406)
            return
        ticket = _bearer(ws)
        if ticket is None:
            await ws.close(code=4401)
            return
        factory = ws.app.state.deps.connection_factory

        def _verify():
            installation = ensure_execution_installation(factory)
            verify_execution_ticket(
                factory, ticket=ticket, server_id=installation.server_id,
                executor_id=executor_id, binding_id=None,
                scope="link:connect")
            return installation.server_id

        try:
            server_id = await anyio.to_thread.run_sync(_verify)
        except OktoNexusError:
            await ws.close(code=4401)
            return
        info = protocol_info()
        if (not info["remote_execution_ready"] or
                R4_PREVIEW_REVISION not in info["nxl_accepted"]):
            await ws.close(code=4406)
            return
        await ws.accept(subprotocol=SUBPROTOCOL)
        connection_id: str | None = None
        generation: int | None = None
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=10)
            if len(raw.encode("utf-8")) > MAX_FRAME_BYTES:
                await ws.close(code=4409)
                return
            hello = decode_r4_frame(raw.encode("utf-8"))
            if (hello["type"] != "hello" or
                    hello["server_id"] != server_id or
                    hello["executor_id"] != executor_id or
                    hello["core_version"] != info["core_version"] or
                    hello["management_revision"] !=
                    info["management_revision"] or
                    R4_PREVIEW_REVISION not in hello["supported_nxl"] or
                    info["executor_snapshot_format"] not in
                    hello["snapshot_formats"]):
                await ws.close(code=4406)
                return
            connection_id = "conn_" + secrets.token_hex(16)

            def _claim():
                with factory.unit_of_work() as uow:
                    row = uow.connection.execute(
                        "SELECT generation,revoked_at FROM execution_executors "
                        "WHERE server_id=? AND executor_id=? AND kind='remote'",
                        (server_id, executor_id),
                    ).fetchone()
                    if row is None or row["revoked_at"] is not None:
                        raise ValueError("executor unavailable")
                    next_generation = row["generation"] + 1
                    changed = uow.connection.execute(
                        "UPDATE execution_executors SET generation=?,"
                        "owner_instance_id=?,control_state='RECOVERING',"
                        "last_seen_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                        "WHERE server_id=? AND executor_id=? AND generation=?",
                        (next_generation, connection_id, server_id,
                         executor_id, row["generation"]),
                    ).rowcount
                    if changed != 1:
                        raise ValueError("executor generation changed")
                    return next_generation

            try:
                generation = await anyio.to_thread.run_sync(_claim)
            except ValueError:
                await ws.close(code=4403)
                return
            welcome = {
                "protocol_major": 1, "contract_revision": R4_PREVIEW_REVISION,
                "type": "welcome", "link_attempt_id": hello["link_attempt_id"],
                "server_id": server_id, "executor_id": executor_id,
                "connection_id": connection_id,
                "connection_generation": generation,
                "management_revision": info["management_revision"],
                "accepted_nxl": R4_PREVIEW_REVISION,
                "snapshot_format": info["executor_snapshot_format"],
                "control_capabilities": [],
            }
            await ws.send_text(encode_r4_frame(welcome).decode("utf-8"))
            # Attach/reconcile and lease installation are separate gates.
            # Until implemented, heartbeats preserve only technical presence.
            while True:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=30)
                if len(raw.encode("utf-8")) > MAX_FRAME_BYTES:
                    await ws.close(code=4409)
                    break
                frame = decode_r4_frame(raw.encode("utf-8"))
                if (frame["type"] != "heartbeat" or
                        frame["server_id"] != server_id or
                        frame["executor_id"] != executor_id or
                        frame["connection_id"] != connection_id or
                        frame["connection_generation"] != generation):
                    await ws.close(code=4406)
                    break

                def _touch():
                    with factory.unit_of_work() as uow:
                        return uow.connection.execute(
                            "UPDATE execution_executors SET "
                            "last_seen_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                            "WHERE server_id=? AND executor_id=? AND "
                            "owner_instance_id=? AND generation=? AND "
                            "control_state='RECOVERING'",
                            (server_id, executor_id,
                             connection_id, generation),
                        ).rowcount

                if await anyio.to_thread.run_sync(_touch) != 1:
                    await ws.close(code=4403)
                    break
        except (WebSocketDisconnect, asyncio.TimeoutError):
            pass
        except (CoreError, UnicodeError, ValueError, RecursionError):
            await ws.close(code=4406)
        finally:
            if connection_id is not None and generation is not None:
                def _release():
                    with factory.unit_of_work() as uow:
                        uow.connection.execute(
                            "UPDATE execution_executors SET control_state='DISCONNECTED',"
                            "owner_instance_id=NULL WHERE server_id=? "
                            "AND executor_id=? AND owner_instance_id=? "
                            "AND generation=?",
                            (server_id, executor_id, connection_id,
                             generation),
                        )

                await anyio.to_thread.run_sync(_release)

    return router
