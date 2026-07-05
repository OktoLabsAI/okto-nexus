"""Central tag catalog (migration 013): service + repo contract + REST.

The same CONTRACT scenarios run against BOTH TagCatalogRepo implementations
(the in-memory fake below and the real SQLite adapter over a migrated store),
mirroring ``test_ports_contract`` - fake-drift on the catalog would silently
weaken the fail-closed rule. On top: TagCatalogService semantics (register /
duplicate / delete guards / the EXACT ``TAG_IN_USE`` payload shape / the
``ensure_registered`` existence gate) and the ``/api/v1/tags`` REST surface
including the normative 409 envelope.
"""

from __future__ import annotations

import pytest

from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.adapters.outbound.sqlite.tag_catalog_repo import SqliteTagCatalogRepo
from okto_nexus.application.ports import TagCatalogRepo
from okto_nexus.application.tags import TagCatalogService
from okto_nexus.domain.models import Agent, TagKey, TagValue
from okto_nexus.errors import ErrorCode, OktoNexusError

from test_shared_md import FakeConnectionFactory


class FakeTagCatalogRepo:
    """In-memory TagCatalogRepo honouring the port contract."""

    def __init__(self) -> None:
        self.keys: dict[str, TagKey] = {}
        self.values: dict[tuple[str, str], TagValue] = {}

    def create_key(self, uow, *, key, description=None):
        if key in self.keys:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"Tag key '{key}' is already registered.",
                {"key": key},
            )
        self.keys[key] = TagKey(key=key, description=description, created_at="t0")
        return self.keys[key]

    def get_key(self, uow, key):
        return self.keys.get(key)

    def list_keys(self, uow):
        return [self.keys[k] for k in sorted(self.keys)]

    def delete_key(self, uow, *, key):
        if key not in self.keys:
            return False
        del self.keys[key]
        for pair in [p for p in self.values if p[0] == key]:
            del self.values[pair]  # the adapter's ON DELETE CASCADE
        return True

    def create_value(self, uow, *, key, value, description=None):
        if key not in self.keys:
            raise OktoNexusError(
                ErrorCode.NOT_FOUND,
                f"Tag key '{key}' is not registered; register the key "
                "before adding values.",
                {"key": key},
            )
        if (key, value) in self.values:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"Tag value '{key}={value}' is already registered.",
                {"key": key, "value": value},
            )
        self.values[(key, value)] = TagValue(
            key=key, value=value, description=description, created_at="t0"
        )
        return self.values[(key, value)]

    def get_value(self, uow, *, key, value):
        return self.values.get((key, value))

    def list_values(self, uow, *, key=None):
        pairs = sorted(p for p in self.values if key is None or p[0] == key)
        return [self.values[p] for p in pairs]

    def delete_value(self, uow, *, key, value):
        return self.values.pop((key, value), None) is not None


class FakeAgentRepo:
    """Minimal agents port for the usage scan (list + set_* mirrors)."""

    def __init__(self) -> None:
        self.rows: dict[str, Agent] = {}

    def add(self, agent_id, *, tags=None, comm_scope=None) -> Agent:
        agent = Agent(
            agent_id=agent_id,
            created_at="t0",
            tags=tags or {},
            comm_scope=comm_scope,
        )
        self.rows[agent_id] = agent
        return agent

    def list(self, uow):
        return list(self.rows.values())


class _Backend:
    def __init__(self, name, catalog, agents, uow_factory, seed_agent) -> None:
        self.name = name
        self.catalog = catalog
        self.agents = agents
        self.uow = uow_factory
        self.seed_agent = seed_agent
        self.service = TagCatalogService(catalog=catalog, agents=agents)


