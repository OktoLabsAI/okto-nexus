"""Central capability catalog (migration 014): seed + gate + REST + surface.

Five layers, mirroring ``test_tag_catalog``:

* contract: the same registry scenarios run against BOTH CapabilityCatalogRepo
  implementations (in-memory fake + real SQLite over a migrated store) so
  fake-drift cannot silently weaken the fail-closed rule;
* seed: ``seed_capability_catalog`` absorbs every announced name idempotently
  (the "owned => registered" invariant), including at bootstrap on a store
  that predates the catalog;
* write-path gates: agent capability writes (service + REST POST/PATCH) and
  ``strategy: "capability"`` targets (message + handoff, incl. sub-rules in
  ``mixed`` and the ``direct_with_fallback`` fallback) fail closed on
  unregistered names, and historic targets never block deletion;
* REST ``/api/v1/capabilities`` incl. the normative 409 envelopes;
* discovery: ``capability_list`` is catalog-complete (descriptions,
  zero-owner names) and the MCP surface documents the rule at revision 16.
"""

from __future__ import annotations

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.adapters.inbound.mcp.tools.handoff import (
    build_service as build_handoff_service,
)
from okto_nexus.adapters.inbound.mcp.tools.identity import (
    build_service as build_identity_service,
)
from okto_nexus.adapters.inbound.mcp.tools.messages import (
    build_service as build_message_service,
)
from okto_nexus.adapters.outbound.sqlite.capability_catalog_repo import (
    SqliteCapabilityCatalogRepo,
)
from okto_nexus.adapters.outbound.sqlite.identity_repo import SqliteAgentRepo
from okto_nexus.application.capabilities import (
    CapabilityCatalogService,
    seed_capability_catalog,
)
from okto_nexus.application.ports import CapabilityCatalogRepo
from okto_nexus.domain.base import new_id
from okto_nexus.domain.ids import resolve_realpath, resolve_workspace_id
from okto_nexus.domain.models import Agent, CapabilityName
from okto_nexus.domain.targets import iter_target_capabilities, validate_target
from okto_nexus.errors import ErrorCode, OktoNexusError

from test_shared_md import FakeConnectionFactory


class FakeCapabilityCatalogRepo:
    """In-memory CapabilityCatalogRepo honouring the port contract."""

    def __init__(self) -> None:
        self.rows: dict[str, CapabilityName] = {}

    def create(self, uow, *, name, description=None):
        if name in self.rows:
            raise OktoNexusError(
                ErrorCode.VALIDATION_ERROR,
                f"Capability '{name}' is already registered.",
                {"name": name},
            )
        self.rows[name] = CapabilityName(
            name=name, description=description, created_at="t0"
        )
        return self.rows[name]

    def ensure(self, uow, *, name):
        if name in self.rows:
            return False
        self.rows[name] = CapabilityName(name=name, created_at="t0")
        return True

    def get(self, uow, name):
        return self.rows.get(name)

    def list(self, uow):
        return [self.rows[n] for n in sorted(self.rows)]

    def delete(self, uow, *, name):
        return self.rows.pop(name, None) is not None


