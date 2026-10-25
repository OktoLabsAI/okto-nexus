"""The endpoint update policy is an operator setting outside every consent digest (#89)."""
import shutil

import pytest
from test_canonical_boot import configure
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner, _default_migrations_dir
from okto_nexus.application.execution_leases import _agent_guard
from okto_nexus.config import NexusConfig
from okto_nexus.errors import ErrorCode, OktoNexusError


def state(setup, binding):
    deps = setup[0]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        agent = conn.execute("SELECT agent_id,revision,runtime_update_policy FROM agent_endpoints WHERE endpoint_id=?",
                             (binding["endpoint_id"],)).fetchone()
        _, revisions, _ = current_agent_revisions(deps.connection_factory, agent_id=agent["agent_id"], uow=uow,
                                                  require_active=False, persist=False)
        return dict(
            policy=agent["runtime_update_policy"], revision=agent["revision"], revisions=revisions,
            guard=_agent_guard(conn, agent["agent_id"]),
            grants=[dict(r) for r in conn.execute("SELECT * FROM runtime_execution_grants WHERE endpoint_id=?", (binding["endpoint_id"],))],
            boot=[dict(r) for r in conn.execute("SELECT * FROM runtime_boot_bindings WHERE endpoint_id=?", (binding["endpoint_id"],))],
            audit=[dict(r) for r in conn.execute("SELECT * FROM runtime_access_audit WHERE resource_id=? "
                "AND changed_fields='[\"runtime_update_policy\"]'", (binding["endpoint_id"],))])


def test_setter_keeps_revision_guard_grants_and_boot_and_is_operator_only(connected_local):
    setup, binding, _ = connected_local
    client, headers = setup[2], setup[3]
    configure(setup, binding)
    path = f"/api/v1/harness/endpoints/{binding['endpoint_id']}/update-policy"
    before = state(setup, binding)
    assert before["policy"] is None and not any(g["revoked_at"] for g in before["grants"])
    current = client.get(path, headers=headers["operator"]).json()["data"]
    assert (current["policy"], current["effective_policy"], current["policy_source"]) == (None, "review", "hub")
    body = dict(expected_revision=current["revision"], policy="follow")
    assert client.put(path, headers=headers["subject"], json=body).status_code == 403
    assert state(setup, binding)["policy"] is None
    saved = client.put(path, headers=headers["operator"], json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"] == dict(endpoint_id=binding["endpoint_id"], agent_id=saved.json()["data"]["agent_id"],
        revision=before["revision"], policy="follow", effective_policy="follow", policy_source="endpoint",
        hub_policy="review")
    after = state(setup, binding)
    # Same revision, guard, grants and boot row: a lease renewal sees no change.
    assert after["policy"] == "follow"
    assert {k: after[k] for k in ("revision", "revisions", "guard", "grants", "boot")} == \
        {k: before[k] for k in ("revision", "revisions", "guard", "grants", "boot")}
    assert len(after["audit"]) == 1
    assert client.put(path, headers=headers["operator"], json=body | {"policy": "review"}).status_code == 200
    assert client.put(path, headers=headers["operator"], json=body | {"policy": "bogus"}).status_code in (400, 422)
    assert client.put(path, headers=headers["operator"], json=body | {"extra": 1}).status_code in (400, 422)
    assert client.put(path, headers=headers["operator"], json=dict(expected_revision=current["revision"] + 5, policy=None)).status_code == 409
    cleared = client.put(path, headers=headers["operator"], json=dict(expected_revision=current["revision"], policy=None))
    assert cleared.json()["data"]["policy"] is None
    assert state(setup, binding)["guard"] == before["guard"]


def test_generic_paths_reject_the_policy_key(connected_local):
    setup, binding, _ = connected_local
    from okto_nexus.adapters.inbound.mcp.tools.harness import build_endpoint_service
    service = build_endpoint_service(setup[0])
    descriptor = service.registry.resolve("claude_code", "stream")
    with pytest.raises(OktoNexusError) as error:
        service.validate_public_config(descriptor, "conversation", {"runtime_update_policy": "follow"})
    assert error.value.code == ErrorCode.VALIDATION_ERROR
    client, headers = setup[2], setup[3]
    for body in ({"runtime_update_policy": "follow"}, {"public_config": {"runtime_update_policy": "follow"}}):
        response = client.put(f"/api/v1/harness/endpoints/{binding['endpoint_id']}",
                              headers=headers["operator"], json=dict(expected_revision=1, **body))
        assert response.status_code != 200, response.text
    assert state(setup, binding)["policy"] is None


