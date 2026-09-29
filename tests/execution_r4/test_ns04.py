"""Core-owned catalog, local candidate and inventory publication checks."""

from dataclasses import replace

import pytest
from nexus_connector_core import InstallationCandidate

from okto_nexus.adapters.outbound.execution.core_inventory import (
    discover_local_candidates, local_catalog, local_inventory_snapshot,
)
from okto_nexus.adapters.outbound.sqlite.execution_identity import ensure_execution_installation
from okto_nexus.application.executor_inventory import publish_executor_inventory
from okto_nexus.bootstrap.dependencies import bootstrap
from okto_nexus.domain.execution.keys import ExecutorKey
from okto_nexus.errors import OktoNexusError


def test_ns04_01(monkeypatch, tmp_path):
    import nexus_connector_core as core

    monkeypatch.setattr(core, "create_runtime", lambda **_: (_ for _ in ()).throw(
        AssertionError("runtime composed for catalog")))
    catalog = local_catalog()
    assert any(row["adapter_id"] == "codex_app_server" for row in catalog["runtimes"])
    attach = next(row for row in catalog["runtimes"]
                  if row["adapter_id"] == "claude_attach")
    assert attach["support_status"] == "registered_unqualified"
    assert discover_local_candidates(path_env=str(tmp_path)).candidates == ()


def test_ns04_03(tmp_path):
    deps = bootstrap({}, ["--home", str(tmp_path / "home")])
    identity = ensure_execution_installation(deps.connection_factory)
    principal = ExecutorKey(identity.server_id, identity.embedded_executor_id)
    candidates = [
        InstallationCandidate(
            adapter_id="codex_app_server", executable=str(tmp_path / name),
            fingerprint="sha256:" + "a" * 64, source="path", trust="selected",
            version="0.157.0", architecture="x86_64",
            build_identity="sha256:" + "b" * 64,
        )
        for name in ("copy-a", "copy-b")
    ]

    def snapshot(items, seq):
        return local_inventory_snapshot(
            items, server_id=identity.server_id,
            executor_id=identity.embedded_executor_id,
            producer_instance_id="process-one", publication_sequence=seq,
        )

    first = snapshot(candidates, 1)
    published = publish_executor_inventory(
        deps.connection_factory, principal=principal,
        producer_instance_id="process-one", snapshot=first,
    )
    assert published.reused is False
    assert publish_executor_inventory(
        deps.connection_factory, principal=principal,
        producer_instance_id="process-one", snapshot=first,
    ).reused is True
    reordered = snapshot(list(reversed(candidates)), 2)
    assert reordered["inventory_revision"] == first["inventory_revision"]
    publish_executor_inventory(deps.connection_factory, principal=principal,
                               producer_instance_id="process-one", snapshot=reordered)
    changed = snapshot([replace(candidates[0],
                                fingerprint="sha256:" + "c" * 64,
                                build_identity="sha256:" + "d" * 64),
                        candidates[1]], 3)
    assert changed["inventory_revision"] != first["inventory_revision"]
    publish_executor_inventory(deps.connection_factory, principal=principal,
                               producer_instance_id="process-one", snapshot=changed)
    with pytest.raises(OktoNexusError):
        publish_executor_inventory(deps.connection_factory, principal=principal,
                                   producer_instance_id="process-one", snapshot=first)
    tampered = dict(changed)
    tampered["inventory_revision"] = first["inventory_revision"]
    with pytest.raises(OktoNexusError):
        publish_executor_inventory(deps.connection_factory, principal=principal,
                                   producer_instance_id="process-one", snapshot=tampered)
    with pytest.raises(OktoNexusError):
        publish_executor_inventory(deps.connection_factory, principal=principal,
                                   producer_instance_id="other-process", snapshot=changed)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        current = uow.connection.execute(
            "SELECT publication_sequence,inventory_revision,previous_revision "
            "FROM execution_inventory_current WHERE server_id=? AND executor_id=?",
            (principal.server_id, principal.executor_id),
        ).fetchone()
        count = uow.connection.execute("SELECT COUNT(*) FROM execution_inventory_snapshots "
                                       "WHERE server_id=? AND executor_id=?",
                                       (principal.server_id, principal.executor_id)).fetchone()[0]
        projections = [row[0] for row in uow.connection.execute(
            "SELECT canonical_projection FROM execution_inventory_snapshots")]
    assert tuple(current) == (3, changed["inventory_revision"], first["inventory_revision"])
    assert count == 2
    assert all(str(tmp_path) not in projection for projection in projections)
