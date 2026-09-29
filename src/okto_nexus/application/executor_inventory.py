"""Canonical R4 inventory ingress after host authentication.

Core validates the full path-free projection. This service checks the
authenticated executor/producer, sequence CAS and current pointer before
binding is allowed to use an inventory revision. It does no discovery or
provider I/O inside the SQLite transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..domain.execution.keys import ExecutorKey
from ..errors import ErrorCode, OktoNexusError


@dataclass(frozen=True, slots=True)
class InventoryPublication:
    server_id: str
    executor_id: str
    publication_sequence: int
    inventory_revision: str
    reused: bool


def publish_executor_inventory(factory, *, principal: ExecutorKey,
                               producer_instance_id: str,
                               snapshot: Mapping[str, Any]) -> InventoryPublication:
    """Store one authenticated snapshot; same sequence/content is idempotent."""
    from nexus_connector_core import CoreError, verify_executor_inventory_snapshot
    from nexus_connector_core.protocol import canonical_json

    try:
        verify_executor_inventory_snapshot(snapshot)
        projection = canonical_json(dict(snapshot))
    except (CoreError, ValueError, TypeError) as exc:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid executor inventory snapshot.", {}) from exc
    if len(projection) > 1024 * 1024:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Executor inventory snapshot is too large.", {})
    if (snapshot["server_id"] != principal.server_id or
            snapshot["executor_id"] != principal.executor_id or
            snapshot["producer_instance_id"] != producer_instance_id):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                              "Inventory producer scope does not match.", {})
    sequence = snapshot["publication_sequence"]
    revision = snapshot["inventory_revision"]
    with factory.unit_of_work() as uow:
        conn = uow.connection
        existing = conn.execute(
            "SELECT publication_sequence,inventory_revision FROM execution_inventory_current "
            "WHERE server_id=? AND executor_id=?",
            (principal.server_id, principal.executor_id),
        ).fetchone()
        if existing is not None:
            old_sequence, old_revision = existing
            if sequence < old_sequence or (sequence == old_sequence and revision != old_revision):
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "Stale or conflicting inventory sequence.", {})
            if sequence == old_sequence:
                return InventoryPublication(principal.server_id,
                                            principal.executor_id, sequence,
                                            revision, True)
        conn.execute(
            "INSERT INTO execution_inventory_snapshots(server_id,executor_id,"
            "publication_sequence,inventory_revision,catalog_format,availability_format,"
            "snapshot_format,core_version,canonical_projection,received_at,"
            "observation_age_ms,producer_instance_id) VALUES (?,?,?,?,?,?,?,?,"
            "?,strftime('%Y-%m-%dT%H:%M:%fZ','now'),?,?)",
            (principal.server_id, principal.executor_id, sequence, revision,
             snapshot["catalog"]["format_version"],
             snapshot["availability"]["format_version"],
             snapshot["snapshot_format_version"], snapshot["core_version"],
             projection.decode("utf-8"), snapshot["observation_age_ms"],
             producer_instance_id),
        )
        if existing is None:
            conn.execute(
                "INSERT INTO execution_inventory_current(server_id,executor_id,"
                "publication_sequence,inventory_revision) VALUES (?,?,?,?)",
                (principal.server_id, principal.executor_id, sequence, revision),
            )
        else:
            conn.execute(
                "UPDATE execution_inventory_current SET publication_sequence=?,"
                "inventory_revision=?,previous_revision=? WHERE server_id=? AND executor_id=?",
                (sequence, revision, existing["inventory_revision"],
                 principal.server_id, principal.executor_id),
            )
        # Keep the current and immediately previous publication only.
        conn.execute(
            "DELETE FROM execution_inventory_snapshots WHERE server_id=? AND executor_id=? "
            "AND publication_sequence NOT IN (SELECT publication_sequence FROM "
            "execution_inventory_snapshots WHERE server_id=? AND executor_id=? "
            "ORDER BY publication_sequence DESC LIMIT 2)",
            (principal.server_id, principal.executor_id,
             principal.server_id, principal.executor_id),
        )
    return InventoryPublication(principal.server_id, principal.executor_id,
                                sequence, revision, False)
