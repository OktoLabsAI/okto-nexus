"""Agent communication permissions (migration 011): presets + enforcement.

Two layers under test:

* the REST surface (presets CRUD, agent create/patch with preset/flags) over
  the real FastAPI app + SQLite store - the Pulse semantics: a preset COPIES
  its flags onto the agent; explicit flags win; null resets to unrestricted;
* application-layer enforcement, exercised through the real services over the
  real adapters: default-allow for legacy agents, flag denials, the
  quantitative limits (rate) and the PERMISSION_DENIED error shape every
  transport inherits. Directed-send audience restriction moved from
  ``allowed_peers`` to tag-based ``comm_scope`` (F1); its enforcement is
  covered by ``test_comm_scope_outbound.py``.
"""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from okto_nexus.adapters.inbound.http.app import build_app  # noqa: E402
from okto_nexus.adapters.inbound.mcp.server import bootstrap  # noqa: E402
from okto_nexus.adapters.inbound.mcp.tools.handoff import (  # noqa: E402
    build_service as build_handoff_service,
)
from okto_nexus.adapters.inbound.mcp.tools.identity import (  # noqa: E402
    build_service as build_identity_service,
)
from okto_nexus.adapters.inbound.mcp.tools.health import (  # noqa: E402
    build_service as build_health_service,
)
from okto_nexus.adapters.inbound.mcp.tools.memory import (  # noqa: E402
    build_service as build_memory_service,
)
from okto_nexus.adapters.inbound.mcp.tools.messages import (  # noqa: E402
    build_service as build_message_service,
)
from okto_nexus.adapters.inbound.mcp.tools.shared_md import (  # noqa: E402
    build_service as build_shared_md_service,
)
from okto_nexus.domain.permissions import (  # noqa: E402
    BUILTIN_PRESETS,
    PERMISSION_DESCRIPTIONS,
    PERMISSION_REGISTRY,
    PermissionSet,
    builtin_preset,
    validate_permission_flags,
)
from okto_nexus.errors import ErrorCode, OktoNexusError  # noqa: E402


