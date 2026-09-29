"""Ticket-authenticated NXL R4 control link, fenced before execution."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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
from ....adapters.outbound.sqlite.execution_agent_revisions import (
    current_agent_revisions,
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

        def _admit_attach(frame: dict) -> int:
            if (frame["server_id"] != server_id or
                    frame["executor_id"] != executor_id or
                    frame["connection_id"] != connection_id or
                    frame["expected_connection_generation"] != generation):
                raise ValueError("attach scope changed")
            verified = verify_execution_ticket(
                factory, ticket=frame["ticket"], server_id=server_id,
                executor_id=executor_id, binding_id=frame["binding_id"],
                scope="lane:attach")
            if (verified.agent_id != frame["agent_id"] or
                    verified.credential_epoch != frame["credential_epoch"] or
                    verified.authorization_revision !=
                    frame["authorization_revision"]):
                raise ValueError("attach authority changed")
            _, revisions, _ = current_agent_revisions(
                factory, agent_id=verified.agent_id)
            if revisions.configuration != frame["configuration_revision"]:
                raise ValueError("attach configuration changed")
            with factory.unit_of_work() as uow:
                conn = uow.connection
                owner = conn.execute(
                    "SELECT 1 FROM execution_executors WHERE server_id=? "
                    "AND executor_id=? AND owner_instance_id=? AND generation=? "
                    "AND control_state='RECOVERING' AND revoked_at IS NULL",
                    (server_id, executor_id, connection_id, generation),
                ).fetchone()
                binding = conn.execute(
                    "SELECT ep.agent_id FROM execution_bindings b JOIN "
                    "agent_endpoints ep ON ep.endpoint_id=b.endpoint_id "
                    "WHERE b.server_id=? AND b.executor_id=? AND b.binding_id=?",
                    (server_id, executor_id, frame["binding_id"]),
                ).fetchone()
                ticket_row = conn.execute(
                    "SELECT revoked_at,expires_at,credential_epoch,"
                    "authorization_revision,bound_connection_id "
                    "FROM execution_link_tickets WHERE ticket_id=?",
                    (verified.ticket_id,),
                ).fetchone()
                current = conn.execute(
                    "SELECT credential_epoch,authorization_revision,"
                    "configuration_revision FROM execution_agent_revisions "
                    "WHERE server_id=? AND agent_id=?",
                    (server_id, verified.agent_id),
                ).fetchone()
                expires = (datetime.fromisoformat(
                    ticket_row["expires_at"].replace("Z", "+00:00"))
                    if ticket_row is not None else None)
                remaining = (int((expires - datetime.now(timezone.utc))
                                 .total_seconds()) if expires is not None else 0)
                if (owner is None or binding is None or
                        binding["agent_id"] != verified.agent_id or
                        ticket_row is None or ticket_row["revoked_at"] is not None or
                        remaining < 1 or
                        ticket_row["bound_connection_id"] not in
                        (None, connection_id) or current is None or
                        tuple(current) != (
                            frame["credential_epoch"],
                            frame["authorization_revision"],
                            frame["configuration_revision"]) or
                        ticket_row["credential_epoch"] !=
                        frame["credential_epoch"] or
                        ticket_row["authorization_revision"] !=
                        frame["authorization_revision"]):
                    raise ValueError("attach authority unavailable")
                prior = conn.execute(
                    "SELECT connection_id,connection_generation,"
                    "attach_request_id,ticket_id FROM execution_control_lanes "
                    "WHERE server_id=? AND executor_id=? AND binding_id=?",
                    (server_id, executor_id, frame["binding_id"]),
                ).fetchone()
                if (prior is not None and
                        prior["connection_id"] == connection_id and
                        prior["connection_generation"] == generation and
                        prior["attach_request_id"] != frame["attach_request_id"]):
                    old_ticket = conn.execute(
                        "SELECT revoked_at FROM execution_link_tickets "
                        "WHERE ticket_id=?", (prior["ticket_id"],),
                    ).fetchone()
                    if (prior["ticket_id"] == verified.ticket_id or
                            old_ticket is None or
                            old_ticket["revoked_at"] is None):
                        raise ValueError("attach attempt changed")
                conn.execute(
                    "INSERT INTO execution_control_lanes(server_id,executor_id,"
                    "binding_id,agent_id,ticket_id,attach_request_id,"
                    "connection_id,connection_generation,credential_epoch,"
                    "authorization_revision,configuration_revision,expires_at,"
                    "state) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'ADMITTED') "
                    "ON CONFLICT(server_id,executor_id,binding_id) DO UPDATE SET "
                    "agent_id=excluded.agent_id,ticket_id=excluded.ticket_id,"
                    "attach_request_id=excluded.attach_request_id,"
                    "connection_id=excluded.connection_id,"
                    "connection_generation=excluded.connection_generation,"
                    "credential_epoch=excluded.credential_epoch,"
                    "authorization_revision=excluded.authorization_revision,"
                    "configuration_revision=excluded.configuration_revision,"
                    "expires_at=excluded.expires_at,state='ADMITTED'",
                    (server_id, executor_id, frame["binding_id"],
                     verified.agent_id, verified.ticket_id,
                     frame["attach_request_id"], connection_id, generation,
                     frame["credential_epoch"],
                     frame["authorization_revision"],
                     frame["configuration_revision"],
                     ticket_row["expires_at"]),
                )
                conn.execute(
                    "UPDATE execution_link_tickets SET bound_connection_id=? "
                    "WHERE ticket_id=? AND revoked_at IS NULL",
                    (connection_id, verified.ticket_id),
                )
                return min(600, remaining)
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
                        "SELECT generation,revoked_at,owner_instance_id "
                        "FROM execution_executors "
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
                    uow.connection.execute(
                        "UPDATE execution_control_lanes SET state='DISCONNECTED' "
                        "WHERE server_id=? AND executor_id=? AND "
                        "connection_generation<>?",
                        (server_id, executor_id, next_generation),
                    )
                    if row["owner_instance_id"] is not None:
                        uow.connection.execute(
                            "UPDATE execution_link_tickets SET "
                            "bound_connection_id=NULL WHERE server_id=? "
                            "AND executor_id=? AND bound_connection_id=?",
                            (server_id, executor_id,
                             row["owner_instance_id"]),
                        )
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
                if frame["type"] == "binding.attach":
                    try:
                        expires_in = await anyio.to_thread.run_sync(
                            _admit_attach, frame)
                    except (OktoNexusError, ValueError):
                        await ws.send_text(encode_r4_frame({
                            "protocol_major": 1,
                            "contract_revision": R4_PREVIEW_REVISION,
                            "type": "error", "server_id": server_id,
                            "executor_id": executor_id,
                            "connection_id": connection_id,
                            "connection_generation": generation,
                            "code": "ATTACH_DENIED", "stage": "binding.attach",
                            "possible_effect": False, "retry_safe": False,
                        }).decode("utf-8"))
                        continue
                    await ws.send_text(encode_r4_frame({
                        "protocol_major": 1,
                        "contract_revision": R4_PREVIEW_REVISION,
                        "type": "binding.attached",
                        "attach_request_id": frame["attach_request_id"],
                        "server_id": server_id, "executor_id": executor_id,
                        "connection_id": connection_id,
                        "connection_generation": generation,
                        "binding_id": frame["binding_id"],
                        "agent_id": frame["agent_id"],
                        "credential_epoch": frame["credential_epoch"],
                        "authorization_revision":
                        frame["authorization_revision"],
                        "configuration_revision":
                        frame["configuration_revision"],
                        "expires_in": expires_in,
                    }).decode("utf-8"))
                    continue
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
                        uow.connection.execute(
                            "UPDATE execution_control_lanes SET state='DISCONNECTED' "
                            "WHERE server_id=? AND executor_id=? AND "
                            "connection_id=? AND connection_generation=?",
                            (server_id, executor_id, connection_id, generation),
                        )
                        uow.connection.execute(
                            "UPDATE execution_link_tickets SET "
                            "bound_connection_id=NULL WHERE server_id=? "
                            "AND executor_id=? AND bound_connection_id=?",
                            (server_id, executor_id, connection_id),
                        )

                await anyio.to_thread.run_sync(_release)

    return router
