"""Attention HTTP integration over the real services and migrated SQLite store."""

from contextlib import contextmanager
from datetime import datetime, timezone
import importlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
from okto_nexus.adapters.inbound.http.operator_auth import COOKIE
from okto_nexus.adapters.inbound.mcp.tools.inbox import build_service as build_inbox
from okto_nexus.adapters.inbound.mcp.tools.messages import build_service as build_messages
from okto_nexus.application.inbox import DEFAULT_MAX_DELIVERY_ATTEMPTS
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.bootstrap import dependencies, embedded_inventory
from okto_nexus.config import NexusConfig, load_config
from okto_nexus.domain.base import iso_plus, iso_to_epoch
from okto_nexus.errors import OktoNexusError


HEADERS = {"x-nexus-ui": "1", "Origin": "http://testserver"}
ACCOUNT = {"username": "attention-operator", "password": "synthetic-attention-password"}
BASE = "/api/v1/attention"


class Clock:
    def __init__(self):
        self.iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def now_iso(self):
        return self.iso

    def now_epoch(self):
        return iso_to_epoch(self.iso)

    def advance(self, seconds):
        self.iso = iso_plus(self.iso, seconds)


@pytest.fixture
def attention_env(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(dependencies, "SystemClock", lambda: clock)
    monkeypatch.setattr(embedded_inventory, "discover_local_candidates",
                        lambda **_: SimpleNamespace(candidates=()))
    deps = dependencies.bootstrap({}, ["--home", str(tmp_path / "home"),
        "--feature-harness-integrations", "false", "--embedding-mode", "off"])
    with deps.connection_factory.unit_of_work() as uow:
        for workspace in ("attention-one", "attention-two"):
            deps.repos.workspaces.upsert(uow, workspace_id=workspace, display_name=workspace)
        deps.repos.agents.upsert(uow, agent_id="attention-worker")
    app = build_app(deps)
    with TestClient(app, client=("127.0.0.1", 50000), base_url="http://localhost") as client:
        yield SimpleNamespace(deps=deps, app=app, client=client, clock=clock)


def snapshot(env, *, domain_only=False):
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        names = [row[0] for row in uow.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        if domain_only:
            names = [name for name in names if not name.startswith("attention_") and name != "events"]
        return {name: sorted((tuple(row) for row in uow.connection.execute('SELECT * FROM "' + name + '"')),
                             key=repr) for name in names}


def parked(env, *, count=1, workspace="attention-one"):
    """Reach the canonical parked lane by exhausting real inbox leases."""
    service = build_messages(env.deps)
    ids = [service.create_message(workspace_id=workspace, from_agent_id="operator",
        subject="Attention fixture", body="private-attention-payload-marker",
        target={"strategy": "direct", "agent_id": "attention-worker"})["message_id"]
        for _ in range(count)]
    inbox = build_inbox(env.deps)
    for _ in range(DEFAULT_MAX_DELIVERY_ATTEMPTS):
        pulled = inbox.pull(agent_id="attention-worker", limit=200, lease_seconds=60)
        assert {item["message_id"] for item in pulled["messages"]} == set(ids)
        env.clock.advance(61)
    assert inbox.pull(agent_id="attention-worker", limit=200, lease_seconds=60)["count"] == 0
    with env.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM message_deliveries "
            "WHERE status='parked' AND message_id IN (" + ",".join("?" for _ in ids) + ")", ids).fetchone()[0] == count
    return ids


def data(response):
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["ok"] is True
    return response.json()["data"]


def item(env):
    view = data(env.client.get(BASE, params={"kind": "delivery_parked"}))
    assert view["total"] == 1
    return view["items"][0]


def revision_body(value):
    return {"source_revision": value["source_revision"],
            "preference_revision": value["seen_state"]["revision"]}


def preference(response):
    result = data(response)
    assert result["version"] == 1 and result["observed_at"]
    return result["item"]


@contextmanager
def device(app, **kwargs):
    """Another HTTP client of the one server already started by the fixture."""
    client = TestClient(app, **kwargs)
    try:
        yield client
    finally:
        client.close()


def test_empty_list_and_summary_are_explicit_passive_snapshots(attention_env):
    env = attention_env
    before = snapshot(env)
    listing = data(env.client.get(BASE))
    summary = data(env.client.get(BASE + "/summary"))
    assert listing["version"] == summary["version"] == 1
    assert listing["items"] == [] and listing["total"] == summary["total"] == 0
    assert listing["counts"] == summary["counts"]
    assert listing["event_cursor"] == summary["event_cursor"]
    assert listing["next_cursor"] is None
    assert listing["snapshot_revision"] == summary["snapshot_revision"]
    assert listing["observed_at"] and 0 < listing["refresh_after_seconds"] <= 15
    assert "next_refresh_at" in listing
    assert snapshot(env) == before


@pytest.mark.parametrize("family", ["native", "operations"])
@pytest.mark.parametrize("path", [BASE, BASE + "/summary"])
def test_policy_read_failure_is_sanitized_and_never_an_empty_success(attention_env, monkeypatch, family, path):
    env = attention_env
    adapter = importlib.import_module("okto_nexus.adapters.outbound.sqlite.attention_" + family)
    original = adapter.build_policy
    before = snapshot(env)

    def unavailable(uow, **kwargs):
        # Fail a real SQLite query while preparing authority, before UDF setup.
        uow.connection.execute("SELECT * FROM private_attention_failure_marker")

    monkeypatch.setattr(adapter, "build_policy", unavailable)
    response = env.client.get(path)
    assert response.status_code == 503, response.text
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "DB_ERROR"
    assert "private_attention_failure_marker" not in response.text
    assert "OperationalError" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert snapshot(env) == before
    monkeypatch.setattr(adapter, "build_policy", original)
    assert data(env.client.get(path))["total"] == 0
    assert snapshot(env) == before


@pytest.mark.parametrize("path", [BASE, BASE + "/summary"])
def test_existing_operator_auth_paths_and_agent_refusal(attention_env, path):
    env = attention_env
    _, operator_key = ensure_operator_key(env.deps, env.app.state.auth)
    with env.deps.connection_factory.unit_of_work() as uow:
        worker_key = env.app.state.auth.issue_key(uow, agent_id="attention-worker")
    auth = env.app.state.operator_auth
    auth.configure(**ACCOUNT, local=True)
    with device(env.app, client=("192.0.2.25", 50001)) as remote:
        assert remote.get(path).status_code == 401
        assert data(remote.get(path, headers={"x-api-key": operator_key}))["version"] == 1
        assert remote.get(path, headers={"x-api-key": worker_key}).status_code == 403
        remote.cookies.set(COOKIE, auth.login(**ACCOUNT))
        assert data(remote.get(path))["version"] == 1
        assert remote.get(path, headers={"x-api-key": worker_key}).status_code == 403
        assert remote.post("/api/v1/operator-auth/logout", headers=HEADERS).status_code == 200
        assert remote.get(path).status_code == 401
    assert env.deps.config.feature_harness_integrations is False


@pytest.mark.parametrize("query", [
    {"category": "wrong"}, {"kind": "invented"}, {"state": "unknown"},
    {"priority": "11"}, {"priority": "true"}, {"seen": "wrong"},
    {"limit": "0"}, {"limit": "201"}, {"limit": "false"}, {"workspace": "attention-one"},
    [("workspace_id", "attention-one"), ("workspace_id", "attention-two")],
])
def test_invalid_filters_use_envelope_and_never_write(attention_env, query):
    before = snapshot(attention_env)
    response = attention_env.client.get(BASE, params=query)
    assert response.status_code == 422, response.text
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.headers["cache-control"] == "no-store"
    assert snapshot(attention_env) == before


@pytest.mark.parametrize("suffix,body", [
    ("seen", {}), ("seen", {"source_revision": "private-marker", "preference_revision": True}),
    ("seen", {"source_revision": "private-marker", "preference_revision": 0, "seen": "false"}),
    ("seen", {"source_revision": "private-marker", "preference_revision": 0, "principal": "other"}),
    ("snooze", {"source_revision": "private-marker", "preference_revision": 0}),
    ("snooze", {"source_revision": "private-marker", "preference_revision": 0, "until": 999}),
])
def test_invalid_preferences_are_strict_and_do_not_echo_values(attention_env, suffix, body):
    before = snapshot(attention_env)
    response = attention_env.client.post(BASE + "/missing/" + suffix, json=body)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.headers["cache-control"] == "no-store"
    assert "private-marker" not in response.text
    assert snapshot(attention_env) == before


def test_canonical_parked_source_filters_summary_and_payload_privacy(attention_env):
    env = attention_env
    parked(env, count=2)
    parked(env, workspace="attention-two")
    before = snapshot(env)
    filters = {"workspace_id": "attention-one", "agent_id": "attention-worker",
               "kind": "delivery_parked", "state": "open", "seen": "unseen"}
    listing = data(env.client.get(BASE, params=filters))
    summary = data(env.client.get(BASE + "/summary", params=filters))
    assert listing["total"] == summary["total"] == 2
    assert listing["counts"] == summary["counts"]
    assert listing["snapshot_revision"] == summary["snapshot_revision"]
    assert {value["workspace_id"] for value in listing["items"]} == {"attention-one"}
    assert {value["kind"] for value in listing["items"]} == {"delivery_parked"}
    assert "private-attention-payload-marker" not in str(listing)
    assert snapshot(env) == before


def test_cursor_has_stable_ties_and_cannot_change_filters(attention_env):
    env = attention_env
    parked(env, count=3)
    filters = {"kind": "delivery_parked", "workspace_id": "attention-one", "limit": 1}
    first = data(env.client.get(BASE, params=filters))
    second = data(env.client.get(BASE, params={**filters, "cursor": first["next_cursor"]}))
    third = data(env.client.get(BASE, params={**filters, "cursor": second["next_cursor"]}))
    assert first["total"] == second["total"] == third["total"] == 3
    assert len({page["items"][0]["attention_id"] for page in (first, second, third)}) == 3
    assert third["next_cursor"] is None
    for query in ({**filters, "cursor": "forged"},
                  {**filters, "cursor": first["next_cursor"], "workspace_id": "attention-two"}):
        assert env.client.get(BASE, params=query).status_code == 409
    original = first["items"][0]
    data(env.client.post(BASE + "/" + original["attention_id"] + "/seen", json=revision_body(original)))
    changed = env.client.get(BASE, params={**filters, "cursor": first["next_cursor"]})
    assert changed.status_code == 409
    assert changed.json()["error"]["details"]["reason"] == "ATTENTION_SNAPSHOT_CHANGED"


def test_real_projection_budget_failure_is_unavailable_never_empty(attention_env, monkeypatch):
    env = attention_env
    parked(env)
    # Targeted budget fault at the SQL adapter; projection and HTTP remain real.
    monkeypatch.setattr(env.app.state.attention.queries, "QUERY_SECONDS", 0)
    before = snapshot(env)
    for path in (BASE, BASE + "/summary"):
        result = env.client.get(path)
        assert result.status_code == 503, result.text
        assert result.json()["ok"] is False and "data" not in result.json()
        assert result.json()["error"]["code"] == "ATTENTION_QUERY_BUDGET"
        assert result.headers["cache-control"] == "no-store"
    assert snapshot(env) == before


def test_preferences_are_shared_between_devices_cas_and_independent_from_resolution(attention_env):
    env = attention_env
    parked(env)
    original = item(env)
    before = snapshot(env, domain_only=True)
    env.app.state.operator_auth.configure(**ACCOUNT, local=True)
    with device(env.app, client=("192.0.2.30", 50001)) as first, \
            device(env.app, client=("192.0.2.31", 50002)) as second:
        for client in (first, second):
            assert client.post("/api/v1/operator-auth/login", json=ACCOUNT, headers=HEADERS).status_code == 200
        path = BASE + "/" + original["attention_id"]
        seen = preference(first.post(path + "/seen", json=revision_body(original), headers=HEADERS))
        assert seen["seen_state"]["seen"] is True
        assert seen["seen_state"]["revision"] == original["seen_state"]["revision"] + 1
        observed = data(second.get(BASE, params={"kind": "delivery_parked"}))["items"][0]
        assert observed["seen_state"] == seen["seen_state"]
        assert second.post(path + "/seen", json=revision_body(original), headers=HEADERS).status_code == 409
        until = iso_plus(env.clock.now_iso(), 60)
        snoozed = preference(second.post(path + "/snooze", json={**revision_body(seen), "until": until}, headers=HEADERS))
        assert snoozed["seen_state"]["snoozed"] is True
        assert iso_to_epoch(snoozed["seen_state"]["snoozed_until"]) == iso_to_epoch(until)
        assert snoozed["resolution"] == original["resolution"]
        assert data(first.get(BASE, params={"kind": "delivery_parked", "seen": "snoozed", "state": "all"}))["total"] == 1
        unsnoozed = preference(first.post(path + "/snooze", json={**revision_body(snoozed), "until": None}, headers=HEADERS))
        assert unsnoozed["seen_state"]["snoozed"] is False
        unseen = preference(second.post(path + "/seen", json={**revision_body(unsnoozed), "seen": False}, headers=HEADERS))
        assert unseen["seen_state"]["seen"] is False
    assert snapshot(env, domain_only=True) == before


def test_missing_and_changed_sources_never_create_preferences(attention_env):
    env = attention_env
    parked(env)
    original = item(env)
    before = snapshot(env)
    missing = env.client.post(BASE + "/missing/seen", json=revision_body(original))
    assert missing.status_code == 404, missing.text
    changed = env.client.post(BASE + "/" + original["attention_id"] + "/seen",
        json={**revision_body(original), "source_revision": "forged-source-revision"})
    assert changed.status_code == 409, changed.text
    assert snapshot(env) == before


def test_snooze_expiry_is_derived_without_a_read_side_write(attention_env):
    env = attention_env
    parked(env)
    original = item(env)
    snoozed = preference(env.client.post(BASE + "/" + original["attention_id"] + "/snooze",
        json={**revision_body(original), "until": iso_plus(env.clock.now_iso(), 5)}))
    listing = data(env.client.get(BASE, params={"kind": "delivery_parked"}))
    assert 0 < listing["refresh_after_seconds"] <= 5
    env.clock.advance(6)
    before = snapshot(env)
    current = item(env)
    assert current["seen_state"]["snoozed"] is False
    assert current["seen_state"]["revision"] == snoozed["seen_state"]["revision"]
    assert current["resolution"] == original["resolution"]
    assert snapshot(env) == before


def test_agent_cannot_mutate_preferences_even_with_an_operator_cookie(attention_env):
    env = attention_env
    parked(env)
    original = item(env)
    with env.deps.connection_factory.unit_of_work() as uow:
        key = env.app.state.auth.issue_key(uow, agent_id="attention-worker")
    env.app.state.operator_auth.configure(**ACCOUNT, local=True)
    with device(env.app, client=("192.0.2.32", 50001)) as remote:
        remote.cookies.set(COOKIE, env.app.state.operator_auth.login(**ACCOUNT))
        # Warm the existing authentication audit before the domain snapshot.
        assert remote.get(BASE, headers={"x-api-key": key}).status_code == 403
        before = snapshot(env)
        for suffix, extra in (("seen", {}), ("snooze", {"until": None})):
            result = remote.post(BASE + "/" + original["attention_id"] + "/" + suffix,
                json={**revision_body(original), **extra}, headers={**HEADERS, "x-api-key": key})
            assert result.status_code == 403
        assert snapshot(env) == before


def test_operator_key_rotation_is_checked_after_warm_http_auth(attention_env):
    env = attention_env
    _, key = ensure_operator_key(env.deps, env.app.state.auth)
    with device(env.app, client=("192.0.2.33", 50001)) as remote:
        data(remote.get(BASE, headers={"x-api-key": key}))
        independent_auth = AgentKeyAuthService(env.deps.repos.agents, env.deps.clock)
        with env.deps.connection_factory.unit_of_work() as uow:
            replacement = independent_auth.issue_key(uow, agent_id="operator")
        result = remote.get(BASE, headers={"x-api-key": key})
        assert result.status_code in (401, 403), result.text
        data(remote.get(BASE, headers={"x-api-key": replacement}))


def test_preferences_survive_server_restart(attention_env):
    env = attention_env
    parked(env)
    original = item(env)
    seen = preference(env.client.post(BASE + "/" + original["attention_id"] + "/seen", json=revision_body(original)))
    restarted = dependencies.bootstrap({}, ["--home", str(env.deps.config.home_dir),
        "--feature-harness-integrations", "false", "--embedding-mode", "off"])
    with TestClient(build_app(restarted), client=("127.0.0.1", 50001)) as client:
        current = data(client.get(BASE, params={"kind": "delivery_parked"}))["items"][0]
        assert current["attention_id"] == original["attention_id"]
        assert current["seen_state"] == seen["seen_state"]


@pytest.mark.parametrize("headers", [{}, {"Origin": "https://evil.example", "x-nexus-ui": "1"},
                                    {"Sec-Fetch-Site": "cross-site", "x-nexus-ui": "1"}])
def test_human_preference_mutations_require_existing_csrf_protection(attention_env, headers):
    env = attention_env
    parked(env)
    original = item(env)
    env.app.state.operator_auth.configure(**ACCOUNT, local=True)
    with device(env.app, client=("192.0.2.30", 50001)) as remote:
        remote.cookies.set(COOKIE, env.app.state.operator_auth.login(**ACCOUNT))
        before = snapshot(env)
        for suffix, extra in (("seen", {}), ("snooze", {"until": None})):
            result = remote.post(BASE + "/" + original["attention_id"] + "/" + suffix,
                                 json={**revision_body(original), **extra}, headers=headers)
            assert result.status_code == 403
        assert snapshot(env) == before


def test_feature_off_is_explicit_and_leaves_original_paths_and_domain_intact(attention_env):
    env = attention_env
    parked(env)
    original = item(env)
    before = snapshot(env, domain_only=True)
    assert env.client.patch("/api/v1/settings", json={"feature_attention": False}).status_code == 200
    expected = snapshot(env, domain_only=True)
    assert {k: v for k, v in expected.items() if k != "settings"} == {k: v for k, v in before.items() if k != "settings"}
    for response in (env.client.get(BASE), env.client.get(BASE + "/summary"),
                     env.client.post(BASE + "/" + original["attention_id"] + "/seen", json=revision_body(original))):
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "FEATURE_DISABLED"
    assert env.client.get("/api/v1/approvals", params={"workspace": "attention-one"}).status_code == 200
    assert env.client.get("/api/v1/handoffs", params={"workspace": "attention-one"}).status_code == 200
    assert snapshot(env, domain_only=True) == expected
    assert env.deps.config.feature_harness_integrations is False


def test_attention_settings_catalog_bounds_persistence_and_no_runtime_coupling(attention_env):
    env = attention_env
    settings = {v["key"]: v for v in env.client.get("/api/v1/settings").json()["data"]["items"]}
    assert settings["feature_attention"]["value"] is True
    for name in ("attention_unclaimed_seconds", "attention_disconnected_seconds"):
        assert settings[name]["value"] == 300
        assert (settings[name]["min"], settings[name]["max"]) == (0, 86400)
        for invalid in (-1, 86401, True, False, 0.5, "0"):
            assert env.client.patch("/api/v1/settings", json={name: invalid}).status_code == 422
    values = {"feature_attention": False, "attention_unclaimed_seconds": 0, "attention_disconnected_seconds": 86400}
    assert env.client.patch("/api/v1/settings", json=values).status_code == 200
    assert all(getattr(env.deps.config, name) == value for name, value in values.items())
    assert env.deps.config.feature_harness_integrations is False
    restarted = dependencies.bootstrap({}, ["--home", str(env.deps.config.home_dir),
        "--feature-harness-integrations", "false", "--embedding-mode", "off"])
    build_app(restarted)
    assert all(getattr(restarted.config, name) == value for name, value in values.items())


@pytest.mark.parametrize("source", ["env", "cli"])
def test_attention_settings_explicit_defaults_pin_stored_overrides(attention_env, source):
    env = attention_env
    assert env.client.patch("/api/v1/settings", json={"feature_attention": False,
        "attention_unclaimed_seconds": 7}).status_code == 200
    environ = {"OKTO_NEXUS_FEATURE_ATTENTION": "true", "OKTO_NEXUS_ATTENTION_UNCLAIMED_SECONDS": "300"} if source == "env" else {}
    args = ["--home", str(env.deps.config.home_dir), "--feature-harness-integrations", "false", "--embedding-mode", "off"]
    if source == "cli":
        args += ["--feature-attention", "true", "--attention-unclaimed-seconds", "300"]
    restarted = dependencies.bootstrap(environ, args)
    with TestClient(build_app(restarted), client=("127.0.0.1", 50001)) as client:
        settings = {v["key"]: v for v in client.get("/api/v1/settings").json()["data"]["items"]}
        for key, expected in (("feature_attention", True), ("attention_unclaimed_seconds", 300)):
            assert settings[key]["value"] == expected
            assert settings[key]["source"] == "cli/env" and not settings[key]["editable"]
            assert client.patch("/api/v1/settings", json={key: expected}).status_code == 422


@pytest.mark.parametrize("name", ["attention_unclaimed_seconds", "attention_disconnected_seconds"])
def test_attention_threshold_config_bounds_and_zero(name):
    flag = "--" + name.replace("_", "-")
    env = "OKTO_NEXUS_" + name.upper()
    assert getattr(load_config({env: "3"}, [flag, "0"]), name) == 0
    for invalid in (-1, 86401, True):
        with pytest.raises(OktoNexusError, match="0..86400"):
            NexusConfig(**{name: invalid})
    with pytest.raises(OktoNexusError):
        load_config({env: "86401"})