@pytest.fixture
def loopback_client(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    app = build_app(deps)
    with TestClient(app, client=("127.0.0.1", 50100)) as client:
        yield deps, client


@pytest.fixture
def deps(tmp_path):
    return bootstrap({}, ["--home", str(tmp_path / "home")])


def _register(deps, agent_id: str, permissions=None, preset_id=None) -> None:
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.upsert(uow, agent_id=agent_id)
        if permissions is not None or preset_id is not None:
            deps.repos.agents.set_permissions(
                uow, agent_id=agent_id, permissions=permissions, preset_id=preset_id
            )


# --------------------------------------------------------------------------- #
# Domain: registry, presets, PermissionSet semantics
# --------------------------------------------------------------------------- #
def test_builtin_presets_cover_the_registry():
    ids = [p["preset_id"] for p in BUILTIN_PRESETS]
    assert ids == [
        "builtin:full",
        "builtin:coordinator",
        "builtin:worker",
        "builtin:observer",
    ]
    for preset in BUILTIN_PRESETS:
        # Every preset's flags validate against the registry (no drift).
        assert validate_permission_flags(preset["flags"])
    worker = builtin_preset("builtin:worker")["flags"]
    assert worker["messages"]["send_broadcast"] is False
    assert worker["messages"]["send_direct"] is True
    assert worker["handoffs"]["work"] is True
    assert worker["handoffs"]["create"] is False
    observer = builtin_preset("builtin:observer")["flags"]
    assert observer["events"]["read"] is True
    assert observer["messages"]["send_direct"] is False


def test_permission_set_default_allow_and_denial_shape():
    unrestricted = PermissionSet(None)
    assert unrestricted.allows("messages", "send_broadcast")
    assert unrestricted.limit("messages_per_minute") == 0

    restricted = PermissionSet({"messages": {"send_broadcast": False}})
    assert not restricted.allows("messages", "send_broadcast")
    assert restricted.allows("messages", "send_direct")  # absent = allowed
    with pytest.raises(OktoNexusError) as exc:
        restricted.require("messages", "send_broadcast")
    assert exc.value.code == ErrorCode.PERMISSION_DENIED
    assert exc.value.details["required_permission"] == "messages.send_broadcast"


def test_validate_rejects_unknown_flags_and_wrong_types():
    with pytest.raises(OktoNexusError):
        validate_permission_flags({"nope": {}})
    with pytest.raises(OktoNexusError):
        validate_permission_flags({"messages": {"send_direct": "yes"}})
    with pytest.raises(OktoNexusError):
        validate_permission_flags({"limits": {"messages_per_minute": -1}})
    ok = validate_permission_flags({"limits": {"max_recipients": 3}})
    assert ok["limits"]["max_recipients"] == 3


def test_allowed_peers_flag_is_gone_from_the_registry():
    # REMOVED in F1: allowlists are now the tag-based comm_scope.outbound
    # selector. The registry, the descriptions and every builtin preset are
    # clean, so the data-driven dashboard editor drops the field by itself.
    assert "allowed_peers" not in PERMISSION_REGISTRY["messages"]
    assert not any("allowed_peers" in key for key in PERMISSION_DESCRIPTIONS)
    for preset in BUILTIN_PRESETS:
        assert "allowed_peers" not in preset["flags"]["messages"]
    # A NEW payload carrying it is rejected fail-closed as an unknown flag.
    with pytest.raises(OktoNexusError) as exc:
        validate_permission_flags({"messages": {"allowed_peers": ["bob"]}})
    assert exc.value.code == ErrorCode.VALIDATION_ERROR
    assert exc.value.details["flag"] == "messages.allowed_peers"


def test_legacy_allowed_peers_rows_are_inert(deps, tmp_path):
    # A row persisted by an older version keeps its allowed_peers blob; no
    # code reads it anymore, so a direct send to a peer OUTSIDE the old list
    # goes through (the legacy gate has no effect - comm_scope governs now).
    service = build_message_service(deps)
    _register(deps, "legacy")
    _register(deps, "outside")
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.agents.set_permissions(
            uow,
            agent_id="legacy",
            permissions={"messages": {"allowed_peers": ["bob"]}},
            preset_id=None,
        )

    out = service.create_message(
        project_root=str(tmp_path),
        from_agent_id="legacy",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "outside"},
    )
    assert out["recipients"] == ["outside"]


# --------------------------------------------------------------------------- #
# REST: presets CRUD
# --------------------------------------------------------------------------- #
def test_presets_endpoint_lists_builtins_registry_and_descriptions(loopback_client):
    _, client = loopback_client
    data = client.get("/api/v1/presets").json()["data"]
    builtin_ids = [p["preset_id"] for p in data["items"] if p["is_builtin"]]
    assert builtin_ids == [p["preset_id"] for p in BUILTIN_PRESETS]
    assert data["registry"] == PERMISSION_REGISTRY
    assert "messages.send_broadcast" in data["descriptions"]


def test_builtin_presets_are_read_only(loopback_client):
    _, client = loopback_client
    patch = client.patch("/api/v1/presets/builtin:worker", json={"name": "x"})
    assert patch.status_code == 403
    delete = client.delete("/api/v1/presets/builtin:worker")
    assert delete.status_code == 403


