"""Namespace isolation for future durable R4 execution tables."""

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from okto_nexus.adapters.outbound.sqlite.connection import ConnectionFactory
from okto_nexus.adapters.outbound.sqlite.execution_identity import (
    ensure_execution_installation, register_remote_executor,
)
from okto_nexus.adapters.outbound.sqlite.execution_workspace import (
    bind_approved_workspace, workspace_binding_diff_hash,
)
from okto_nexus.adapters.outbound.sqlite.migrations import MigrationRunner
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.config import load_config
from okto_nexus.domain.execution.keys import (
    ApprovalKey, BindingKey, ExecutorKey, SessionKey,
    SessionOwnerGeneration, StreamKey,
)
from okto_nexus.errors import OktoNexusError


def test_ns02_01():
    left = ExecutorKey("server-a", "executor")
    right = ExecutorKey("server-b", "executor")
    assert left != right
    bindings = {
        BindingKey("server-a", "executor", "same"): "left",
        BindingKey("server-b", "executor", "same"): "right",
    }
    sessions = {
        SessionKey("server-a", "executor", "same"): "left",
        SessionKey("server-b", "executor", "same"): "right",
    }
    streams = {
        StreamKey("server-a", "executor", "same", "epoch"): "left",
        StreamKey("server-b", "executor", "same", "epoch"): "right",
    }
    approvals = {
        ApprovalKey("server-a", "executor", "same", "agent", "ws", "same",
                    SessionOwnerGeneration(1), "request", "native"): "left",
        ApprovalKey("server-b", "executor", "same", "agent", "ws", "same",
                    SessionOwnerGeneration(1), "request", "native"): "right",
    }
    for mapping in (bindings, sessions, streams, approvals):
        left_key = next(key for key in mapping if key.server_id == "server-a")
        del mapping[left_key]
        assert len(mapping) == 1
        assert next(iter(mapping)).server_id == "server-b"
    with pytest.raises((TypeError, ValueError)):
        ApprovalKey("server-a", "executor", "same", "agent", "ws", "same",
                    1, "request", "native")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        SessionKey("server-a", "executor", "x" * 161)


def test_ns02_02(tmp_path):
    """Migration 066 expands a populated legacy store and is replay safe."""
    home = tmp_path / "home"
    config = load_config({}, ["--home", str(home)])
    factory = ConnectionFactory(config)
    migration_source = Path(__file__).resolve().parents[2] / "src/okto_nexus/migrations"
    old_dir = tmp_path / "old-migrations"
    old_dir.mkdir()
    for path in migration_source.glob("[0-9]*_*.sql"):
        if int(path.name.split("_", 1)[0]) < 66:
            shutil.copy2(path, old_dir / path.name)
    assert max(MigrationRunner(factory, old_dir).apply()) == 65
    now = "2026-09-29T00:00:00+00:00"
    conn = factory.get_connection()
    try:
        conn.execute("INSERT INTO agents(agent_id,created_at) VALUES (?,?)",
                     ("agent-a", now))
        conn.execute("INSERT INTO workspaces(workspace_id,created_at) VALUES (?,?)",
                     ("ws-a", now))
        conn.execute("INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,"
                     "adapter_id,protocol,enabled,created_at,updated_at) "
                     "VALUES (?,?,?,?,?,?,?,?)",
                     ("ep-a", "agent-a", "ws-a", "codex", "native", 0, now, now))
        conn.commit()
    finally:
        conn.close()
    assert MigrationRunner(factory).apply() == [66, 67, 68, 69, 70, 71, 72, 73, 74, 75]
    assert MigrationRunner(factory).apply() == []
    conn = factory.get_connection()
    try:
        names = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'execution_%'")}
        assert len(names) == 22
        assert {"execution_operations", "execution_dispatch_outbox",
                "execution_event_ingress", "execution_event_watermarks"} <= names
        assert conn.execute("SELECT enabled FROM agent_endpoints WHERE endpoint_id='ep-a'").fetchone()[0] == 0
        indexes = {row[1] for row in conn.execute("PRAGMA index_list('execution_dispatch_outbox')")}
        assert "idx_execution_dispatch_pending" in indexes
        for server in ("server-a", "server-b"):
            conn.execute("INSERT INTO execution_executors(server_id,executor_id,kind,"
                         "control_state,generation) VALUES (?,?,?,?,?)",
                         (server, "executor", "embedded", "DISCONNECTED", 1))
            conn.execute("INSERT INTO execution_workspace_bindings(server_id,"
                         "workspace_binding_id,executor_id,workspace_id,realization_handle,"
                         "revision,status) VALUES (?,?,?,?,?,?,?)",
                         (server, "same", "executor", "ws-a", "opaque", 1, "PENDING"))
        conn.commit()
        conn.execute("DELETE FROM execution_workspace_bindings WHERE server_id=?",
                     ("server-a",))
        conn.commit()
        assert conn.execute("SELECT server_id FROM execution_workspace_bindings").fetchall()[0][0] == "server-b"
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO execution_workspace_bindings(server_id,"
                         "workspace_binding_id,executor_id,workspace_id,realization_handle,"
                         "revision,status) VALUES (?,?,?,?,?,?,?)",
                         ("server-b", "bad", "missing", "ws-a", "opaque", 1, "PENDING"))
        conn.execute("INSERT INTO execution_executors(server_id,executor_id,kind,"
                     "control_state,generation) VALUES (?,?,?,?,?)",
                     ("server-b", "other-executor", "embedded", "DISCONNECTED", 1))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO execution_bindings(server_id,binding_id,"
                         "executor_id,endpoint_id,workspace_binding_id,candidate_ref,"
                         "inventory_revision,realization_ref,realization_revision,"
                         "binding_revision) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         ("server-b", "bad", "other-executor", "ep-a", "same",
                          "candidate", "revision", "real", 1, 1))
    finally:
        conn.close()