@pytest.fixture(params=["fake", "sqlite"])
def backend(request, migrated_factory) -> _Backend:
    if request.param == "fake":
        agents = FakeAgentRepo()

        def seed(agent_id, *, tags=None, comm_scope=None):
            agents.add(agent_id, tags=tags, comm_scope=comm_scope)

        return _Backend(
            "fake",
            FakeTagCatalogRepo(),
            agents,
            FakeConnectionFactory().unit_of_work,
            seed,
        )
    agents = SqliteAgentRepo()

    def seed(agent_id, *, tags=None, comm_scope=None):
        with migrated_factory.unit_of_work() as uow:
            agents.upsert(uow, agent_id=agent_id)
            if tags is not None:
                agents.set_tags(uow, agent_id=agent_id, tags=tags)
            if comm_scope is not None:
                agents.set_comm_scope(uow, agent_id=agent_id, comm_scope=comm_scope)

    return _Backend(
        "sqlite",
        SqliteTagCatalogRepo(),
        agents,
        migrated_factory.unit_of_work,
        seed,
    )


def _register(backend: _Backend, key: str, *values: str) -> None:
    with backend.uow() as uow:
        backend.service.register_key(uow, key=key)
        for value in values:
            backend.service.register_value(uow, key=key, value=value)


# --------------------------------------------------------------------------- #
# Contract: registry CRUD on both implementations
# --------------------------------------------------------------------------- #
def test_contract_adapter_satisfies_protocol(backend):
    assert isinstance(backend.catalog, TagCatalogRepo)


def test_contract_register_and_snapshot(backend):
    _register(backend, "team", "backend", "infra")
    _register(backend, "env", "prod")
    with backend.uow() as uow:
        snapshot = backend.service.snapshot(uow)
    assert [entry["key"] for entry in snapshot] == ["env", "team"]
    team = next(e for e in snapshot if e["key"] == "team")
    assert [v["value"] for v in team["values"]] == ["backend", "infra"]


def test_contract_duplicate_key_and_value_are_validation_errors(backend):
    _register(backend, "team", "backend")
    with backend.uow() as uow:
        with pytest.raises(OktoNexusError) as ei:
            backend.service.register_key(uow, key="team")
        assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
        assert "already registered" in ei.value.message
        with pytest.raises(OktoNexusError) as ei:
            backend.service.register_value(uow, key="team", value="backend")
        assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


def test_contract_value_requires_registered_key(backend):
    with backend.uow() as uow:
        with pytest.raises(OktoNexusError) as ei:
            backend.service.register_value(uow, key="ghost", value="x")
    assert ei.value.code == ErrorCode.NOT_FOUND.value


def test_contract_delete_unknown_key_or_value_is_not_found(backend):
    with backend.uow() as uow:
        with pytest.raises(OktoNexusError) as ei:
            backend.service.delete_key(uow, key="ghost")
        assert ei.value.code == ErrorCode.NOT_FOUND.value
        with pytest.raises(OktoNexusError) as ei:
            backend.service.delete_value(uow, key="ghost", value="x")
        assert ei.value.code == ErrorCode.NOT_FOUND.value


def test_contract_deleting_unused_key_cascades_values(backend):
    _register(backend, "team", "backend", "infra")
    with backend.uow() as uow:
        assert backend.service.delete_key(uow, key="team") == {
            "key": "team",
            "deleted": True,
        }
        assert backend.catalog.list_values(uow) == []
        assert backend.catalog.list_keys(uow) == []


# --------------------------------------------------------------------------- #
# TAG_IN_USE: the AC3 payload shape, byte-exact structure
# --------------------------------------------------------------------------- #
def test_delete_key_in_use_by_agent_tags_raises_tag_in_use(backend):
    _register(backend, "team", "backend")
    backend.seed_agent("worker-1", tags={"team": ["backend"]})
    with backend.uow() as uow:
        with pytest.raises(OktoNexusError) as ei:
            backend.service.delete_key(uow, key="team")
    err = ei.value
    assert err.code == ErrorCode.TAG_IN_USE.value
    assert err.details == {
        "key": "team",
        "value": None,
        "total_uses": 1,
        "uses": [{"agent_id": "worker-1", "kind": "agent_tags"}],
    }
    # Nothing was deleted.
    with backend.uow() as uow:
        assert backend.catalog.get_key(uow, "team") is not None