class FakeAgentRepo:
    """Minimal agents port for the ownership scan (list only)."""

    def __init__(self) -> None:
        self.rows: dict[str, Agent] = {}

    def add(self, agent_id, *, capabilities=None, is_active=True) -> Agent:
        agent = Agent(
            agent_id=agent_id,
            created_at="t0",
            capabilities=capabilities or {},
            is_active=is_active,
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
        self.service = CapabilityCatalogService(catalog=catalog, agents=agents)


@pytest.fixture(params=["fake", "sqlite"])
def backend(request, migrated_factory) -> _Backend:
    if request.param == "fake":
        agents = FakeAgentRepo()

        def seed(agent_id, *, capabilities=None, is_active=True):
            agents.add(agent_id, capabilities=capabilities, is_active=is_active)

        return _Backend(
            "fake",
            FakeCapabilityCatalogRepo(),
            agents,
            FakeConnectionFactory().unit_of_work,
            seed,
        )
    agents = SqliteAgentRepo()

    def seed(agent_id, *, capabilities=None, is_active=True):
        with migrated_factory.unit_of_work() as uow:
            agents.upsert(uow, agent_id=agent_id, capabilities=capabilities)
            if not is_active:
                agents.set_active(uow, agent_id=agent_id, is_active=False)

    return _Backend(
        "sqlite",
        SqliteCapabilityCatalogRepo(),
        agents,
        migrated_factory.unit_of_work,
        seed,
    )


def _register(backend: _Backend, *names: str) -> None:
    with backend.uow() as uow:
        for name in names:
            backend.service.register(uow, name=name)


# --------------------------------------------------------------------------- #
# Contract: registry CRUD on both implementations
# --------------------------------------------------------------------------- #
def test_contract_adapter_satisfies_protocol(backend):
    assert isinstance(backend.catalog, CapabilityCatalogRepo)


def test_contract_register_and_snapshot(backend):
    with backend.uow() as uow:
        backend.service.register(uow, name="ocr", description="Reads scans")
        backend.service.register(uow, name="dispatch")
        snapshot = backend.service.snapshot(uow)
    assert [entry["name"] for entry in snapshot] == ["dispatch", "ocr"]
    ocr = next(e for e in snapshot if e["name"] == "ocr")
    assert ocr["description"] == "Reads scans"
    assert ocr["created_at"]


def test_contract_duplicate_and_blank_names_are_validation_errors(backend):
    _register(backend, "ocr")
    with backend.uow() as uow:
        with pytest.raises(OktoNexusError) as ei:
            backend.service.register(uow, name="ocr")
        assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
        assert "already registered" in ei.value.message
        with pytest.raises(OktoNexusError) as ei:
            backend.service.register(uow, name="   ")
        assert ei.value.code == ErrorCode.VALIDATION_ERROR.value


def test_contract_delete_unknown_name_is_not_found(backend):
    with backend.uow() as uow:
        with pytest.raises(OktoNexusError) as ei:
            backend.service.delete(uow, name="ghost")
    assert ei.value.code == ErrorCode.NOT_FOUND.value


def test_contract_deleting_unowned_name_succeeds(backend):
    _register(backend, "ocr")
    with backend.uow() as uow:
        assert backend.service.delete(uow, name="ocr") == {
            "name": "ocr",
            "deleted": True,
        }
        assert backend.catalog.list(uow) == []


# --------------------------------------------------------------------------- #
# CAPABILITY_IN_USE: the normative payload shape, byte-exact structure
# --------------------------------------------------------------------------- #
def test_delete_owned_name_raises_capability_in_use(backend):
    _register(backend, "ocr")
    backend.seed_agent("worker-1", capabilities={"ocr": True})
    with backend.uow() as uow:
        with pytest.raises(OktoNexusError) as ei:
            backend.service.delete(uow, name="ocr")
    err = ei.value
    assert err.code == ErrorCode.CAPABILITY_IN_USE.value
    assert err.details == {
        "capability": "ocr",
        "total_uses": 1,
        "uses": [{"agent_id": "worker-1", "kind": "capabilities"}],
    }
    # Nothing was deleted.
    with backend.uow() as uow:
        assert backend.catalog.get(uow, "ocr") is not None


def test_inactive_owners_still_block_deletion(backend):
    # An inactive agent can reactivate: its announcement must stay valid.
    _register(backend, "ocr")
    backend.seed_agent("parked", capabilities=["ocr"], is_active=False)
    backend.seed_agent("busy", capabilities=["ocr", "pdf"])
    with backend.uow() as uow:
        with pytest.raises(OktoNexusError) as ei:
            backend.service.delete(uow, name="ocr")
    assert ei.value.details["total_uses"] == 2
    assert [u["agent_id"] for u in ei.value.details["uses"]] == ["busy", "parked"]


def test_falsey_flag_is_not_ownership(backend):
    # {"ocr": false} normalises to "not possessed" (routing-consistent), so
    # it never blocks deletion.
    _register(backend, "ocr")
    backend.seed_agent("worker-1", capabilities={"ocr": False})
    with backend.uow() as uow:
        assert backend.service.delete(uow, name="ocr")["deleted"] is True


# --------------------------------------------------------------------------- #
# ensure_registered: the fail-closed existence gate
# --------------------------------------------------------------------------- #
def test_ensure_registered_passes_for_registered_names(backend):
    _register(backend, "ocr", "pdf")
    with backend.uow() as uow:
        backend.service.ensure_registered(
            uow, ["ocr", "pdf"], field="capabilities"
        )  # no raise
        backend.service.ensure_registered(uow, [], field="capabilities")  # no-op


def test_ensure_registered_lists_every_unknown_name_sorted(backend):
    _register(backend, "ocr")
    with backend.uow() as uow:
        with pytest.raises(OktoNexusError) as ei:
            backend.service.ensure_registered(
                uow, ["zeta", "ocr", "alpha", "zeta"], field="capabilities"
            )
    err = ei.value
    assert err.code == ErrorCode.VALIDATION_ERROR.value
    assert err.details == {
        "field": "capabilities",
        "unregistered": ["alpha", "zeta"],
    }
    assert "references unregistered capability(ies): alpha, zeta" in err.message


# --------------------------------------------------------------------------- #
# Seed: idempotent absorption of every announced name
# --------------------------------------------------------------------------- #
def test_seed_absorbs_announced_names_and_is_idempotent(backend):
    backend.seed_agent("a", capabilities={"py": True, "js": False})
    backend.seed_agent("b", capabilities=["py", "ocr"])
    backend.seed_agent("parked", capabilities=["scan"], is_active=False)
    with backend.uow() as uow:
        inserted = seed_capability_catalog(
            uow, catalog=backend.catalog, agents=backend.agents
        )
        assert inserted == 3  # py, ocr, scan - js is a falsey flag
        assert [row.name for row in backend.catalog.list(uow)] == [
            "ocr",
            "py",
            "scan",
        ]
        # Second pass: nothing new, nothing overwritten.
        assert (
            seed_capability_catalog(uow, catalog=backend.catalog, agents=backend.agents)
            == 0
        )


def test_seed_never_overwrites_operator_descriptions(backend):
    _register_with_description(backend, "ocr", "Reads scans")
    backend.seed_agent("a", capabilities=["ocr"])
    with backend.uow() as uow:
        seed_capability_catalog(uow, catalog=backend.catalog, agents=backend.agents)
        assert backend.catalog.get(uow, "ocr").description == "Reads scans"


def _register_with_description(backend: _Backend, name: str, description: str):
    with backend.uow() as uow:
        backend.service.register(uow, name=name, description=description)


# --------------------------------------------------------------------------- #
# End to end over the real wiring (bootstrap deps)
# --------------------------------------------------------------------------- #
@pytest.fixture
def deps(tmp_path):
    return bootstrap({}, ["--home", str(tmp_path / "home")])


def _catalog(deps, *names: str) -> None:
    with deps.connection_factory.unit_of_work() as uow:
        for name in names:
            deps.repos.capability_catalog.create(uow, name=name)


def _upsert_agent(deps, agent_id: str, *, capabilities=None) -> None:
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id=agent_id, capabilities=capabilities)


