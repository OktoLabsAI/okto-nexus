"""Retired Server native factories cannot be revived by legacy profile changes.

Canonical session reuse and sibling lifecycle live in execution_r4/test_session_reuse.py.
"""
import sys
from pathlib import Path

import pytest

from test_pr34_remediation import runtime as runtime_fixture
from test_harness_codex_connector import _FAKE_SERVER_SOURCE

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


def refused_open(runtime, endpoint="endpoint-codex", *, agent="worker", root=None):
    deps, client, default_root, _, operator, _ = runtime
    assert not hasattr(deps, "harness_connector_factories")
    response = client.post("/api/v1/harness/sessions", headers={"x-api-key": operator}, json={
        "agent_id": agent, "kind": "codex", "endpoint_id": endpoint, "project_root": root or default_root})
    assert response.status_code == 409, response.text
    assert response.json()["error"]["details"]["migration_required"] is True
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
    refused_open(runtime, "isolated-codex", agent=agent, root=root)


@pytest.mark.parametrize("runtime", ["production"], indirect=True)
def test_concurrent_retired_native_opens_create_no_connection(runtime):
    from concurrent.futures import ThreadPoolExecutor
    _, client, root, _, operator, _ = runtime
    configure(runtime)
    refused_open(runtime)
    endpoints = ["concurrent-one", "concurrent-two"]
    for endpoint in endpoints:
        created = client.post("/api/v1/harness/endpoints", headers={"x-api-key": operator}, json={
            "endpoint_id": endpoint, "agent_id": "worker", "adapter_id": "codex",
            "project_root": root, "profile_id": "profile-codex", "enabled": True})
        assert created.status_code == 200, created.text
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda endpoint: refused_open(runtime, endpoint), endpoints))
    assert len(responses) == 2


@pytest.mark.parametrize("runtime", ["production"], indirect=True)
def test_retired_native_factory_refuses_even_identical_approved_profiles(runtime):
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
    for endpoint in ("endpoint-codex", "second-codex"):
        refused_open(runtime, endpoint)