def test_custom_preset_crud_roundtrip(loopback_client):
    _, client = loopback_client
    created = client.post(
        "/api/v1/presets",
        json={
            "name": "Restricted worker",
            "description": "no broadcast, capped rate",
            "flags": {
                "messages": {"send_broadcast": False},
                "limits": {"messages_per_minute": 5},
            },
        },
    )
    assert created.status_code == 200
    preset = created.json()["data"]
    assert preset["is_builtin"] is False
    pid = preset["preset_id"]

    # Duplicate name -> validation error.
    dup = client.post(
        "/api/v1/presets", json={"name": "Restricted worker", "flags": {}}
    )
    assert dup.status_code == 422
    # Builtin name collision -> validation error.
    collide = client.post("/api/v1/presets", json={"name": "worker", "flags": {}})
    assert collide.status_code == 422
    # Unknown flag -> validation error.
    bad = client.post(
        "/api/v1/presets", json={"name": "x", "flags": {"messages": {"zap": True}}}
    )
    assert bad.status_code == 422

    patched = client.patch(
        f"/api/v1/presets/{pid}",
        json={"flags": {"messages": {"send_broadcast": True}}},
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["flags"]["messages"]["send_broadcast"] is True

    assert client.delete(f"/api/v1/presets/{pid}").status_code == 200
    assert client.delete(f"/api/v1/presets/{pid}").status_code == 404


# --------------------------------------------------------------------------- #
# REST: agents with presets / flags (the Pulse copy semantics)
# --------------------------------------------------------------------------- #
def test_agent_created_with_preset_copies_its_flags(loopback_client):
    _, client = loopback_client
    created = client.post(
        "/api/v1/agents",
        json={"agent_id": "worker-1", "preset_id": "builtin:worker"},
    ).json()["data"]
    assert created["preset_id"] == "builtin:worker"
    assert created["permissions"]["messages"]["send_broadcast"] is False

    listed = client.get("/api/v1/agents").json()["data"]["items"]
    row = next(a for a in listed if a["agent_id"] == "worker-1")
    assert row["preset_id"] == "builtin:worker"
    assert row["permissions"]["handoffs"]["create"] is False


def test_agent_patch_preset_resets_and_null_restores_full_access(loopback_client):
    _, client = loopback_client
    client.post("/api/v1/agents", json={"agent_id": "a1"})

    patched = client.patch(
        "/api/v1/agents/a1", json={"preset_id": "builtin:observer"}
    ).json()["data"]
    assert patched["permissions"]["messages"]["send_direct"] is False

    # Custom flags win and keep the preset reference.
    custom = client.patch(
        "/api/v1/agents/a1",
        json={"permissions": {"messages": {"send_direct": True}}},
    ).json()["data"]
    assert custom["permissions"]["messages"]["send_direct"] is True

    # Explicit null preset -> unrestricted.
    cleared = client.patch("/api/v1/agents/a1", json={"preset_id": None}).json()["data"]
    assert cleared["permissions"] is None
    assert cleared["preset_id"] is None

    # Unknown preset -> 404; invalid flags -> 422.
    assert (
        client.patch("/api/v1/agents/a1", json={"preset_id": "nope"}).status_code == 404
    )
    assert (
        client.patch(
            "/api/v1/agents/a1", json={"permissions": {"messages": {"zap": 1}}}
        ).status_code
        == 422
    )


def test_deleting_a_custom_preset_keeps_agent_flags(loopback_client):
    _, client = loopback_client
    pid = client.post(
        "/api/v1/presets",
        json={"name": "Quiet", "flags": {"messages": {"send_broadcast": False}}},
    ).json()["data"]["preset_id"]
    client.post("/api/v1/agents", json={"agent_id": "quiet-1", "preset_id": pid})

    assert client.delete(f"/api/v1/presets/{pid}").status_code == 200
    row = client.get("/api/v1/agents/quiet-1").json()["data"]
    # The dangling reference is cleared but the materialised flags survive.
    assert row["preset_id"] is None
    assert row["permissions"]["messages"]["send_broadcast"] is False


# --------------------------------------------------------------------------- #
# Enforcement: application services over the real store
# --------------------------------------------------------------------------- #
def test_broadcast_denied_for_worker_but_direct_allowed(deps, tmp_path):
    service = build_message_service(deps)
    _register(
        deps, "alice", builtin_preset("builtin:worker")["flags"], "builtin:worker"
    )
    _register(deps, "bob")
    root = str(tmp_path)

    with pytest.raises(OktoNexusError) as exc:
        service.create_message(
            project_root=root, from_agent_id="alice", subject="s", body="b"
        )
    assert exc.value.code == ErrorCode.PERMISSION_DENIED
    assert exc.value.details["required_permission"] == "messages.send_broadcast"

    result = service.create_message(
        project_root=root,
        from_agent_id="alice",
        subject="s",
        body="b",
        target={"strategy": "direct", "agent_id": "bob"},
    )
    assert result["recipients"] == ["bob"]


def test_legacy_agent_without_flags_is_unrestricted(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "legacy")
    result = service.create_message(
        project_root=str(tmp_path), from_agent_id="legacy", subject="s", body="b"
    )
    # Broadcast allowed (delivered to nobody: no present agents) - no denial.
    assert result["delivered_count"] == 0


def test_rate_limit_blocks_the_next_send(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "spammy", {"limits": {"messages_per_minute": 2}})
    _register(deps, "bob")
    root = str(tmp_path)
    target = {"strategy": "direct", "agent_id": "bob"}

    for _ in range(2):
        service.create_message(
            project_root=root,
            from_agent_id="spammy",
            subject="s",
            body="b",
            target=target,
        )
    with pytest.raises(OktoNexusError) as exc:
        service.create_message(
            project_root=root,
            from_agent_id="spammy",
            subject="s",
            body="b",
            target=target,
        )
    assert exc.value.code == ErrorCode.PERMISSION_DENIED
    assert exc.value.details["limit"] == 2


def test_channel_post_needs_send_channel_only(deps, tmp_path):
    service = build_message_service(deps)
    # send_broadcast off but send_channel on: posting into a channel works.
    _register(
        deps,
        "chatty",
        {"messages": {"send_broadcast": False, "send_channel": True}},
    )
    root = str(tmp_path)
    channel = service.create_channel(project_root=root, name="general")["channel"]
    result = service.create_message(
        project_root=root,
        from_agent_id="chatty",
        subject="s",
        body="b",
        channel_id=channel["channel_id"],
    )
    assert result["channel_id"] == channel["channel_id"]

    # And with send_channel off the same post is denied.
    _register(deps, "muted", {"messages": {"send_channel": False}})
    with pytest.raises(OktoNexusError) as exc:
        service.create_message(
            project_root=root,
            from_agent_id="muted",
            subject="s",
            body="b",
            channel_id=channel["channel_id"],
        )
    assert exc.value.details["required_permission"] == "messages.send_channel"


def test_channel_create_gated_by_caller_identity(deps, tmp_path):
    service = build_message_service(deps)
    _register(deps, "limited", {"channels": {"create": False}})
    root = str(tmp_path)

    with pytest.raises(OktoNexusError) as exc:
        service.create_channel(project_root=root, name="ops", agent_id="limited")
    assert exc.value.code == ErrorCode.PERMISSION_DENIED
    # An EXISTING channel must not mask the denial via the idempotent path.
    service.create_channel(project_root=root, name="ops")
    with pytest.raises(OktoNexusError):
        service.create_channel(project_root=root, name="ops", agent_id="limited")
    # No identity (cooperative stdio) -> default-allow.
    assert service.create_channel(project_root=root, name="ops")["created"] is False


def test_handoff_create_and_work_gates(deps, tmp_path):
    handoffs = build_handoff_service(deps)
    _register(
        deps, "worker", builtin_preset("builtin:worker")["flags"], "builtin:worker"
    )
    _register(deps, "boss")
    root = str(tmp_path)
    # Handoffs require the workspace row to exist (FK; normally created by
    # session_open / message_create).
    from okto_nexus.domain.ids import resolve_realpath, resolve_workspace_id

    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(
            uow,
            workspace_id=resolve_workspace_id(root),
            root_realpath=resolve_realpath(root),
        )

    # Worker cannot CREATE handoffs...
    with pytest.raises(OktoNexusError) as exc:
        handoffs.handoff_create(
            project_root=root,
            from_agent_id="worker",
            target={"strategy": "broadcast"},
            visibility="public",
        )
    assert exc.value.details["required_permission"] == "handoffs.create"

    # ...but the unrestricted boss can, and the worker CAN claim/complete.
    created = handoffs.handoff_create(
        project_root=root,
        from_agent_id="boss",
        target={"strategy": "broadcast"},
        visibility="public",
    )
    handoff_id = created["handoff_id"]
    claimed = handoffs.handoff_claim(
        project_root=root, handoff_id=handoff_id, agent_id="worker"
    )
    assert claimed["status"] == "CLAIMED"

    # An observer (handoffs.work off) cannot claim.
    _register(
        deps,
        "watcher",
        builtin_preset("builtin:observer")["flags"],
        "builtin:observer",
    )
    second = handoffs.handoff_create(
        project_root=root,
        from_agent_id="boss",
        target={"strategy": "broadcast"},
        visibility="public",
    )
    with pytest.raises(OktoNexusError) as exc:
        handoffs.handoff_claim(
            project_root=root,
            handoff_id=second["handoff_id"],
            agent_id="watcher",
        )
    assert exc.value.details["required_permission"] == "handoffs.work"

    # Cancel is creator-only AND flag-gated: boss may cancel its own.
    cancelled = handoffs.handoff_cancel(
        project_root=root,
        handoff_id=second["handoff_id"],
        agent_id="boss",
    )
    assert cancelled["status"] == "CANCELLED"


def test_permission_denied_maps_to_http_403(loopback_client, tmp_path):
    deps, client = loopback_client
    # The REST error mapper turns PERMISSION_DENIED into 403 (used by the
    # preset guard; service denials inherit the same mapping).
    assert client.delete("/api/v1/presets/builtin:full").status_code == 403


# --------------------------------------------------------------------------- #
# Identity lockdown: self-only registration + whoami (key-derived profile)
# --------------------------------------------------------------------------- #
def test_agent_register_is_self_only_when_authenticated(deps):
    identity = build_identity_service(deps)
    _register(deps, "alice")

    # Authenticated as alice: minting a NEW identity is denied...
    with pytest.raises(OktoNexusError) as exc:
        identity.agent_register(agent_id="mallory", actor_agent_id="alice")
    assert exc.value.code == ErrorCode.PERMISSION_DENIED
    assert exc.value.details["attempted_agent_id"] == "mallory"

    # ...and so is rewriting ANOTHER existing agent's profile.
    _register(deps, "bob")
    with pytest.raises(OktoNexusError):
        identity.agent_register(agent_id="bob", role="hijacked", actor_agent_id="alice")
    with deps.connection_factory.unit_of_work() as uow:
        assert deps.repos.agents.get(uow, "bob").role is None

    # Updating HER OWN profile stays allowed (role/capabilities refresh).
    # Capabilities are fail-closed: register the vocabulary before announcing.
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.capability_catalog.ensure(uow, name="search")
    updated = identity.agent_register(
        agent_id="alice",
        role="researcher",
        capabilities={"search": True},
        actor_agent_id="alice",
    )
    assert updated["role"] == "researcher"

    # No authenticated identity (cooperative stdio): the V1 contract holds.
    free = identity.agent_register(agent_id="newcomer")
    assert free["agent_id"] == "newcomer"


def test_session_open_is_self_only_when_authenticated(deps, tmp_path):
    identity = build_identity_service(deps)
    _register(deps, "alice")
    _register(deps, "bob")
    ws = identity.workspace_resolve(project_root=str(tmp_path))["workspace_id"]

    with pytest.raises(OktoNexusError) as exc:
        identity.session_open(
            agent_id="bob", workspace_id=ws, actor_agent_id="alice"
        )
    assert exc.value.code == ErrorCode.PERMISSION_DENIED
    assert exc.value.details["required_permission"] == "identity.session_self"

    opened = identity.session_open(
        agent_id="alice", workspace_id=ws, actor_agent_id="alice"
    )
    assert opened["agent_id"] == "alice"


def test_agent_register_self_updates_are_permission_gated(deps):
    identity = build_identity_service(deps)
    _register(
        deps,
        "limited",
        {
            "identity": {
                "update_profile": False,
                "update_capabilities": False,
            }
        },
    )
    _register(
        deps,
        "no-caps",
        {
            "identity": {
                "update_profile": True,
                "update_capabilities": False,
            }
        },
    )
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.capability_catalog.ensure(uow, name="ocr")

    with pytest.raises(OktoNexusError) as profile:
        identity.agent_register(
            agent_id="limited", role="worker", actor_agent_id="limited"
        )
    assert profile.value.details["required_permission"] == "identity.update_profile"

    with pytest.raises(OktoNexusError) as caps:
        identity.agent_register(
            agent_id="no-caps",
            capabilities={"ocr": True},
            actor_agent_id="no-caps",
        )
    assert caps.value.details["required_permission"] == "identity.update_capabilities"


def test_workspace_list_permissions_gate_listing_and_paths(deps, tmp_path):
    identity = build_identity_service(deps)
    identity.workspace_resolve(project_root=str(tmp_path), display_name="Project")
    _register(deps, "no-list", {"workspaces": {"list": False}})
    _register(
        deps,
        "no-paths",
        {"workspaces": {"list": True, "include_paths": False}},
    )

    with pytest.raises(OktoNexusError) as denied:
        identity.workspace_list(actor_agent_id="no-list")
    assert denied.value.details["required_permission"] == "workspaces.list"

    rows = identity.workspace_list(actor_agent_id="no-paths")
    assert rows and "root_realpath" not in rows[0]
    with pytest.raises(OktoNexusError) as paths:
        identity.workspace_list(include_paths=True, actor_agent_id="no-paths")
    assert paths.value.details["required_permission"] == "workspaces.include_paths"


def test_experimental_memory_permissions_gate_agent_tools(deps, tmp_path):
    deps.config.feature_memory = True
    memory = build_memory_service(deps)
    root = str(tmp_path)
    _register(deps, "writer")
    _register(deps, "no-write", {"experimental": {"memory_write": False}})
    _register(
        deps,
        "no-read",
        {
            "experimental": {
                "memory_read": False,
                "memory_search": False,
            }
        },
    )

    with pytest.raises(OktoNexusError) as write_denied:
        memory.put_memory(
            project_root=root,
            agent_id="no-write",
            title="blocked",
            content="blocked",
        )
    assert (
        write_denied.value.details["required_permission"]
        == "experimental.memory_write"
    )

    created = memory.put_memory(
        project_root=root,
        agent_id="writer",
        title="ok",
        content="searchable content",
    )
    with pytest.raises(OktoNexusError) as read_denied:
        memory.get_memory(
            project_root=root,
            memory_id=created["memory_id"],
            agent_id="no-read",
        )
    assert (
        read_denied.value.details["required_permission"] == "experimental.memory_read"
    )
    with pytest.raises(OktoNexusError) as search_denied:
        memory.search_memory(project_root=root, query="searchable", agent_id="no-read")
    assert (
        search_denied.value.details["required_permission"]
        == "experimental.memory_search"
    )


def test_shared_md_and_health_permissions_are_gated(deps, tmp_path):
    identity = build_identity_service(deps)
    ws = identity.workspace_resolve(project_root=str(tmp_path))["workspace_id"]
    _register(
        deps,
        "limited",
        {
            "shared_md": {"render": False},
            "health": {"read": False},
        },
    )

    shared = build_shared_md_service(deps)
    with pytest.raises(OktoNexusError) as render_denied:
        shared.shared_md_render(workspace_id=ws, agent_id="limited")
    assert render_denied.value.details["required_permission"] == "shared_md.render"

    deps.config.feature_health = True
    health = build_health_service(deps)
    health.require_feature_health()
    with pytest.raises(OktoNexusError) as health_denied:
        health.require_agent_read(agent_id="limited")
    assert health_denied.value.details["required_permission"] == "health.read"


def test_agent_whoami_returns_own_profile_with_permissions(deps):
    identity = build_identity_service(deps)
    _register(
        deps,
        "worker-7",
        builtin_preset("builtin:worker")["flags"],
        "builtin:worker",
    )
    # Capabilities are fail-closed: register the vocabulary before announcing.
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.capability_catalog.ensure(uow, name="ocr")
    identity.agent_register(
        agent_id="worker-7",
        role="executor",
        capabilities={"ocr": True},
        actor_agent_id="worker-7",
    )

    me = identity.agent_whoami(actor_agent_id="worker-7")
    assert me["agent_id"] == "worker-7"
    assert me["role"] == "executor"
    assert me["capabilities"] == {"ocr": True}
    assert me["preset_id"] == "builtin:worker"
    assert me["permissions"]["messages"]["send_broadcast"] is False
    assert me["is_active"] is True

    # No authenticated identity -> prescriptive VALIDATION_ERROR.
    with pytest.raises(OktoNexusError) as exc:
        identity.agent_whoami(actor_agent_id=None)
    assert exc.value.code == ErrorCode.VALIDATION_ERROR

    # A deleted identity surfaces NOT_FOUND (not a silent recreate).
    with pytest.raises(OktoNexusError) as exc:
        identity.agent_whoami(actor_agent_id="ghost")
    assert exc.value.code == ErrorCode.NOT_FOUND
