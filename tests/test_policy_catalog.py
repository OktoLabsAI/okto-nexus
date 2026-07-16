"""Tests for B1 - REST /api/v1/policies: the named, versioned policy catalog
(spec 80624c1a, FR9/TR6, BR4/BR5/BR11).

Exercises the operator surface end-to-end over the REAL bootstrap (a migrated
temp SQLite home) through the FastAPI TestClient, plus a few service-level
assertions for the append-only + delete-guard invariants. Creating, editing and
publishing a policy is pure STAGING: it attaches to no one and enforces nothing
(BR4). A version is immutable and monotonic (BR11/BR4). DELETE is blocked while
any agent binds the policy (BR5 -> POLICY_IN_USE), so no pin is ever orphaned.
"""

from __future__ import annotations

import pytest

from okto_nexus.adapters.inbound.mcp.server import bootstrap
from okto_nexus.application.auth import AgentKeyAuthService
from okto_nexus.application.policy_catalog import PolicyCatalogService
from okto_nexus.errors import ErrorCode, OktoNexusError


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


def _service(deps) -> PolicyCatalogService:
    return PolicyCatalogService(
        connection_factory=deps.connection_factory,
        policies=deps.repos.policies,
        policy_bindings=deps.repos.policy_bindings,
        agents=deps.repos.agents,
    )


def _bind(deps, *, agent_id: str, policy_id: str, mode: str = "latest") -> None:
    """Insert a global binding directly (B2's PUT surface is not built yet)."""
    binding = {"source": "global", "policy_id": policy_id, "mode": mode}
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.policy_bindings.replace(uow, agent_id=agent_id, bindings=[binding])


# --------------------------------------------------------------------------- #
# REST lifecycle: header CRUD + append-only version publishing
# --------------------------------------------------------------------------- #
def test_rest_crud_and_version_lifecycle(rest_client):
    client, _deps = rest_client

    # Empty to start.
    assert client.get("/api/v1/policies").json()["data"]["items"] == []

    created = client.post(
        "/api/v1/policies",
        json={"name": "reviewers-only", "description": "Audience for reviewers"},
    )
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    pid = data["policy_id"]
    assert pid.startswith("pol_")
    assert data["name"] == "reviewers-only"
    assert data["description"] == "Audience for reviewers"
    assert data["created_at"]
    assert data["versions"] == []
    assert data["latest_version"] == 0

    # List shows the header.
    items = client.get("/api/v1/policies").json()["data"]["items"]
    assert len(items) == 1 and items[0]["policy_id"] == pid

    # Get one (no versions yet).
    got = client.get(f"/api/v1/policies/{pid}").json()["data"]
    assert got["policy_id"] == pid and got["versions"] == []

    # Publish v1 (the contract's canonical body).
    v1 = client.post(
        f"/api/v1/policies/{pid}/versions",
        json={
            "audience": {"outbound": {"team": ["reviews"]}},
            "governance": [
                {
                    "action": "message_create",
                    "limit_kind": "max_count",
                    "limit_value": 100,
                    "window": "1h",
                }
            ],
        },
    )
    assert v1.status_code == 200, v1.text
    v1d = v1.json()["data"]
    assert v1d["policy_id"] == pid and v1d["version"] == 1
    assert v1d["audience"] == {"outbound": {"team": ["reviews"]}}
    assert v1d["governance"][0]["action"] == "message_create"
    assert v1d["governance"][0]["limit_kind"] == "max_count"
    assert v1d["published_at"]

    # Publish v2 -> monotonic max+1; an empty version is legal (non-restricting).
    v2 = client.post(
        f"/api/v1/policies/{pid}/versions",
        json={"audience": None, "governance": []},
    )
    assert v2.status_code == 200 and v2.json()["data"]["version"] == 2

    # Version history is ascending; v1's body is unchanged (immutable, BR11).
    versions = client.get(f"/api/v1/policies/{pid}/versions").json()["data"]["items"]
    assert [v["version"] for v in versions] == [1, 2]
    assert versions[0]["audience"] == {"outbound": {"team": ["reviews"]}}

    # The header now reports latest_version == 2.
    assert client.get(f"/api/v1/policies/{pid}").json()["data"]["latest_version"] == 2

    # PATCH the header only; versions untouched.
    patched = client.patch(
        f"/api/v1/policies/{pid}", json={"description": "updated note"}
    )
    assert patched.status_code == 200
    pd = patched.json()["data"]
    assert pd["description"] == "updated note" and pd["name"] == "reviewers-only"
    assert pd["latest_version"] == 2

    # DELETE (no bindings) succeeds and clears the catalog.
    deleted = client.delete(f"/api/v1/policies/{pid}")
    assert deleted.status_code == 200
    assert deleted.json()["data"] == {"deleted": True, "policy_id": pid}
    assert client.get("/api/v1/policies").json()["data"]["items"] == []