def test_migration_155_adds_column_and_append_only_table_to_existing_rows(tmp_path):
    old = tmp_path / "old"
    old.mkdir()
    for path in _default_migrations_dir().glob("*.sql"):
        if int(path.name.split("_")[0]) <= 154:
            shutil.copy(path, old)
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path / "home"))
    MigrationRunner(factory, migrations_dir=old).apply()
    now = "2026-01-01T00:00:00Z"
    with factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute("INSERT INTO workspaces(workspace_id,created_at) VALUES(?,?)", ("workspace", now))
        conn.execute("INSERT INTO agents(agent_id,created_at) VALUES(?,?)", ("agent", now))
        conn.execute("INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,adapter_id,protocol,created_at,updated_at) "
                     "VALUES(?,?,?,?,?,?,?)", ("endpoint", "agent", "workspace", "fixture", "nxl-r4", now, now))
    assert MigrationRunner(factory).apply() == [155, 156, 157]
    assert MigrationRunner(factory).apply() == []
    row = lambda *v: ("s", "e", "a", "ref", v[1], "r", "review", "hub", "hub", "b2", now)
    insert = ("INSERT INTO execution_installation_succession(server_id,executor_id,adapter_id,stable_ref,decision,"
              "reason,policy,policy_source,decided_by,to_build_identity,decided_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)")
    with factory.unit_of_work() as uow:
        conn = uow.connection
        assert conn.execute("SELECT runtime_update_policy FROM agent_endpoints").fetchone()[0] is None
        conn.execute("UPDATE agent_endpoints SET runtime_update_policy='follow'")
        conn.execute(insert, row(1, "held"))
        conn.execute(insert, row(2, "accepted"))
        assert [r[0] for r in conn.execute("SELECT id FROM execution_installation_succession ORDER BY id")] == [1, 2]
    for statement, args in ((insert, row(3, "held")),):
        with factory.unit_of_work() as uow, pytest.raises(Exception, match="UNIQUE"):
            uow.connection.execute(statement, args)
    with factory.unit_of_work() as uow, pytest.raises(Exception, match="check|CHECK"):
        uow.connection.execute("UPDATE agent_endpoints SET runtime_update_policy='hold'")
    with factory.unit_of_work() as uow, pytest.raises(Exception, match="check|CHECK"):
        uow.connection.execute(insert, ("s", "e", "a", "ref", "held", "r", "hold", "hub", "hub", "b3", now))
    for sql in ("UPDATE execution_installation_succession SET reason='x'", "DELETE FROM execution_installation_succession"):
        with factory.unit_of_work() as uow, pytest.raises(Exception, match="append_only"):
            uow.connection.execute(sql)


@pytest.mark.parametrize("keep_agents", [True, False])
def test_database_reset_handles_the_append_only_succession_table(tmp_path, keep_agents):
    from okto_nexus.application.database_reset import clear_operational_history
    factory = ConnectionFactory(NexusConfig(home_dir=tmp_path / "home"))
    MigrationRunner(factory).apply()
    insert = ("INSERT INTO execution_installation_succession(server_id,executor_id,adapter_id,stable_ref,decision,"
              "reason,policy,policy_source,decided_by,to_build_identity,decided_at) "
              "VALUES('s','e','a','ref','accepted','operator_accepted','review','hub','operator','b','2026-01-01T00:00:00Z')")
    with factory.unit_of_work() as uow:
        uow.connection.execute(insert)
    with factory.unit_of_work() as uow:
        clear_operational_history(uow.connection, keep_agents=keep_agents)
    with factory.unit_of_work(write=False) as uow:
        count = uow.connection.execute("SELECT COUNT(*) FROM execution_installation_succession").fetchone()[0]
    # An operator accept is connection state: it survives a reset that keeps agents.
    assert count == (1 if keep_agents else 0)
    with factory.unit_of_work() as uow:
        uow.connection.execute(insert.replace("'b'", "'c'"))
    with factory.unit_of_work() as uow, pytest.raises(Exception, match="append_only"):
        uow.connection.execute("DELETE FROM execution_installation_succession")
