"""Tests for communication presets (spec 6f961722).

Covers the 4th per-agent axis end to end: the pure domain core (closed content
dimensions, single-source binding, latest/pinned resolution), the catalog
service (CRUD + append-only versions + the in-use delete guard + the
single-source binding), the REST surface (operator-gated), the SELF-ONLY whoami
block (present only when bound, never on discovery), and the idempotent built-in
seed. Harness mirrors test_governance.py (real bootstrap + tool registry) and
test_policy_catalog.py (TestClient over the migrated home).
"""

from __future__ import annotations

import asyncio
import functools
import inspect

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap, register_tools
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.application.comm_preset_catalog import (
    BUILTIN_COMM_PRESETS,
    CommPresetCatalogService,
    seed_comm_presets,
)
from okto_nexus.domain import comm_preset as cp
from okto_nexus.errors import ErrorCode, OktoNexusError


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #
class FakeServer:
    """Captures FastMCP-style ``@server.tool()`` registrations by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            if inspect.iscoroutinefunction(fn):

                @functools.wraps(fn)
                def _sync(*a, **k):
                    return asyncio.run(fn(*a, **k))

                self.tools[fn.__name__] = _sync
            else:
                self.tools[fn.__name__] = fn
            return fn

        return deco


def _ok(env: dict) -> dict:
    assert env["ok"] is True, f"expected ok envelope, got: {env}"
    return env["data"]


def make_env(tmp_path):
    """Real bootstrap in a temp home + two registered agents + a workspace."""
    deps = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
    server = FakeServer()
    register_tools(server, deps)
    tools = server.tools
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    root = str(project)
    _ok(tools["workspace_resolve"](project_root=root))
    _ok(tools["agent_register"](agent_id="alpha", role="builder"))
    _ok(tools["agent_register"](agent_id="beta", role="reviewer"))
    return deps, tools, root


def _service(deps) -> CommPresetCatalogService:
    return CommPresetCatalogService(
        connection_factory=deps.connection_factory,
        presets=deps.repos.comm_presets,
        comm_bindings=deps.repos.comm_bindings,
        agents=deps.repos.agents,
    )


@pytest.fixture()
def rest_client(tmp_path):
    from fastapi.testclient import TestClient

    from okto_nexus.adapters.inbound.http.app import build_app, ensure_operator_key

    deps = bootstrap({"OKTO_NEXUS_HOME": str(tmp_path / "home")}, [])
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    _, operator_key = ensure_operator_key(deps, auth)
    app = build_app(deps)
    with TestClient(app) as client:
        client.headers.update({"x-api-key": operator_key})
        yield client, deps


def _issue_key(deps, agent_id: str) -> str:
    auth = AgentKeyAuthService(deps.repos.agents, deps.clock)
    with deps.connection_factory.unit_of_work() as uow:
        return auth.issue_key(uow, agent_id=agent_id)


# ==========================================================================  #
# T-A: domain content + binding form (fail-closed, closed dimensions)
# ==========================================================================  #
def test_content_unknown_dimension_is_rejected_fail_closed():
    with pytest.raises(OktoNexusError) as exc:
        cp.validate_content_form({"tone": "concise", "mood": "happy"})
    assert exc.value.code == ErrorCode.VALIDATION_ERROR
    assert "mood" in exc.value.details["unknown"]


def test_content_empty_is_valid_and_whitespace_dropped():
    assert cp.validate_content_form({}) == {}
    assert cp.validate_content_form(None) == {}
    # a whitespace-only value is dropped, never surfaced
    assert cp.validate_content_form({"tone": "   ", "format": "markdown"}) == {
        "format": "markdown"
    }


def test_content_is_returned_in_canonical_order_and_trimmed():
    out = cp.validate_content_form(
        {"additional_instructions": " be terse ", "tone": "formal", "language": "en"}
    )
    assert list(out.keys()) == ["tone", "language", "additional_instructions"]
    assert out["additional_instructions"] == "be terse"


def test_content_rejects_non_string_and_over_long_values():
    with pytest.raises(OktoNexusError):
        cp.validate_content_form({"tone": 5})
    with pytest.raises(OktoNexusError):
        cp.validate_content_form({"tone": "x" * 501})
    # additional_instructions gets the larger note budget
    assert cp.validate_content_form({"additional_instructions": "y" * 600})
    with pytest.raises(OktoNexusError):
        cp.validate_content_form({"additional_instructions": "y" * 4001})


def test_binding_form_inline_and_global_grammar():
    assert cp.validate_comm_binding_form(
        {"source": "inline", "content": {"tone": "warm"}}
    ) == {"source": "inline", "content": {"tone": "warm"}}
    assert cp.validate_comm_binding_form(
        {"source": "global", "preset_id": "cpr_x", "mode": "latest"}
    ) == {"source": "global", "preset_id": "cpr_x", "mode": "latest"}
    pinned = cp.validate_comm_binding_form(
        {
            "source": "global",
            "preset_id": "cpr_x",
            "mode": "pinned",
            "pinned_version": 3,
        }
    )
    assert pinned["pinned_version"] == 3


@pytest.mark.parametrize(
    "binding",
    [
        {"source": "nope"},
        {"source": "global", "mode": "latest"},  # no preset_id
        {"source": "global", "preset_id": "cpr_x", "mode": "bogus"},
        {"source": "global", "preset_id": "cpr_x", "mode": "pinned"},  # no pin
        {
            "source": "global",
            "preset_id": "cpr_x",
            "mode": "pinned",
            "pinned_version": 0,
        },
        {
            "source": "global",
            "preset_id": "cpr_x",
            "mode": "latest",
            "pinned_version": 2,
        },
        {"source": "inline", "content": {"nope": "x"}},
        {"source": "inline", "junk": 1},  # unknown field
    ],
)
def test_binding_form_rejects_malformed(binding):
    with pytest.raises(OktoNexusError):
        cp.validate_comm_binding_form(binding)


def test_compose_is_single_source_xor():
    assert cp.compose_comm_binding() is None
    assert cp.compose_comm_binding(inline={"tone": "x"})["source"] == "inline"
    assert (
        cp.compose_comm_binding(global_ref={"preset_id": "cpr_x", "mode": "latest"})[
            "source"
        ]
        == "global"
    )
    with pytest.raises(OktoNexusError):
        cp.compose_comm_binding(
            inline={"tone": "x"}, global_ref={"preset_id": "cpr_x", "mode": "latest"}
        )


# ==========================================================================  #
# T-B: domain resolution -> the whoami block (BR11 shape)
# ==========================================================================  #
def _ver(pid, n, content):
    return cp.CommPresetVersion(
        preset_id=pid, version=n, content=content, published_at=f"t{n}"
    )


def test_resolve_inline_always_surfaces_even_when_empty():
    b = cp.compose_comm_binding(inline={"tone": "concise"})
    assert cp.resolve_communication(b, {}) == {
        "source": "inline",
        "content": {"tone": "concise"},
    }
    empty = cp.compose_comm_binding(inline={})
    assert cp.resolve_communication(empty, {}) == {"source": "inline", "content": {}}


def test_resolve_global_latest_and_pinned():
    vs = [_ver("cpr_1", 1, {"tone": "a"}), _ver("cpr_1", 2, {"tone": "b"})]
    latest = cp.compose_comm_binding(
        global_ref={"preset_id": "cpr_1", "mode": "latest"}
    )
    assert cp.resolve_communication(latest, {"cpr_1": vs}) == {
        "source": "cpr_1@2",
        "content": {"tone": "b"},
    }
    pinned = cp.compose_comm_binding(
        global_ref={"preset_id": "cpr_1", "mode": "pinned", "pinned_version": 1}
    )
    assert cp.resolve_communication(pinned, {"cpr_1": vs}) == {
        "source": "cpr_1@1",
        "content": {"tone": "a"},
    }


def test_resolve_unresolvable_or_absent_is_none():
    latest = cp.compose_comm_binding(
        global_ref={"preset_id": "cpr_1", "mode": "latest"}
    )
    assert cp.resolve_communication(latest, {"cpr_1": []}) is None  # no versions
    pinned = cp.compose_comm_binding(
        global_ref={"preset_id": "cpr_1", "mode": "pinned", "pinned_version": 9}
    )
    assert cp.resolve_communication(pinned, {"cpr_1": [_ver("cpr_1", 1, {})]}) is None
    assert cp.resolve_communication(None, {}) is None


# ==========================================================================  #
# T-C: catalog service (CRUD, append-only versions, delete guard, binding)
# ==========================================================================  #
def test_service_crud_versions_and_duplicate_name(tmp_path):
    deps, _tools, _root = make_env(tmp_path)
    svc = _service(deps)
    seeded = {p["name"] for p in svc.list()}
    p = svc.create(name="MyStyle", description="note")
    pid = p["preset_id"]
    assert p["latest_version"] == 0 and p["versions"] == []
    v1 = svc.publish_version(preset_id=pid, content={"tone": "concise"})
    v2 = svc.publish_version(preset_id=pid, content={"tone": "formal"})
    assert (v1["version"], v2["version"]) == (1, 2)  # append-only MAX+1
    got = svc.get(preset_id=pid)
    assert got["latest_version"] == 2 and len(got["versions"]) == 2
    # duplicate name is rejected (against a seeded name too)
    with pytest.raises(OktoNexusError) as exc:
        svc.create(name=next(iter(seeded)))
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_service_delete_guard_and_single_source_binding(tmp_path):
    deps, _tools, _root = make_env(tmp_path)
    svc = _service(deps)
    pid = svc.create(name="Bound")["preset_id"]
    svc.publish_version(preset_id=pid, content={"tone": "concise"})
    # bind alpha -> latest
    r = svc.set_agent_binding(
        agent_id="alpha", global_={"preset_id": pid, "mode": "latest"}
    )
    assert r["communication"]["source"] == f"{pid}@1"
    # in use -> guarded
    with pytest.raises(OktoNexusError) as exc:
        svc.delete(preset_id=pid)
    assert exc.value.code == ErrorCode.COMM_PRESET_IN_USE
    assert exc.value.details["agents"] == ["alpha"]
    # switching alpha to inline frees the preset; a single binding replaces the old
    inline = svc.set_agent_binding(agent_id="alpha", inline={"tone": "warm"})
    assert inline["communication"] == {"source": "inline", "content": {"tone": "warm"}}
    assert svc.delete(preset_id=pid)["deleted"] is True


def test_service_binding_existence_checks(tmp_path):
    deps, _tools, _root = make_env(tmp_path)
    svc = _service(deps)
    with pytest.raises(OktoNexusError) as unknown_agent:
        svc.set_agent_binding(agent_id="ghost", inline={"tone": "x"})
    assert unknown_agent.value.code == ErrorCode.NOT_FOUND
    with pytest.raises(OktoNexusError) as unknown_preset:
        svc.set_agent_binding(
            agent_id="alpha", global_={"preset_id": "cpr_none", "mode": "latest"}
        )
    assert unknown_preset.value.code == ErrorCode.NOT_FOUND
    pid = svc.create(name="P")["preset_id"]  # exists but no versions yet
    with pytest.raises(OktoNexusError) as missing_pin:
        svc.set_agent_binding(
            agent_id="alpha",
            global_={"preset_id": pid, "mode": "pinned", "pinned_version": 5},
        )
    assert missing_pin.value.code == ErrorCode.VALIDATION_ERROR


def test_service_get_binding_editor_shape_and_clear(tmp_path):
    deps, _tools, _root = make_env(tmp_path)
    svc = _service(deps)
    # no binding
    empty = svc.get_agent_binding(agent_id="alpha")
    assert empty == {
        "agent_id": "alpha",
        "inline": None,
        "global": None,
        "communication": None,
    }
    pid = svc.create(name="P")["preset_id"]
    svc.publish_version(preset_id=pid, content={"tone": "concise"})
    svc.set_agent_binding(
        agent_id="alpha",
        global_={"preset_id": pid, "mode": "pinned", "pinned_version": 1},
    )
    shaped = svc.get_agent_binding(agent_id="alpha")
    assert shaped["global"] == {"preset_id": pid, "mode": "pinned", "pinned_version": 1}
    assert shaped["inline"] is None
    # clear (no side)
    svc.set_agent_binding(agent_id="alpha")
    assert svc.resolve_communication("alpha") is None


# ==========================================================================  #
# T-D: REST surface (operator-gated) + error mapping
# ==========================================================================  #
def test_rest_lifecycle_and_binding(rest_client):
    client, _deps = rest_client
    B = "/api/v1"
    created = client.post(f"{B}/comm-presets", json={"name": "RestStyle"})
    assert created.status_code == 200
    pid = created.json()["data"]["preset_id"]
    assert (
        client.post(
            f"{B}/comm-presets/{pid}/versions", json={"content": {"tone": "concise"}}
        ).json()["data"]["version"]
        == 1
    )
    client.post(f"{B}/agents", json={"agent_id": "alpha", "role": "builder"})
    bound = client.put(
        f"{B}/agents/alpha/communication",
        json={"global": {"preset_id": pid, "mode": "latest"}},
    )
    assert bound.json()["data"]["communication"]["source"] == f"{pid}@1"
    # in-use delete -> 409 with the binder list
    blocked = client.delete(f"{B}/comm-presets/{pid}")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["details"]["agents"] == ["alpha"]


def test_rest_validation_and_operator_gate(rest_client):
    client, deps = rest_client
    B = "/api/v1"
    # unknown header field -> 422
    assert (
        client.post(f"{B}/comm-presets", json={"name": "x", "color": "red"}).status_code
        == 422
    )
    pid = client.post(f"{B}/comm-presets", json={"name": "V"}).json()["data"][
        "preset_id"
    ]
    # unknown content dimension -> 422
    bad = client.post(
        f"{B}/comm-presets/{pid}/versions", json={"content": {"nope": "x"}}
    )
    assert bad.status_code == 422
    # inline XOR global both -> 422
    client.post(f"{B}/agents", json={"agent_id": "alpha"})
    both = client.put(
        f"{B}/agents/alpha/communication",
        json={"inline": {"tone": "x"}, "global": {"preset_id": pid, "mode": "latest"}},
    )
    assert both.status_code == 422
    # non-operator key -> 403 on a mutating route (D5)
    key = _issue_key(deps, "alpha")
    denied = client.post(
        f"{B}/comm-presets", json={"name": "Nope"}, headers={"x-api-key": key}
    )
    assert denied.status_code == 403


# ==========================================================================  #
# T-E: whoami self-only block (present when bound, absent otherwise, never
# on discovery) - BR11 / D-CP-4
# ==========================================================================  #
def test_whoami_communication_block_gated_and_self_only(tmp_path):
    from okto_nexus.adapters.inbound.http.identity_ctx import current_agent

    deps, tools, _root = make_env(tmp_path)
    svc = _service(deps)
    pid = svc.create(name="Whoami")["preset_id"]
    svc.publish_version(preset_id=pid, content={"tone": "concise", "verbosity": "low"})

    with deps.connection_factory.unit_of_work(write=False) as uow:
        alpha = deps.repos.agents.get(uow, "alpha")
        beta = deps.repos.agents.get(uow, "beta")

    token = current_agent.set(alpha)
    try:
        # no binding -> block ABSENT (byte-identical to the pre-feature whoami)
        assert "communication" not in _ok(tools["agent_whoami"]())
        svc.set_agent_binding(
            agent_id="alpha", global_={"preset_id": pid, "mode": "latest"}
        )
        view = _ok(tools["agent_whoami"]())
        assert view["communication"] == {
            "source": f"{pid}@1",
            "content": {"tone": "concise", "verbosity": "low"},
        }
        # discovery NEVER carries the block (D-CP-4): neither agent_get nor agent_list
        got = _ok(tools["agent_get"](agent_id="alpha"))
        assert "communication" not in got
        listed = _ok(tools["agent_list"]())["agents"]
        assert all("communication" not in a for a in listed)
    finally:
        current_agent.reset(token)

    # beta holds no binding -> no block
    token = current_agent.set(beta)
    try:
        assert "communication" not in _ok(tools["agent_whoami"]())
    finally:
        current_agent.reset(token)


def test_whoami_omits_block_when_global_unresolvable(tmp_path):
    from okto_nexus.adapters.inbound.http.identity_ctx import current_agent

    deps, tools, _root = make_env(tmp_path)
    svc = _service(deps)
    # a preset with NO published version, bound latest -> nothing resolves
    pid = svc.create(name="Empty")["preset_id"]
    svc.set_agent_binding(
        agent_id="alpha", global_={"preset_id": pid, "mode": "latest"}
    )
    with deps.connection_factory.unit_of_work(write=False) as uow:
        alpha = deps.repos.agents.get(uow, "alpha")
    token = current_agent.set(alpha)
    try:
        assert "communication" not in _ok(tools["agent_whoami"]())
    finally:
        current_agent.reset(token)


# ==========================================================================  #
# T-F: built-in seed (idempotent) + surface revision
# ==========================================================================  #
def test_builtin_presets_seeded_and_idempotent(tmp_path):
    deps, _tools, _root = make_env(tmp_path)
    svc = _service(deps)
    names = {p["name"] for p in svc.list()}
    assert names == {name for name, _desc, _content in BUILTIN_COMM_PRESETS}
    # each built-in has exactly one published version
    for p in svc.list():
        assert p["latest_version"] == 1
    # re-seeding is a no-op (create-if-missing): no dupes, no version bump
    with deps.connection_factory.unit_of_work() as uow:
        created = seed_comm_presets(uow, presets=deps.repos.comm_presets)
    assert created == 0
    assert {p["name"] for p in svc.list()} == names
    assert all(p["latest_version"] == 1 for p in svc.list())


def test_no_comm_preset_mcp_tool_and_surface_revision_is_28(tmp_path):
    from okto_nexus.adapters.inbound.mcp.server import SURFACE_REVISION

    deps, tools, _root = make_env(tmp_path)
    assert SURFACE_REVISION == 28
    # communication presets add NO MCP tool (operator surface is REST only)
    assert not any("comm_preset" in name or "communication" in name for name in tools)