def test_ns02_03(tmp_path):
    """Local server/executor IDs survive restart without claiming Core ownership."""
    home = tmp_path / "installation"
    first = bootstrap({}, ["--home", str(home)])
    identity_a = ensure_execution_installation(first.connection_factory)
    second = bootstrap({}, ["--home", str(home)])
    identity_b = ensure_execution_installation(second.connection_factory)
    assert identity_a == identity_b
    assert identity_a.server_id.startswith("srv_")
    assert identity_a.embedded_executor_id.startswith("exe_")
    with second.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            "SELECT control_state,owner_instance_id,generation FROM execution_executors "
            "WHERE server_id=? AND executor_id=?",
            (identity_b.server_id, identity_b.embedded_executor_id),
        ).fetchone()
    assert tuple(row) == ("DISCONNECTED", None, 1)
    with second.connection_factory.unit_of_work() as uow:
        for actor in ("agent-a", "agent-b"):
            uow.connection.execute("INSERT INTO agents(agent_id,created_at) "
                                   "VALUES (?,?)", (actor, "2026-09-29T00:00:00Z"))
    first_registration = register_remote_executor(
        second.connection_factory, actor_agent_id="agent-a",
        connector_id="connector-a", client_intent_id="intent-a",
    )
    retry = register_remote_executor(
        second.connection_factory, actor_agent_id="agent-a",
        connector_id="connector-a", client_intent_id="intent-a",
    )
    assert retry.executor_id == first_registration.executor_id
    assert retry.reused is True
    assert retry.intent_id == first_registration.intent_id
    with pytest.raises(OktoNexusError):
        register_remote_executor(second.connection_factory, actor_agent_id="agent-a",
                                 connector_id="connector-b", client_intent_id="intent-a")
    with pytest.raises(OktoNexusError):
        register_remote_executor(second.connection_factory, actor_agent_id="agent-b",
                                 connector_id="connector-a", client_intent_id="intent-b")
    with second.connection_factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute("SELECT control_state,owner_instance_id,generation "
                                     "FROM execution_executors WHERE server_id=? AND "
                                     "executor_id=?",
                                     (identity_b.server_id,
                                      first_registration.executor_id)).fetchone()
        assert tuple(row) == ("DISCONNECTED", None, 1)
        count = uow.connection.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        assert count == 3  # operator seed plus two explicit fixtures