def _open_session(deps, agent_id: str, project_root: str) -> None:
    ws = resolve_workspace_id(project_root)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(
            uow,
            workspace_id=ws,
            root_realpath=resolve_realpath(project_root),
            last_seen_at=deps.clock.now_iso(),
        )
        deps.repos.sessions.create(
            uow,
            session_id=new_id("ses"),
            agent_id=agent_id,
            workspace_id=ws,
            status="active",
        )


def test_bootstrap_seeds_a_store_that_predates_the_catalog(tmp_path):
    home = tmp_path / "home"
    deps = bootstrap({}, ["--home", str(home)])
    # An agent announced "legacy" without the catalog knowing (old build).
    _upsert_agent(deps, "old-timer", capabilities={"legacy": True})

    rebooted = bootstrap({}, ["--home", str(home)])
    with rebooted.connection_factory.unit_of_work() as uow:
        assert rebooted.repos.capability_catalog.get(uow, "legacy") is not None
    # The invariant holds: re-announcing the same capabilities passes the gate.
    service = build_identity_service(rebooted)
    out = service.agent_register(agent_id="old-timer", capabilities=["legacy"])
    assert out["agent_id"] == "old-timer"


def test_agent_register_fails_closed_and_persists_nothing(deps):
    service = build_identity_service(deps)
    with pytest.raises(OktoNexusError) as ei:
        service.agent_register(agent_id="fresh", capabilities=["ghost", "ocr"])
    err = ei.value
    assert err.code == ErrorCode.VALIDATION_ERROR.value
    assert err.details == {
        "field": "capabilities",
        "unregistered": ["ghost", "ocr"],
    }
    # Nothing persisted by the rejected register; only the bootstrap-seeded
    # "operator" identity exists (spec 2948b2a2 FR6).
    assert [a["agent_id"] for a in service.agent_list()] == ["operator"]

    _catalog(deps, "ghost", "ocr")
    out = service.agent_register(agent_id="fresh", capabilities=["ghost", "ocr"])
    assert out["agent_id"] == "fresh"


