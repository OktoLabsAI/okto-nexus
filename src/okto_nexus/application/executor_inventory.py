"""Canonical R4 inventory ingress after host authentication.

Core validates the full path-free projection. This service checks the
authenticated executor/producer, sequence CAS and current pointer before
binding is allowed to use an inventory revision. It does no discovery or
provider I/O inside the SQLite transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
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


def load_current_executor_inventory(projection: str) -> dict[str, Any]:
    """Revalidate retained evidence before using it for a new product action.

    Historical snapshots stay readable, but an upgrade requires publication
    of evidence from the current shared Core before admission or dispatch.
    """
    from nexus_connector_core import (
        CoreError, __version__, verify_executor_inventory_snapshot,
    )

    try:
        snapshot = json.loads(projection)
        verify_executor_inventory_snapshot(snapshot)
        if snapshot["core_version"] != __version__:
            raise ValueError("Inventory Core version has changed")
        return snapshot
    except (CoreError, ValueError, TypeError) as exc:
        raise OktoNexusError(
            ErrorCode.CONFLICT,
            "Refresh the executor inventory with the current Core before continuing.",
            {},
        ) from exc


def publish_executor_inventory(factory, *, principal: ExecutorKey,
                               producer_instance_id: str,
                               snapshot: Mapping[str, Any],
                               publication_ticket_id: str | None = None,
                               embedded_owner: tuple[str, int, int] | None = None) -> InventoryPublication:
    """Store one authenticated snapshot; same sequence/content is idempotent."""
    from nexus_connector_core import CoreError, __version__, verify_executor_inventory_snapshot
    from nexus_connector_core.protocol import canonical_json

    try:
        verify_executor_inventory_snapshot(snapshot)
        if snapshot["core_version"] != __version__:
            raise ValueError("Inventory Core version does not match the installed Core")
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
        reconciled_producer = False
        if embedded_owner is not None:
            from ..adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
            owner_id, epoch, generation = embedded_owner
            local = conn.execute(
                "SELECT 1 FROM execution_installation i JOIN execution_executors e "
                "ON e.server_id=i.server_id AND e.executor_id=i.embedded_executor_id "
                "WHERE i.server_id=? AND e.executor_id=? AND e.kind='embedded' "
                "AND e.owner_instance_id=? AND e.generation=? AND e.revoked_at IS NULL "
                "AND e.control_state IN ('RECOVERING','CONTROL_READY')",
                (principal.server_id, principal.executor_id, producer_instance_id, generation)).fetchone()
            if (publication_ticket_id is not None or producer_instance_id != owner_id or
                    local is None or not SqliteRuntimeOutboxRepo().owns(
                        uow, owner_id=owner_id, epoch=epoch,
                        now=datetime.now(timezone.utc).isoformat())):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                      "The embedded inventory owner is no longer current.", {})
            reconciled_producer = True
        if publication_ticket_id is not None:
            # Revalidate the authenticated ticket inside the publication
            # transaction. A current reconciled channel is the only proof
            # that permits replacing an earlier inventory producer.
            authority = conn.execute(
                "SELECT e.owner_instance_id,e.control_state,e.generation,"
                "e.revoked_at AS executor_revoked_at,e.registered_by_agent_id,"
                "t.agent_id,t.binding_id,t.bound_connection_id,t.revoked_at,"
                "t.expires_at,t.audience,t.scopes_json,t.credential_epoch,"
                "t.authorization_revision,r.credential_epoch AS current_epoch,"
                "r.authorization_revision AS current_authorization "
                "FROM execution_executors e JOIN execution_link_tickets t "
                "ON t.server_id=e.server_id AND t.executor_id=e.executor_id "
                "JOIN execution_agent_revisions r ON r.server_id=t.server_id "
                "AND r.agent_id=t.agent_id WHERE e.server_id=? AND e.executor_id=? "
                "AND t.ticket_id=?",
                (principal.server_id, principal.executor_id, publication_ticket_id),
            ).fetchone()
            if (authority is None or authority['revoked_at'] is not None or
                    authority['executor_revoked_at'] is not None or authority['binding_id'] is not None or
                    authority['agent_id'] != authority['registered_by_agent_id'] or
                    authority['audience'] != 'nexus-executor-control' or
                    'inventory:publish' not in json.loads(authority['scopes_json']) or
                    authority['credential_epoch'] != authority['current_epoch'] or
                    authority['authorization_revision'] != authority['current_authorization'] or
                    datetime.fromisoformat(authority['expires_at'].replace('Z', '+00:00')) <= datetime.now(timezone.utc)):
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                      "The inventory publication authority has changed.", {})
            reconciled_producer = (authority['control_state'] == 'CONTROL_READY' and
                authority['owner_instance_id'] == producer_instance_id and
                authority['bound_connection_id'] == producer_instance_id)
            if (authority['generation'] > 1 or authority['owner_instance_id'] is not None) and not reconciled_producer:
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "Publish through the current reconciled control channel.", {})
        existing = conn.execute(
            "SELECT c.publication_sequence,c.inventory_revision,"
            "s.producer_instance_id FROM execution_inventory_current c "
            "JOIN execution_inventory_snapshots s ON s.server_id=c.server_id "
            "AND s.executor_id=c.executor_id AND "
            "s.publication_sequence=c.publication_sequence "
            "WHERE c.server_id=? AND c.executor_id=?",
            (principal.server_id, principal.executor_id),
        ).fetchone()
        if existing is not None:
            old_sequence, old_revision = existing[:2]
            if existing["producer_instance_id"] != producer_instance_id:
                if not reconciled_producer or sequence <= old_sequence:
                    raise OktoNexusError(ErrorCode.CONFLICT,
                                          "A different producer requires channel reconciliation and a newer sequence.", {})
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