def test_delete_value_in_use_by_comm_scope_raises_tag_in_use(backend):
    _register(backend, "team", "backend", "infra")
    backend.seed_agent("sender-1", comm_scope={"outbound": {"team": ["backend"]}})
    with backend.uow() as uow:
        with pytest.raises(OktoNexusError) as ei:
            backend.service.delete_value(uow, key="team", value="backend")
    err = ei.value
    assert err.code == ErrorCode.TAG_IN_USE.value
    assert err.details == {
        "key": "team",
        "value": "backend",
        "total_uses": 1,
        "uses": [{"agent_id": "sender-1", "kind": "comm_scope"}],
    }
    # The UNUSED sibling value still deletes fine.
    with backend.uow() as uow:
        result = backend.service.delete_value(uow, key="team", value="infra")
    assert result["deleted"] is True


def test_delete_value_in_use_by_inbound_scope_raises_tag_in_use(backend):
    # The F2 inbound leg counts as a comm_scope use exactly like outbound -
    # deleting the pair would orphan the selector and silently widen reach.
    _register(backend, "sector", "ops")
    backend.seed_agent("guarded-1", comm_scope={"inbound": {"sector": ["ops"]}})
    with backend.uow() as uow:
        with pytest.raises(OktoNexusError) as ei:
            backend.service.delete_value(uow, key="sector", value="ops")
    err = ei.value
    assert err.code == ErrorCode.TAG_IN_USE.value
    assert err.details["uses"] == [{"agent_id": "guarded-1", "kind": "comm_scope"}]


def test_scope_using_pair_on_both_legs_counts_once(backend):
    _register(backend, "team", "backend")
    backend.seed_agent(
        "both-legs",
        comm_scope={
            "outbound": {"team": ["backend"]},
            "inbound": {"team": ["backend"]},
        },
    )
    with backend.uow() as uow:
        with pytest.raises(OktoNexusError) as ei:
            backend.service.delete_key(uow, key="team")
    assert ei.value.details["uses"] == [{"agent_id": "both-legs", "kind": "comm_scope"}]


def test_tag_in_use_lists_every_agent_and_kind_sorted(backend):
    _register(backend, "team", "backend")
    backend.seed_agent(
        "a-both",
        tags={"team": ["backend"]},
        comm_scope={"outbound": {"team": ["backend"]}},
    )
    backend.seed_agent("b-tags", tags={"team": ["backend"]})
    with backend.uow() as uow:
        with pytest.raises(OktoNexusError) as ei:
            backend.service.delete_key(uow, key="team")
    details = ei.value.details
    assert details["total_uses"] == 3
    assert details["uses"] == [
        {"agent_id": "a-both", "kind": "agent_tags"},
        {"agent_id": "a-both", "kind": "comm_scope"},
        {"agent_id": "b-tags", "kind": "agent_tags"},
    ]


def test_value_delete_ignores_other_values_of_the_same_key(backend):
    _register(backend, "team", "backend", "infra")
    backend.seed_agent("worker-1", tags={"team": ["backend"]})
    with backend.uow() as uow:
        result = backend.service.delete_value(uow, key="team", value="infra")
    assert result["deleted"] is True


# --------------------------------------------------------------------------- #
# ensure_registered: the fail-closed existence gate
# --------------------------------------------------------------------------- #
def test_ensure_registered_passes_for_registered_pairs(backend):
    _register(backend, "team", "backend")
    with backend.uow() as uow:
        backend.service.ensure_registered(
            uow, {"team": ["backend"]}, field="tags"
        )  # no raise
        backend.service.ensure_registered(uow, None, field="tags")  # no-op


def test_ensure_registered_rejects_unknown_key_and_value(backend):
    _register(backend, "team", "backend")
    with backend.uow() as uow:
        with pytest.raises(OktoNexusError) as ei:
            backend.service.ensure_registered(
                uow,
                {"team": ["backend", "ghost"], "unregistered": ["x"]},
                field="tags",
            )
    err = ei.value
    assert err.code == ErrorCode.VALIDATION_ERROR.value
    assert err.details["field"] == "tags"
    assert {
        (u["key"], u["value"], u["missing"]) for u in err.details["unregistered"]
    } == {
        ("team", "ghost", "value"),
        ("unregistered", "x", "key"),
    }
    assert "fail-closed" in err.message