# --------------------------------------------------------------------------- #
# Fail-closed validation (VALIDATION_ERROR 422)
# --------------------------------------------------------------------------- #
def test_rest_validation_is_fail_closed(rest_client):
    client, _deps = rest_client

    def _code(resp):
        return resp.json()["error"]["code"]

    # Missing / blank name.
    assert client.post("/api/v1/policies", json={"description": "x"}).status_code == 422
    blank = client.post("/api/v1/policies", json={"name": "   "})
    assert blank.status_code == 422 and _code(blank) == "VALIDATION_ERROR"

    # Non-string description.
    bad_desc = client.post("/api/v1/policies", json={"name": "p1", "description": 5})
    assert bad_desc.status_code == 422 and _code(bad_desc) == "VALIDATION_ERROR"

    # Unknown header field (the canonical REST envelope keeps VALIDATION_ERROR
    # lean - no details - so we assert only the status + code).
    unknown = client.post("/api/v1/policies", json={"name": "p2", "color": "red"})
    assert unknown.status_code == 422 and _code(unknown) == "VALIDATION_ERROR"

    # Duplicate name.
    assert client.post("/api/v1/policies", json={"name": "dup"}).status_code == 200
    dup = client.post("/api/v1/policies", json={"name": "dup"})
    assert dup.status_code == 422 and _code(dup) == "VALIDATION_ERROR"

    # Malformed version body (bad governance grammar) and unknown version field.
    pid = client.post("/api/v1/policies", json={"name": "withver"}).json()["data"][
        "policy_id"
    ]
    bad_rule = client.post(
        f"/api/v1/policies/{pid}/versions",
        json={"governance": [{"action": "message_create", "limit_kind": "nope"}]},
    )
    assert bad_rule.status_code == 422 and _code(bad_rule) == "VALIDATION_ERROR"
    bad_field = client.post(f"/api/v1/policies/{pid}/versions", json={"foo": "bar"})
    assert bad_field.status_code == 422 and _code(bad_field) == "VALIDATION_ERROR"

    # Rename onto an existing name is a duplicate too.
    other = client.post("/api/v1/policies", json={"name": "other"}).json()["data"][
        "policy_id"
    ]
    clash = client.patch(f"/api/v1/policies/{other}", json={"name": "dup"})
    assert clash.status_code == 422 and _code(clash) == "VALIDATION_ERROR"


# --------------------------------------------------------------------------- #
# NOT_FOUND (404) across every by-id route
# --------------------------------------------------------------------------- #
def test_rest_unknown_policy_is_not_found(rest_client):
    client, _deps = rest_client
    missing = "pol_does_not_exist"

    responses = [
        client.get(f"/api/v1/policies/{missing}"),
        client.patch(f"/api/v1/policies/{missing}", json={"description": "x"}),
        client.delete(f"/api/v1/policies/{missing}"),
        client.post(f"/api/v1/policies/{missing}/versions", json={"governance": []}),
        client.get(f"/api/v1/policies/{missing}/versions"),
    ]
    for resp in responses:
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# BR5 delete guard: POLICY_IN_USE (409) while any agent binds the policy
# --------------------------------------------------------------------------- #
def test_rest_delete_blocked_while_bound(rest_client):
    client, deps = rest_client
    client.post("/api/v1/agents", json={"agent_id": "alpha", "role": "builder"})
    pid = client.post("/api/v1/policies", json={"name": "bound"}).json()["data"][
        "policy_id"
    ]
    client.post(f"/api/v1/policies/{pid}/versions", json={"governance": []})
    _bind(deps, agent_id="alpha", policy_id=pid)

    blocked = client.delete(f"/api/v1/policies/{pid}")
    assert blocked.status_code == 409, blocked.text
    err = blocked.json()["error"]
    assert err["code"] == "POLICY_IN_USE"
    assert err["details"]["policy_id"] == pid
    assert err["details"]["agents"] == ["alpha"]

    # Detach -> deletable again.
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.policy_bindings.replace(uow, agent_id="alpha", bindings=[])
    assert client.delete(f"/api/v1/policies/{pid}").status_code == 200


