"""Retired Server native factories cannot be revived by legacy profile changes.

Canonical session reuse and sibling lifecycle live in execution_r4/test_session_reuse.py.
"""
import sys
from pathlib import Path

import pytest

from test_pr34_remediation import runtime as runtime_fixture
from test_harness_codex_connector import _FAKE_SERVER_SOURCE

runtime = runtime_fixture


def retained_profile(runtime, profile="profile-codex", *, secret=False):
    from okto_nexus.adapters.outbound.sqlite.endpoints_repo import SqliteEndpointRepo
    deps = runtime[0]
    with deps.connection_factory.unit_of_work() as uow:
        SqliteEndpointRepo().put_profile(uow, profile_id=profile, adapter_id="codex",
            config={"command": [sys.executable, "app-server"]},
            secret_refs={"FIXTURE_CREDENTIAL": "env:OKTO_MULTIPLEX_FIXTURE"} if secret else {},
            inherit_ambient=False, enabled=True, now=deps.clock.now_iso())


def retained_endpoint(runtime, endpoint, *, profile="profile-codex", agent="worker", root=None):
    from okto_nexus.adapters.outbound.sqlite.endpoints_repo import SqliteEndpointRepo
    from okto_nexus.domain.endpoints import AgentEndpoint
    from okto_nexus.domain.ids import resolve_workspace_id
    deps, _, default_root, *_ = runtime
    root = root or default_root
    workspace = resolve_workspace_id(root)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=workspace, root_realpath=root)
        SqliteEndpointRepo().create(uow, endpoint=AgentEndpoint(endpoint, agent, "codex", workspace,
            "codex-app-server", runtime_profile_id=profile, enabled=True, activation_state="approved"),
            now=deps.clock.now_iso())


def configure(runtime, *, secret=False):
    # Retained pre-cutover data, not new setup through a removed API.
    Path(runtime[2], "app-server").write_text(_FAKE_SERVER_SOURCE, encoding="utf-8")
    retained_profile(runtime, secret=secret)
    retained_endpoint(runtime, "endpoint-codex")


def open_endpoint(runtime, endpoint="endpoint-codex", *, agent="worker", root=None):
    _, client, default_root, _, operator, _ = runtime
    opened = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": agent, "kind": "codex", "endpoint_id": endpoint, "project_root": root or default_root})
    assert opened.status_code == 200, opened.text
    return opened.json()["data"]


def refused_open(runtime, endpoint="endpoint-codex", *, agent="worker", root=None):
    deps, client, default_root, _, operator, _ = runtime
    assert not hasattr(deps, "harness_connector_factories")
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": agent, "kind": "codex", "endpoint_id": endpoint, "project_root": root or default_root})
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "CONFLICT"
    assert "Legacy connection setup was removed" in response.text
    assert not deps.harness_supervisor.list_live()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM harness_sessions").fetchone()[0] == 0
    return response


@pytest.mark.parametrize("runtime", ["production"], indirect=True)
@pytest.mark.parametrize("change", ["agent", "workspace", "profile", "revision", "secret", "hitl"])
def test_retired_native_factory_refuses_changed_effective_context(runtime, monkeypatch, change):
    deps, client, root, _, operator, _ = runtime
    monkeypatch.setenv("OKTO_MULTIPLEX_FIXTURE", "first-disposable-value")
    configure(runtime, secret=change == "secret")
    refused_open(runtime)
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
        retained_profile(runtime, profile)
    elif change == "revision":
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE runtime_profiles SET revision=revision+1")
    elif change == "secret":
        monkeypatch.setenv("OKTO_MULTIPLEX_FIXTURE", "second-disposable-value")
    else:
        deps.config.feature_hitl = True
    retained_endpoint(runtime, "isolated-codex", agent=agent, profile=profile, root=root)
    refused_open(runtime, "isolated-codex", agent=agent, root=root)


@pytest.mark.parametrize("runtime", ["production"], indirect=True)
def test_concurrent_retired_native_opens_create_no_connection(runtime):
    from concurrent.futures import ThreadPoolExecutor
    _, client, root, _, operator, _ = runtime
    configure(runtime)
    refused_open(runtime)
    endpoints = ["concurrent-one", "concurrent-two"]
    for endpoint in endpoints:
        retained_endpoint(runtime, endpoint)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda endpoint: refused_open(runtime, endpoint), endpoints))
    assert len(responses) == 2


@pytest.mark.parametrize("runtime", ["production"], indirect=True)
def test_retired_native_factory_refuses_even_identical_approved_profiles(runtime):
    deps, client, root, _, operator, _ = runtime
    headers = {"x-api-key": operator}
    assert not hasattr(deps, "harness_connector_factories")
    Path(root, "app-server").write_text(_FAKE_SERVER_SOURCE, encoding="utf-8")
    configure(runtime)
    retained_endpoint(runtime, "second-codex")
    for endpoint in ("endpoint-codex", "second-codex"):
        refused_open(runtime, endpoint)