# --------------------------------------------------------------------------- #
# REST surface: /api/v1/tags (shape per the Tag Registry mockup + AC3)
# --------------------------------------------------------------------------- #
@pytest.fixture
def http_env(tmp_path):
    fastapi = pytest.importorskip("fastapi")  # noqa: F841
    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
    from okto_nexus.adapters.inbound.mcp.server import bootstrap
    from okto_nexus.application.auth import AgentKeyAuthService

    deps = bootstrap({}, ["--home", str(tmp_path / "nexus_home")])
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    issued = ensure_operator_key(deps, auth)
    assert issued is not None
    _, operator_key = issued
    app = build_app(deps)
    with TestClient(app) as client:
        yield deps, client, {"x-api-key": operator_key}


def test_rest_tags_crud_roundtrip(http_env):
    _, client, headers = http_env

    created = client.post(
        "/api/v1/tags",
        json={"key": "team", "description": "Owning squad"},
        headers=headers,
    )
    assert created.status_code == 200
    assert created.json()["data"]["key"] == "team"

    value = client.post(
        "/api/v1/tags/team/values", json={"value": "backend"}, headers=headers
    )
    assert value.status_code == 200
    assert value.json()["data"] == {
        "key": "team",
        "value": "backend",
        "description": None,
        "created_at": value.json()["data"]["created_at"],
    }

    listing = client.get("/api/v1/tags", headers=headers).json()["data"]
    assert listing["items"][0]["key"] == "team"
    assert [v["value"] for v in listing["items"][0]["values"]] == ["backend"]

    # Duplicates surface as 409 CONFLICT (registry is idempotent-hostile).
    assert (
        client.post("/api/v1/tags", json={"key": "team"}, headers=headers).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/tags/team/values", json={"value": "backend"}, headers=headers
        ).status_code
        == 409
    )

    # Unused value + key delete cleanly.
    gone = client.delete("/api/v1/tags/team/values/backend", headers=headers)
    assert gone.status_code == 200 and gone.json()["data"]["deleted"] is True
    gone = client.delete("/api/v1/tags/team", headers=headers)
    assert gone.status_code == 200 and gone.json()["data"]["deleted"] is True
    assert client.delete("/api/v1/tags/team", headers=headers).status_code == 404


def test_rest_delete_in_use_returns_409_with_the_exact_ac3_envelope(http_env):
    deps, client, headers = http_env
    client.post("/api/v1/tags", json={"key": "team"}, headers=headers)
    client.post("/api/v1/tags/team/values", json={"value": "backend"}, headers=headers)
    # An agent references the pair -> deletion must 409 with the full shape.
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="worker-1")
        deps.repos.agents.set_tags(uow, agent_id="worker-1", tags={"team": ["backend"]})

    response = client.delete("/api/v1/tags/team", headers=headers)
    assert response.status_code == 409
    body = response.json()
    assert body["ok"] is False
    error = body["error"]
    assert error["code"] == "TAG_IN_USE"
    assert isinstance(error["message"], str) and error["message"]
    assert error["details"] == {
        "key": "team",
        "value": None,
        "total_uses": 1,
        "uses": [{"agent_id": "worker-1", "kind": "agent_tags"}],
    }

    value_response = client.delete("/api/v1/tags/team/values/backend", headers=headers)
    assert value_response.status_code == 409
    assert value_response.json()["error"]["details"]["value"] == "backend"


# --------------------------------------------------------------------------- #
# PATCH /agents/{id}: tags + comm_scope (fail-closed against the catalog)
# --------------------------------------------------------------------------- #
def _seed_catalog(client, headers, key, *values):
    assert (
        client.post("/api/v1/tags", json={"key": key}, headers=headers).status_code
        == 200
    )
    for value in values:
        assert (
            client.post(
                f"/api/v1/tags/{key}/values", json={"value": value}, headers=headers
            ).status_code
            == 200
        )