def test_ns02_04(tmp_path):
    """An approved opaque root binding never merges distinct remote roots."""
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    factory = deps.connection_factory
    server_id = ensure_execution_installation(factory).server_id
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    with factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute("INSERT INTO agents(agent_id,created_at) VALUES (?,?)",
                     ("agent-a", now.isoformat()))
        conn.execute("INSERT INTO workspaces(workspace_id,created_at,display_name) "
                     "VALUES (?,?,?)", ("ws-a", now.isoformat(), "same repo"))
    executor = register_remote_executor(
        factory, actor_agent_id="agent-a", connector_id="connector-a",
        client_intent_id="register-a",
    ).executor_id

    def approve(proposal_id: str, root: str):
        digest = workspace_binding_diff_hash(
            server_id=server_id, executor_id=executor, workspace_id="ws-a",
            subject_agent_id="agent-a", realization_handle=root,
        )
        with factory.unit_of_work() as uow:
            uow.connection.execute(
                "INSERT INTO execution_proposals(proposal_id,server_id,client_intent_id,"
                "actor_agent_id,subject_agent_id,executor_id,expected_revisions_json,"
                "diff_hash,expires_at,status,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,'2026-10-01T00:00:00+00:00','APPLIED',?)",
                (proposal_id, server_id, proposal_id, "agent-a", "agent-a",
                 executor, "{}", digest, now.isoformat()),
            )

    root_a = "root_aaaaaaaaaaaaaaaa"
    root_b = "root_bbbbbbbbbbbbbbbb"
    approve("proposal-a", root_a)
    first = bind_approved_workspace(
        factory, proposal_id="proposal-a", server_id=server_id,
        executor_id=executor, workspace_id="ws-a", subject_agent_id="agent-a",
        realization_handle=root_a, now=now,
    )
    assert first.status == "PENDING_VALIDATION"
    assert bind_approved_workspace(
        factory, proposal_id="proposal-a", server_id=server_id,
        executor_id=executor, workspace_id="ws-a", subject_agent_id="agent-a",
        realization_handle=root_a, now=now,
    ) == first
    assert bind_approved_workspace(
        factory, proposal_id="proposal-a", server_id=server_id,
        executor_id=executor, workspace_id="ws-a", subject_agent_id="agent-a",
        realization_handle=root_a,
        now=datetime(2026, 10, 2, tzinfo=timezone.utc),
    ) == first
    with pytest.raises(OktoNexusError):
        bind_approved_workspace(
            factory, proposal_id="proposal-a", server_id=server_id,
            executor_id=executor, workspace_id="ws-a", subject_agent_id="agent-a",
            realization_handle=root_b, now=now,
        )
    with pytest.raises(OktoNexusError):
        workspace_binding_diff_hash(
            server_id=server_id, executor_id=executor, workspace_id="ws-a",
            subject_agent_id="agent-a", realization_handle=r"C:\\same-repo\\folder",
        )
    approve("proposal-b", root_b)
    with pytest.raises(OktoNexusError):
        bind_approved_workspace(
            factory, proposal_id="proposal-b", server_id=server_id,
            executor_id=executor, workspace_id="ws-a", subject_agent_id="agent-a",
            realization_handle=root_b,
            now=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )
    second = bind_approved_workspace(
        factory, proposal_id="proposal-b", server_id=server_id,
        executor_id=executor, workspace_id="ws-a", subject_agent_id="agent-a",
        realization_handle=root_b, now=now,
    )
    assert second.workspace_binding_id != first.workspace_binding_id
    with factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute(
            "SELECT workspace_binding_id,realization_handle FROM "
            "execution_workspace_bindings WHERE server_id=? AND executor_id=?",
            (server_id, executor),
        ).fetchall()
    assert {tuple(row) for row in rows} == {
        (first.workspace_binding_id, root_a),
        (second.workspace_binding_id, root_b),
    }
