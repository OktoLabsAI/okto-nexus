"""Production factories must actually exercise declared connection multiplexing."""
import sys
from pathlib import Path

import pytest

from test_pr34_remediation import runtime as runtime_fixture, tool
from test_harness_codex_connector import _FAKE_SERVER_SOURCE
from test_runtime_commands import wait_close_result, wait_operation

runtime = runtime_fixture


def configure(runtime, *, secret=False):
    _, client, root, _, operator, _ = runtime
    Path(root, "app-server").write_text(_FAKE_SERVER_SOURCE, encoding="utf-8")
    response = client.patch("/api/v1/harness/profiles/profile-codex", headers={"x-api-key": operator}, json={
        "expected_revision": 1, "config": {"command": [sys.executable, "app-server"]},
        "secret_refs": {"FIXTURE_CREDENTIAL": "env:OKTO_MULTIPLEX_FIXTURE"} if secret else {}})
    assert response.status_code == 200, response.text


def open_endpoint(runtime, endpoint="endpoint-codex", *, agent="worker", root=None):
    _, client, default_root, _, operator, _ = runtime
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": agent, "kind": "codex", "endpoint_id": endpoint, "project_root": root or default_root})
    assert opened.status_code == 200, opened.text
    return opened.json()["data"]


@pytest.mark.parametrize("runtime", ["production"], indirect=True)
@pytest.mark.parametrize("change", ["agent", "workspace", "profile", "revision", "secret", "hitl"])
def test_production_connection_reuse_never_crosses_effective_context(runtime, monkeypatch, change):
    deps, client, root, _, operator, _ = runtime
    monkeypatch.setenv("OKTO_MULTIPLEX_FIXTURE", "first-disposable-value")
    configure(runtime, secret=change == "secret")
    first = open_endpoint(runtime)
    headers = {"x-api-key": operator}
    profile, agent = "profile-codex", "worker"
    if change == "agent":
        agent = "sibling-agent"
        with deps.connection_factory.unit_of_work() as uow:
            deps.repos.agents.upsert(uow, agent_id=agent)
    elif change == "workspace":
        root = str(Path(root).parent / "other-project")
        Path(root).mkdir()
        Path(root, "app-server").write_text(_FAKE_SERVER_SOURCE, encoding="utf-8")
    elif change == "profile":
        profile = "other-profile"
        changed = client.post("/api/v1/harness/profiles", headers=headers, json={
            "profile_id": profile, "adapter_id": "codex", "enabled": True,
            "config": {"command": [sys.executable, "app-server"]}})
        assert changed.status_code == 200, changed.text
    elif change == "revision":
        changed = client.patch("/api/v1/harness/profiles/profile-codex", headers=headers,
            json={"expected_revision": 2, "config": {"command": [sys.executable, "app-server"]}})
        assert changed.status_code == 200, changed.text
    elif change == "secret":
        monkeypatch.setenv("OKTO_MULTIPLEX_FIXTURE", "second-disposable-value")
    else:
        deps.config.feature_hitl = True
    created = client.post("/api/v1/harness/endpoints", headers=headers, json={
        "endpoint_id": "isolated-codex", "agent_id": agent, "adapter_id": "codex",
        "project_root": root, "profile_id": profile, "enabled": True})
    assert created.status_code == 200, created.text
    second = open_endpoint(runtime, "isolated-codex", agent=agent, root=root)
    assert first["connection_id"] != second["connection_id"]
    peers = [deps.harness_supervisor._live[row["session_id"]].connector.native for row in (first, second)]
    assert peers[0]._transport._proc is not peers[1]._transport._proc
    assert all(peer._transport._proc.poll() is None for peer in peers)


@pytest.mark.parametrize("runtime", ["production"], indirect=True)
def test_concurrent_production_opens_share_a_live_connection(runtime):
    from concurrent.futures import ThreadPoolExecutor
    _, client, root, _, operator, _ = runtime
    configure(runtime)
    first = open_endpoint(runtime)
    endpoints = ["concurrent-one", "concurrent-two"]
    for endpoint in endpoints:
        created = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
            "endpoint_id": endpoint, "agent_id": "worker", "adapter_id": "codex",
            "project_root": root, "profile_id": "profile-codex", "enabled": True})
        assert created.status_code == 200, created.text
    with ThreadPoolExecutor(max_workers=2) as executor:
        sessions = list(executor.map(lambda endpoint: open_endpoint(runtime, endpoint), endpoints))
    assert all(row["connection_id"] == first["connection_id"] for row in sessions)
    assert len({row["session_id"] for row in [first, *sessions]}) == 3


@pytest.mark.parametrize("runtime", ["production"], indirect=True)
def test_production_factory_reuses_compatible_connection_and_preserves_sibling(runtime):
    deps, client, root, _, operator, _ = runtime
    headers = {"x-api-key": operator}
    assert not hasattr(deps, "harness_connector_factories")
    Path(root, "app-server").write_text(_FAKE_SERVER_SOURCE, encoding="utf-8")
    configured = client.patch("/api/v1/harness/profiles/profile-codex", headers=headers, json={
        "expected_revision": 1, "config": {"command": [sys.executable, "app-server"]}})
    assert configured.status_code == 200, configured.text
    created = client.post("/api/v1/harness/endpoints", headers=headers, json={
        "endpoint_id": "second-codex", "agent_id": "worker", "adapter_id": "codex",
        "project_root": root, "profile_id": "profile-codex", "enabled": True})
    assert created.status_code == 200, created.text
    sessions = []
    for endpoint in ("endpoint-codex", "second-codex"):
        opened = client.post("/api/v1/harness/sessions", headers=headers, json={
            "agent_id": "worker", "kind": "codex", "endpoint_id": endpoint, "project_root": root})
        assert opened.status_code == 200, opened.text
        sessions.append(opened.json()["data"])
    assert sessions[0]["connection_id"] == sessions[1]["connection_id"], "Production factory never multiplexes"
    first, second = (row["session_id"] for row in sessions)
    peer = deps.harness_supervisor._live[first].connector.native
    assert peer is deps.harness_supervisor._live[second].connector.native
    assert len(peer._sessions_by_thread) == 2
    process = peer._transport._proc
    closed = tool(client, operator, "harness_close", {"session_id": first})
    assert wait_close_result(client, operator, closed)["lifecycle_state"] == "detached"
    assert process.poll() is None
    sent = tool(client, operator, "harness_send", {"session_id": second, "payload": {"text": "sibling survives"}})
    result = wait_operation(runtime, sent["data"]["operation_id"], lambda row: row["result_durable"])
    assert result["result"]["output_text"] == "sibling survives"
    closed = tool(client, operator, "harness_close", {"session_id": second})
    assert wait_close_result(client, operator, closed)["lifecycle_state"] == "stopped"
    assert process.wait(timeout=5) is not None