# --------------------------------------------------------------------------- #
# Operator-only surface (a third party's key is refused)
# --------------------------------------------------------------------------- #
def test_rest_policies_are_operator_only(rest_client):
    client, deps = rest_client
    client.post("/api/v1/agents", json={"agent_id": "alpha", "role": "builder"})
    alpha_key = _issue_key(deps, "alpha")

    forbidden = client.post(
        "/api/v1/policies",
        json={"name": "x"},
        headers={"x-api-key": alpha_key},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "PERMISSION_DENIED"

    listed = client.get("/api/v1/policies", headers={"x-api-key": alpha_key})
    assert listed.status_code == 403


# --------------------------------------------------------------------------- #
# Service-level invariants (append-only + guard/not-found without HTTP)
# --------------------------------------------------------------------------- #
def test_service_versions_are_append_only_and_immutable(rest_client):
    _client, deps = rest_client
    svc = _service(deps)

    created = svc.create(name="svc-pol")
    pid = created["policy_id"]
    a = svc.publish_version(
        policy_id=pid, audience={"outbound": {"team": ["x"]}}, governance=[]
    )
    b = svc.publish_version(
        policy_id=pid, audience={"outbound": {"team": ["y"]}}, governance=[]
    )
    assert a["version"] == 1 and b["version"] == 2

    versions = svc.list_versions(policy_id=pid)
    assert [v["version"] for v in versions] == [1, 2]
    # v1's frozen body survives v2's publish (immutability).
    assert versions[0]["audience"] == {"outbound": {"team": ["x"]}}


def test_service_guard_and_not_found(rest_client):
    client, deps = rest_client
    svc = _service(deps)

    with pytest.raises(OktoNexusError) as missing:
        svc.get(policy_id="pol_missing")
    assert missing.value.code == ErrorCode.NOT_FOUND.value

    client.post("/api/v1/agents", json={"agent_id": "alpha", "role": "builder"})
    created = svc.create(name="guarded")
    pid = created["policy_id"]
    _bind(deps, agent_id="alpha", policy_id=pid)
    with pytest.raises(OktoNexusError) as in_use:
        svc.delete(policy_id=pid)
    assert in_use.value.code == ErrorCode.POLICY_IN_USE.value
    assert in_use.value.details == {"policy_id": pid, "agents": ["alpha"]}


# --------------------------------------------------------------------------- #
# B2 - PUT /api/v1/agents/{id}/policies (attach/detach bindings, FR10)
# --------------------------------------------------------------------------- #
def _new_policy(client, name: str) -> str:
    resp = client.post("/api/v1/policies", json={"name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["policy_id"]


def _publish(client, policy_id: str, **body) -> int:
    resp = client.post(f"/api/v1/policies/{policy_id}/versions", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["version"]


def test_rest_set_agent_bindings_globals_and_inline(rest_client):
    client, deps = rest_client
    client.post("/api/v1/agents", json={"agent_id": "alpha", "role": "builder"})

    pol_a = _new_policy(client, "pol-a")
    _publish(client, pol_a, governance=[])  # v1
    pol_b = _new_policy(client, "pol-b")
    _publish(client, pol_b, governance=[])  # v1
    _publish(client, pol_b, governance=[])  # v2
    _publish(client, pol_b, governance=[])  # v3

    resp = client.put(
        "/api/v1/agents/alpha/policies",
        json={
            "globals": [
                {"policy_id": pol_a, "mode": "pinned", "pinned_version": 1},
                {"policy_id": pol_b, "mode": "latest"},
            ],
            "inline": {
                "audience": {"outbound": {"team": ["reviews"]}},
                "governance": [],
            },
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["agent_id"] == "alpha"
    # Globals in submission order (pinned@1, latest->3), then inline last.
    assert data["effective_policies"] == [f"{pol_a}@1", f"{pol_b}@3", "inline@-"]

    # Persisted as a full binding set (globals + one inline).
    with deps.connection_factory.unit_of_work(write=False) as uow:
        bindings = deps.repos.policy_bindings.list_for_agent(uow, agent_id="alpha")
    assert [b["source"] for b in bindings] == ["global", "global", "inline"]

    # PUT is a FULL overwrite: an empty body clears every binding.
    cleared = client.put("/api/v1/agents/alpha/policies", json={})
    assert cleared.status_code == 200
    assert cleared.json()["data"]["effective_policies"] == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert deps.repos.policy_bindings.list_for_agent(uow, agent_id="alpha") == []


def test_rest_binding_makes_policy_undeletable_then_deletable(rest_client):
    client, _deps = rest_client
    client.post("/api/v1/agents", json={"agent_id": "alpha", "role": "builder"})
    pid = _new_policy(client, "bound-via-put")
    _publish(client, pid, governance=[])

    client.put(
        "/api/v1/agents/alpha/policies",
        json={"globals": [{"policy_id": pid, "mode": "latest"}]},
    )
    blocked = client.delete(f"/api/v1/policies/{pid}")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["details"]["agents"] == ["alpha"]

    # Detach through the same surface -> deletable again.
    client.put("/api/v1/agents/alpha/policies", json={})
    assert client.delete(f"/api/v1/policies/{pid}").status_code == 200


def test_rest_set_agent_bindings_not_found(rest_client):
    client, _deps = rest_client
    client.post("/api/v1/agents", json={"agent_id": "alpha", "role": "builder"})
    pid = _new_policy(client, "known")
    _publish(client, pid, governance=[])

    # Unknown agent.
    missing_agent = client.put(
        "/api/v1/agents/ghost/policies",
        json={"globals": [{"policy_id": pid, "mode": "latest"}]},
    )
    assert missing_agent.status_code == 404
    assert missing_agent.json()["error"]["code"] == "NOT_FOUND"

    # Known agent, unknown referenced policy.
    missing_policy = client.put(
        "/api/v1/agents/alpha/policies",
        json={"globals": [{"policy_id": "pol_ghost", "mode": "latest"}]},
    )
    assert missing_policy.status_code == 404
    assert missing_policy.json()["error"]["code"] == "NOT_FOUND"


def test_rest_set_agent_bindings_validation(rest_client):
    client, _deps = rest_client
    client.post("/api/v1/agents", json={"agent_id": "alpha", "role": "builder"})
    pid = _new_policy(client, "with-one-version")
    _publish(client, pid, governance=[])  # only v1 exists

    def _code(resp):
        return resp.json()["error"]["code"]

    # pinned_version that was never published -> VALIDATION_ERROR (not NOT_FOUND).
    bad_pin = client.put(
        "/api/v1/agents/alpha/policies",
        json={"globals": [{"policy_id": pid, "mode": "pinned", "pinned_version": 99}]},
    )
    assert bad_pin.status_code == 422 and _code(bad_pin) == "VALIDATION_ERROR"

    # Invalid mode.
    bad_mode = client.put(
        "/api/v1/agents/alpha/policies",
        json={"globals": [{"policy_id": pid, "mode": "always"}]},
    )
    assert bad_mode.status_code == 422 and _code(bad_mode) == "VALIDATION_ERROR"

    # pinned without pinned_version.
    no_pin = client.put(
        "/api/v1/agents/alpha/policies",
        json={"globals": [{"policy_id": pid, "mode": "pinned"}]},
    )
    assert no_pin.status_code == 422 and _code(no_pin) == "VALIDATION_ERROR"

    # Malformed inline governance grammar.
    bad_inline = client.put(
        "/api/v1/agents/alpha/policies",
        json={
            "inline": {"governance": [{"action": "message_create", "limit_kind": "x"}]}
        },
    )
    assert bad_inline.status_code == 422 and _code(bad_inline) == "VALIDATION_ERROR"

    # Unknown top-level field.
    unknown = client.put("/api/v1/agents/alpha/policies", json={"bindings": []})
    assert unknown.status_code == 422 and _code(unknown) == "VALIDATION_ERROR"


def test_rest_set_agent_bindings_operator_only(rest_client):
    client, deps = rest_client
    client.post("/api/v1/agents", json={"agent_id": "alpha", "role": "builder"})
    alpha_key = _issue_key(deps, "alpha")

    forbidden = client.put(
        "/api/v1/agents/alpha/policies",
        json={},
        headers={"x-api-key": alpha_key},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "PERMISSION_DENIED"


def test_service_latest_binding_without_versions_labels_dash(rest_client):
    client, deps = rest_client
    client.post("/api/v1/agents", json={"agent_id": "alpha", "role": "builder"})
    svc = _service(deps)
    pid = svc.create(name="unpublished")["policy_id"]

    result = svc.set_agent_bindings(
        agent_id="alpha", globals_=[{"policy_id": pid, "mode": "latest"}]
    )
    # A latest binding to a policy with no published version yet shows @-.
    assert result["effective_policies"] == [f"{pid}@-"]


# --------------------------------------------------------------------------- #
# C2 read path: GET the current binding set, reshaped for the editor.
# --------------------------------------------------------------------------- #
def test_rest_get_agent_bindings_roundtrips_globals_and_inline(rest_client):
    client, _deps = rest_client
    client.post("/api/v1/agents", json={"agent_id": "alpha", "role": "builder"})

    pol_a = _new_policy(client, "pol-a")
    _publish(client, pol_a, governance=[])  # v1
    pol_b = _new_policy(client, "pol-b")
    _publish(client, pol_b, governance=[])  # v1
    _publish(client, pol_b, governance=[])  # v2

    put_body = {
        "globals": [
            {"policy_id": pol_a, "mode": "pinned", "pinned_version": 1},
            {"policy_id": pol_b, "mode": "latest"},
        ],
        "inline": {
            "audience": {"outbound": {"team": ["reviews"]}},
            "governance": [
                {
                    "action": "message_create",
                    "limit_kind": "deny",
                    "limit_value": None,
                    "window": None,
                }
            ],
        },
    }
    assert client.put("/api/v1/agents/alpha/policies", json=put_body).status_code == 200

    got = client.get("/api/v1/agents/alpha/policies")
    assert got.status_code == 200, got.text
    data = got.json()["data"]
    assert data["agent_id"] == "alpha"
    # Globals in stored order, pinned carries pinned_version, latest omits it.
    assert data["globals"] == [
        {"policy_id": pol_a, "mode": "pinned", "pinned_version": 1},
        {"policy_id": pol_b, "mode": "latest"},
    ]
    assert data["inline"]["audience"] == {"outbound": {"team": ["reviews"]}}
    assert data["inline"]["governance"] == [
        {
            "action": "message_create",
            "limit_kind": "deny",
            "limit_value": None,
            "window": None,
        }
    ]

    # The GET shape feeds straight back into the PUT (round-trip-stable).
    replay = client.put(
        "/api/v1/agents/alpha/policies",
        json={"globals": data["globals"], "inline": data["inline"]},
    )
    assert replay.status_code == 200, replay.text
    assert client.get("/api/v1/agents/alpha/policies").json()["data"] == data


def test_rest_get_agent_bindings_empty_and_not_found(rest_client):
    client, _deps = rest_client
    client.post("/api/v1/agents", json={"agent_id": "alpha", "role": "builder"})

    # No bindings -> unrestricted, ungoverned.
    empty = client.get("/api/v1/agents/alpha/policies")
    assert empty.status_code == 200
    assert empty.json()["data"] == {
        "agent_id": "alpha",
        "globals": [],
        "inline": None,
    }

    # Unknown agent -> NOT_FOUND (fail-closed, same as the PUT).
    ghost = client.get("/api/v1/agents/ghost/policies")
    assert ghost.status_code == 404
    assert ghost.json()["error"]["code"] == "NOT_FOUND"


def test_rest_get_agent_bindings_operator_only(rest_client):
    client, deps = rest_client
    client.post("/api/v1/agents", json={"agent_id": "alpha", "role": "builder"})
    alpha_key = _issue_key(deps, "alpha")

    forbidden = client.get(
        "/api/v1/agents/alpha/policies", headers={"x-api-key": alpha_key}
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "PERMISSION_DENIED"


# --------------------------------------------------------------------------- #
# TS6 - versioning: latest FOLLOWS, pinned FREEZES, publish is immutable (T3)
# --------------------------------------------------------------------------- #
def test_ts6_versioning_latest_follows_pinned_freezes_publish_immutable(rest_client):
    """TS6 (spec 80624c1a): with v1/v2 published, agent A bound latest resolves
    to the highest version and agent B pinned@1 stays on v1; publishing v3
    advances A to v3 while B stays v1, and a previously published version is
    IMMUTABLE (its frozen body survives later publishes; there is no edit-in-
    place, only append)."""
    client, deps = rest_client
    client.post("/api/v1/agents", json={"agent_id": "agent_a", "role": "builder"})
    client.post("/api/v1/agents", json={"agent_id": "agent_b", "role": "reviewer"})
    svc = _service(deps)

    pid = svc.create(name="versioned")["policy_id"]
    assert (
        svc.publish_version(
            policy_id=pid, audience={"outbound": {"team": ["v1"]}}, governance=[]
        )["version"]
        == 1
    )
    assert (
        svc.publish_version(
            policy_id=pid, audience={"outbound": {"team": ["v2"]}}, governance=[]
        )["version"]
        == 2
    )

    # A follows latest (currently 2); B freezes on v1.
    res_a = svc.set_agent_bindings(
        agent_id="agent_a", globals_=[{"policy_id": pid, "mode": "latest"}]
    )
    assert res_a["effective_policies"] == [f"{pid}@2"]
    res_b = svc.set_agent_bindings(
        agent_id="agent_b",
        globals_=[{"policy_id": pid, "mode": "pinned", "pinned_version": 1}],
    )
    assert res_b["effective_policies"] == [f"{pid}@1"]

    # Publish v3: A's latest advances to 3, B's pin stays 1 (re-resolving the
    # live binding set is what the PUT response reports).
    assert (
        svc.publish_version(
            policy_id=pid, audience={"outbound": {"team": ["v3"]}}, governance=[]
        )["version"]
        == 3
    )
    a_now = svc.set_agent_bindings(
        agent_id="agent_a", globals_=[{"policy_id": pid, "mode": "latest"}]
    )
    assert a_now["effective_policies"] == [f"{pid}@3"]
    b_now = svc.set_agent_bindings(
        agent_id="agent_b",
        globals_=[{"policy_id": pid, "mode": "pinned", "pinned_version": 1}],
    )
    assert b_now["effective_policies"] == [f"{pid}@1"]

    # Immutability: every version is append-only and its frozen body is intact -
    # v1 still carries its ORIGINAL audience after v2 and v3 were published.
    versions = svc.list_versions(policy_id=pid)
    assert [v["version"] for v in versions] == [1, 2, 3]
    assert versions[0]["audience"] == {"outbound": {"team": ["v1"]}}
    assert versions[2]["audience"] == {"outbound": {"team": ["v3"]}}


# --------------------------------------------------------------------------- #
# TS7 - delete guard (POLICY_IN_USE) and a nonexistent pin (VALIDATION_ERROR),
# then detach makes the policy deletable (T4)
# --------------------------------------------------------------------------- #
def test_ts7_delete_guard_and_nonexistent_pin(rest_client):
    """TS7 (spec 80624c1a): a bound policy cannot be deleted (POLICY_IN_USE, no
    pin is ever orphaned); a bind that pins a version that was never published is
    a VALIDATION_ERROR (and, being rejected, leaves the prior binding intact so
    the policy stays in use); after detaching all bindings the DELETE succeeds."""
    client, _deps = rest_client
    client.post("/api/v1/agents", json={"agent_id": "alpha", "role": "builder"})
    pid = _new_policy(client, "guarded")
    _publish(client, pid, governance=[])  # only v1 exists

    # Bind (latest) so the policy is in use.
    assert (
        client.put(
            "/api/v1/agents/alpha/policies",
            json={"globals": [{"policy_id": pid, "mode": "latest"}]},
        ).status_code
        == 200
    )

    # DELETE is blocked while bound -> POLICY_IN_USE naming the holder.
    blocked = client.delete(f"/api/v1/policies/{pid}")
    assert blocked.status_code == 409, blocked.text
    err = blocked.json()["error"]
    assert err["code"] == "POLICY_IN_USE"
    assert err["details"]["policy_id"] == pid
    assert err["details"]["agents"] == ["alpha"]

    # A bind pinning a version that was never published -> VALIDATION_ERROR
    # (fail-closed, NOT NOT_FOUND); the rejected PUT does not replace anything.
    bad_pin = client.put(
        "/api/v1/agents/alpha/policies",
        json={"globals": [{"policy_id": pid, "mode": "pinned", "pinned_version": 99}]},
    )
    assert bad_pin.status_code == 422
    assert bad_pin.json()["error"]["code"] == "VALIDATION_ERROR"

    # The prior binding survived the rejected PUT, so the policy is STILL in use.
    assert client.delete(f"/api/v1/policies/{pid}").status_code == 409

    # Detach everything -> the policy becomes deletable.
    assert client.put("/api/v1/agents/alpha/policies", json={}).status_code == 200
    assert client.delete(f"/api/v1/policies/{pid}").status_code == 200