def test_agent_register_without_capabilities_never_hits_the_gate(deps):
    service = build_identity_service(deps)
    assert service.agent_register(agent_id="plain")["agent_id"] == "plain"


def test_message_capability_target_fails_closed(deps, tmp_path):
    service = build_message_service(deps)
    _upsert_agent(deps, "sender")
    with pytest.raises(OktoNexusError) as ei:
        service.create_message(
            project_root=str(tmp_path),
            from_agent_id="sender",
            subject="s",
            body="b",
            target={"strategy": "capability", "capability": "ghost"},
        )
    err = ei.value
    assert err.code == ErrorCode.VALIDATION_ERROR.value
    assert err.details == {"field": "target.capability", "unregistered": ["ghost"]}


def test_message_mixed_subrule_capability_fails_closed(deps, tmp_path):
    service = build_message_service(deps)
    _catalog(deps, "ocr")
    _upsert_agent(deps, "sender")
    with pytest.raises(OktoNexusError) as ei:
        service.create_message(
            project_root=str(tmp_path),
            from_agent_id="sender",
            subject="s",
            body="b",
            target={
                "strategy": "mixed",
                "rules": [
                    {"strategy": "capability", "capability": ["ocr", "ghost"]},
                    {"strategy": "role", "role": "validator"},
                ],
            },
        )
    assert ei.value.details == {
        "field": "target.capability",
        "unregistered": ["ghost"],
    }


def test_message_registered_capability_target_delivers(deps, tmp_path):
    service = build_message_service(deps)
    root = str(tmp_path)
    _catalog(deps, "ocr")
    _upsert_agent(deps, "sender")
    _upsert_agent(deps, "worker", capabilities={"ocr": True})
    _open_session(deps, "worker", root)

    out = service.create_message(
        project_root=root,
        from_agent_id="sender",
        subject="s",
        body="b",
        target={"strategy": "capability", "capability": "ocr"},
    )
    assert out["recipients"] == ["worker"]


def test_handoff_fallback_capability_fails_closed(deps, tmp_path):
    service = build_handoff_service(deps)
    _upsert_agent(deps, "creator")
    _upsert_agent(deps, "named")
    with pytest.raises(OktoNexusError) as ei:
        service.handoff_create(
            project_root=str(tmp_path),
            from_agent_id="creator",
            visibility="public",
            target={
                "strategy": "direct_with_fallback",
                "agent_id": "named",
                "fallback_after_seconds": 60,
                "fallback": {"strategy": "capability", "capability": "ghost"},
            },
        )
    assert ei.value.code == ErrorCode.VALIDATION_ERROR.value
    assert ei.value.details == {
        "field": "target.capability",
        "unregistered": ["ghost"],
    }


