"""Optional two-application HTTP inventory conformance in one process.

Set OKTO_CONNECTOR_SRC to the Connector's src directory. This exercises the
real Nexus ASGI router and Connector HTTP client against the same Core wheel;
it is a contract test, not provider or two-host evidence.
"""

from __future__ import annotations

import os
import asyncio
from pathlib import Path

import httpx
import pytest

from okto_nexus.adapters.inbound.http.app import build_app
from okto_nexus.bootstrap.dependencies import bootstrap


def test_connector_publishes_core_snapshot_to_nexus(tmp_path, monkeypatch):
    source = os.environ.get("OKTO_CONNECTOR_SRC")
    if not source or not Path(source).is_dir():
        pytest.skip("Set OKTO_CONNECTOR_SRC for the cross-repo contract run")
    monkeypatch.syspath_prepend(source)
    from okto_nexus_connector.services.discovery_service import (
        executor_inventory_snapshot,
    )
    from okto_nexus_connector.transport.https_client import NexusHTTPClient

    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute(
            "INSERT INTO agents(agent_id,created_at) VALUES (?,?)",
            ("agent-a", "2026-09-29T00:00:00Z"),
        )
    with deps.connection_factory.unit_of_work() as uow:
        key = app.state.auth.issue_key(uow, agent_id="agent-a")
    async def roundtrip():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport) as raw:
            async with NexusHTTPClient("http://127.0.0.1:8202", client=raw) as http:
                me = await http.me(key)
                assert me.agent_id == "agent-a"
                registered = await http.register_executor(
                    key, client_intent_id="register-a", connector_id="connector-a",
                    label="Remote host",
                )
                assert registered.server_id == me.server_id
                snapshot = executor_inventory_snapshot(
                    [], server_id=registered.server_id,
                    executor_id=registered.executor_id,
                    producer_instance_id="connector-process-a",
                    publication_sequence=1,
                )
                accepted = await http.publish_inventory(
                    registered.bootstrap_ticket,
                    executor_id=registered.executor_id, snapshot=snapshot,
                )
                assert accepted.inventory_revision == snapshot["inventory_revision"]
                return registered, snapshot

    registered, snapshot = asyncio.run(roundtrip())
    with deps.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            "SELECT publication_sequence,inventory_revision FROM "
            "execution_inventory_current WHERE server_id=? AND executor_id=?",
            (registered.server_id, registered.executor_id),
        ).fetchone()
    assert tuple(row) == (1, snapshot["inventory_revision"])