def test_patch_agent_tags_rejects_unregistered_pairs_fail_closed(http_env):
    _, client, headers = http_env
    client.post("/api/v1/agents", json={"agent_id": "worker-1"}, headers=headers)

    response = client.patch(
        "/api/v1/agents/worker-1",
        json={"tags": {"team": ["backend"]}},
        headers=headers,
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "unregistered" in error["message"]

    # Nothing persisted: the agent still has no tags.
    agent = client.get("/api/v1/agents/worker-1", headers=headers).json()["data"]
    assert agent["tags"] == {}


def test_patch_agent_tags_and_comm_scope_roundtrip_and_reset(http_env):
    _, client, headers = http_env
    _seed_catalog(client, headers, "team", "backend", "infra")
    client.post("/api/v1/agents", json={"agent_id": "worker-1"}, headers=headers)

    updated = client.patch(
        "/api/v1/agents/worker-1",
        json={
            "tags": {"team": ["backend"]},
            "comm_scope": {"outbound": {"team": ["backend", "infra"]}},
        },
        headers=headers,
    )
    assert updated.status_code == 200
    data = updated.json()["data"]
    assert data["tags"] == {"team": ["backend"]}
    assert data["comm_scope"] == {"outbound": {"team": ["backend", "infra"]}}

    # A PATCH that does not mention them leaves both untouched.
    untouched = client.patch(
        "/api/v1/agents/worker-1", json={"role": "dev"}, headers=headers
    ).json()["data"]
    assert untouched["tags"] == {"team": ["backend"]}
    assert untouched["comm_scope"] == {"outbound": {"team": ["backend", "infra"]}}

    # Explicit null resets to default-allow.
    reset = client.patch(
        "/api/v1/agents/worker-1",
        json={"tags": None, "comm_scope": None},
        headers=headers,
    ).json()["data"]
    assert reset["tags"] == {}
    assert reset["comm_scope"] is None


def test_patch_agent_comm_scope_selector_must_be_registered(http_env):
    _, client, headers = http_env
    _seed_catalog(client, headers, "team", "backend")
    client.post("/api/v1/agents", json={"agent_id": "worker-1"}, headers=headers)

    response = client.patch(
        "/api/v1/agents/worker-1",
        json={"comm_scope": {"outbound": {"team": ["ghost"]}}},
        headers=headers,
    )
    assert response.status_code == 422
    assert "comm_scope.outbound" in response.json()["error"]["message"]


def test_patch_agent_comm_scope_inbound_roundtrip_and_reset(http_env):
    _, client, headers = http_env
    _seed_catalog(client, headers, "team", "backend")
    _seed_catalog(client, headers, "sector", "ops")
    client.post("/api/v1/agents", json={"agent_id": "worker-1"}, headers=headers)

    updated = client.patch(
        "/api/v1/agents/worker-1",
        json={
            "comm_scope": {
                "outbound": {"team": ["backend"]},
                "inbound": {"sector": ["ops"]},
            }
        },
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["comm_scope"] == {
        "outbound": {"team": ["backend"]},
        "inbound": {"sector": ["ops"]},
    }

    # An inbound-only scope is legal (outbound side stays default-allow)...
    inbound_only = client.patch(
        "/api/v1/agents/worker-1",
        json={"comm_scope": {"inbound": {"sector": ["ops"]}}},
        headers=headers,
    ).json()["data"]
    assert inbound_only["comm_scope"] == {"inbound": {"sector": ["ops"]}}

    # ...and explicit null resets the whole scope to default-allow.
    reset = client.patch(
        "/api/v1/agents/worker-1", json={"comm_scope": None}, headers=headers
    ).json()["data"]
    assert reset["comm_scope"] is None


def test_patch_agent_comm_scope_inbound_selector_must_be_registered(http_env):
    _, client, headers = http_env
    _seed_catalog(client, headers, "sector", "ops")
    client.post("/api/v1/agents", json={"agent_id": "worker-1"}, headers=headers)

    response = client.patch(
        "/api/v1/agents/worker-1",
        json={"comm_scope": {"inbound": {"sector": ["ghost"]}}},
        headers=headers,
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    # The offending FIELD is named so the operator knows which leg to fix.
    assert "comm_scope.inbound" in error["message"]

    # Fail-closed: nothing persisted.
    agent = client.get("/api/v1/agents/worker-1", headers=headers).json()["data"]
    assert agent["comm_scope"] is None


def test_patch_agent_comm_scope_rejects_malformed_envelope(http_env):
    _, client, headers = http_env
    client.post("/api/v1/agents", json={"agent_id": "worker-1"}, headers=headers)
    response = client.patch(
        "/api/v1/agents/worker-1",
        json={"comm_scope": {"outbond": {"team": ["backend"]}}},  # typo
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_agent_comm_scope_rich_expressions_roundtrip(http_env):
    # F3: a direction may carry the rich matchExpressions form; it persists
    # in its canonical shape while a flat direction stays a flat map.
    _, client, headers = http_env
    _seed_catalog(client, headers, "team", "backend")
    _seed_catalog(client, headers, "sector", "ops")
    client.post("/api/v1/agents", json={"agent_id": "worker-1"}, headers=headers)

    updated = client.patch(
        "/api/v1/agents/worker-1",
        json={
            "comm_scope": {
                "outbound": [
                    {"key": "sector", "operator": "Exists"},
                    {"key": "sector", "operator": "NotIn", "values": ["ops"]},
                ],
                "inbound": {"team": ["backend"]},
            }
        },
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["comm_scope"] == {
        "outbound": [
            {"key": "sector", "operator": "Exists"},
            {"key": "sector", "operator": "NotIn", "values": ["ops"]},
        ],
        "inbound": {"team": ["backend"]},
    }


def test_patch_agent_comm_scope_rich_expressions_fail_closed(http_env):
    _, client, headers = http_env
    _seed_catalog(client, headers, "sector", "ops")
    client.post("/api/v1/agents", json={"agent_id": "worker-1"}, headers=headers)

    # Unregistered In/NotIn VALUE -> catalog gate names the offending leg.
    response = client.patch(
        "/api/v1/agents/worker-1",
        json={
            "comm_scope": {
                "outbound": [
                    {"key": "sector", "operator": "NotIn", "values": ["ghost"]}
                ]
            }
        },
        headers=headers,
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "comm_scope.outbound" in error["message"]

    # FORM violation: a presence operator carrying values is rejected.
    response = client.patch(
        "/api/v1/agents/worker-1",
        json={
            "comm_scope": {
                "outbound": [{"key": "sector", "operator": "Exists", "values": ["ops"]}]
            }
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    # Fail-closed: nothing persisted by either attempt.
    agent = client.get("/api/v1/agents/worker-1", headers=headers).json()["data"]
    assert agent["comm_scope"] is None


# --------------------------------------------------------------------------- #
# Discovery: tags are public, comm_scope NEVER leaves the identity slice
# --------------------------------------------------------------------------- #
def test_mcp_discovery_exposes_tags_but_never_comm_scope(migrated_factory):
    from okto_nexus.adapters.outbound.clock import SystemClock
    from okto_nexus.adapters.outbound.sqlite.identity_repo import (
        SqliteSessionRepo,
        SqliteWorkspaceRepo,
    )
    from okto_nexus.application.identity import IdentityService
    from okto_nexus.config import NexusConfig

    agents = SqliteAgentRepo()
    with migrated_factory.unit_of_work() as uow:
        agents.upsert(uow, agent_id="worker-1")
        agents.set_tags(uow, agent_id="worker-1", tags={"team": ["backend"]})
        agents.set_comm_scope(
            uow, agent_id="worker-1", comm_scope={"outbound": {"team": ["backend"]}}
        )

    service = IdentityService(
        connection_factory=migrated_factory,
        workspaces=SqliteWorkspaceRepo(),
        agents=agents,
        sessions=SqliteSessionRepo(),
        clock=SystemClock(),
        config=NexusConfig(home_dir=migrated_factory._config.home_dir),
    )
    for data in (service.agent_get(agent_id="worker-1"), *service.agent_list()):
        assert data["tags"] == {"team": ["backend"]}
        assert "comm_scope" not in data