def test_historic_targets_never_block_deletion(deps, tmp_path):
    # A capability referenced only by an ALREADY-SENT message deletes fine:
    # targets are ephemeral (resolved at send time); only ownership counts.
    messages = build_message_service(deps)
    root = str(tmp_path)
    _catalog(deps, "ephemeral")
    _upsert_agent(deps, "sender")
    _upsert_agent(deps, "worker", capabilities={"ephemeral": True})
    _open_session(deps, "worker", root)
    messages.create_message(
        project_root=root,
        from_agent_id="sender",
        subject="s",
        body="b",
        target={"strategy": "capability", "capability": "ephemeral"},
    )
    # The owner renounces the capability; the historic target stays behind.
    _upsert_agent(deps, "worker", capabilities={})

    service = CapabilityCatalogService(
        catalog=deps.repos.capability_catalog, agents=deps.repos.agents
    )
    with deps.connection_factory.unit_of_work() as uow:
        assert service.delete(uow, name="ephemeral")["deleted"] is True


# --------------------------------------------------------------------------- #
# Grammar helper: iter_target_capabilities walks the whole tree
# --------------------------------------------------------------------------- #
def test_iter_target_capabilities_covers_every_shape():
    def names(target):
        return sorted(iter_target_capabilities(validate_target(target)))

    assert names({"strategy": "capability", "capability": "ocr"}) == ["ocr"]
    assert names({"strategy": "capability", "capability": ["ocr", "pdf"]}) == [
        "ocr",
        "pdf",
    ]
    assert names(
        {
            "strategy": "mixed",
            "rules": [
                {"strategy": "capability", "capability": "ocr"},
                {"strategy": "role", "role": "validator"},
            ],
        }
    ) == ["ocr"]
    assert names(
        {
            "strategy": "direct_with_fallback",
            "agent_id": "a",
            "fallback_after_seconds": 60,
            "fallback": {"strategy": "capability", "capability": "scan"},
        }
    ) == ["scan"]
    assert names({"strategy": "direct", "agent_id": "a"}) == []


# --------------------------------------------------------------------------- #
# REST: /api/v1/capabilities + the agent write gates
# --------------------------------------------------------------------------- #
@pytest.fixture
def http_env(tmp_path):
    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key
    from okto_nexus.application.auth import AgentKeyAuthService

    deps = bootstrap({}, ["--home", str(tmp_path / "nexus_home")])
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    issued = ensure_operator_key(deps, auth)
    assert issued is not None
    _, operator_key = issued
    app = build_app(deps)
    with TestClient(app) as client:
        yield deps, client, {"x-api-key": operator_key}


def test_rest_capabilities_crud_roundtrip(http_env):
    _, client, headers = http_env

    created = client.post(
        "/api/v1/capabilities",
        json={"name": "ocr", "description": "Reads scans"},
        headers=headers,
    )
    assert created.status_code == 200
    data = created.json()["data"]
    assert data["name"] == "ocr" and data["description"] == "Reads scans"
    assert data["created_at"]

    assert (
        client.post(
            "/api/v1/capabilities", json={"name": "dispatch"}, headers=headers
        ).status_code
        == 200
    )
    listing = client.get("/api/v1/capabilities", headers=headers).json()["data"]
    assert [item["name"] for item in listing["items"]] == ["dispatch", "ocr"]

    # Duplicates surface as 409 CONFLICT (registry is idempotent-hostile).
    assert (
        client.post(
            "/api/v1/capabilities", json={"name": "ocr"}, headers=headers
        ).status_code
        == 409
    )

    gone = client.delete("/api/v1/capabilities/ocr", headers=headers)
    assert gone.status_code == 200 and gone.json()["data"]["deleted"] is True
    assert client.delete("/api/v1/capabilities/ocr", headers=headers).status_code == 404


def test_rest_delete_owned_returns_409_with_the_normative_envelope(http_env):
    deps, client, headers = http_env
    client.post("/api/v1/capabilities", json={"name": "ocr"}, headers=headers)
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id="worker-1", capabilities={"ocr": True})

    response = client.delete("/api/v1/capabilities/ocr", headers=headers)
    assert response.status_code == 409
    body = response.json()
    assert body["ok"] is False
    error = body["error"]
    assert error["code"] == "CAPABILITY_IN_USE"
    assert isinstance(error["message"], str) and error["message"]
    assert error["details"] == {
        "capability": "ocr",
        "total_uses": 1,
        "uses": [{"agent_id": "worker-1", "kind": "capabilities"}],
    }
    # Nothing was deleted.
    listing = client.get("/api/v1/capabilities", headers=headers).json()["data"]
    assert [item["name"] for item in listing["items"]] == ["ocr"]


def test_rest_agent_writes_fail_closed_with_422(http_env):
    _, client, headers = http_env

    created = client.post(
        "/api/v1/agents",
        json={"agent_id": "fresh", "capabilities": ["ghost"]},
        headers=headers,
    )
    assert created.status_code == 422
    error = created.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "ghost" in error["message"]
    # The write never happened - not even the agent row.
    assert client.get("/api/v1/agents/fresh", headers=headers).status_code == 404

    # Registering the name unblocks the same payload.
    client.post("/api/v1/capabilities", json={"name": "ghost"}, headers=headers)
    assert (
        client.post(
            "/api/v1/agents",
            json={"agent_id": "fresh", "capabilities": ["ghost"]},
            headers=headers,
        ).status_code
        == 200
    )

    # PATCH runs the same gate.
    patched = client.patch(
        "/api/v1/agents/fresh",
        json={"capabilities": ["phantom"]},
        headers=headers,
    )
    assert patched.status_code == 422
    assert "phantom" in patched.json()["error"]["message"]
    detail = client.get("/api/v1/agents/fresh", headers=headers).json()["data"]
    assert detail["capabilities"] == {"ghost": True}


# --------------------------------------------------------------------------- #
# Discovery: capability_list is catalog-complete
# --------------------------------------------------------------------------- #
def test_capability_list_merges_catalog_and_owners(deps):
    service = build_identity_service(deps)
    _catalog(deps, "ocr")
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.capability_catalog.create(
            uow, name="vision", description="Image understanding"
        )
    _upsert_agent(deps, "a", capabilities={"ocr": True})
    # Defensive union: a name persisted OUTSIDE the catalog still lists.
    _upsert_agent(deps, "b", capabilities={"rogue": True})

    entries = {e["capability"]: e for e in service.capability_list()}
    assert sorted(entries) == ["ocr", "rogue", "vision"]
    assert entries["ocr"] == {
        "capability": "ocr",
        "description": None,
        "agent_count": 1,
        "agents": ["a"],
    }
    # Zero-owner names surface the sanctioned vocabulary with agent_count 0.
    assert entries["vision"] == {
        "capability": "vision",
        "description": "Image understanding",
        "agent_count": 0,
        "agents": [],
    }
    assert entries["rogue"]["description"] is None


# --------------------------------------------------------------------------- #
# Surface: revision 16 + the rule is documented where agents read
# --------------------------------------------------------------------------- #
def test_surface_revision_16_and_docs_teach_the_fail_closed_rule():
    from okto_nexus.adapters.inbound.mcp import resources
    from okto_nexus.adapters.inbound.mcp.server import SURFACE_REVISION
    from okto_nexus.adapters.inbound.mcp.tools.identity import _P_CAPABILITIES

    assert SURFACE_REVISION >= 16
    assert ErrorCode.CAPABILITY_IN_USE.value == "CAPABILITY_IN_USE"

    # The inline parameter cheat-sheet warns at the point of use.
    assert "FAIL-CLOSED" in _P_CAPABILITIES

    identity_docs = resources._RESOURCES["okto-nexus://reference/tool-docs/identity"][
        "body"
    ]
    assert "FAIL-CLOSED" in identity_docs
    assert "capability catalog" in identity_docs

    grammar = resources._RESOURCES["okto-nexus://reference/target-grammar"]["body"]
    assert "capability catalog" in grammar
