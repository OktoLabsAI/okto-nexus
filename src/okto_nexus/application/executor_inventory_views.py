"""Agent-scoped inventory read model with process-local freshness proof."""

from __future__ import annotations

import json
import time

from ..errors import ErrorCode, OktoNexusError


INVENTORY_TTL_MS = 120_000


def read_executor_inventory(factory, *, server_id: str, executor_id: str,
                            agent_id: str,
                            fresh_publications: dict,
                            monotonic_now: float | None = None,
                            context=None, access=None) -> dict:
    """Read only the authenticated agent's executor and current projection.

    After restart the in-memory receipt time is gone. A persisted snapshot
    remains viewable but cannot be treated as fresh for new execution.
    """
    with factory.unit_of_work(write=False) as uow:
        operator = False
        if context is not None or access is not None:
            if context is None or access is None:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The inventory principal is invalid.', {})
            operator = access.authenticate(context, uow=uow, require_feature=False)
            if context.actor_agent_id != agent_id and not operator:
                raise OktoNexusError('SCOPE_MISMATCH',
                                    'Only an operator may inspect another agent\'s runtime options.', {})
        row = uow.connection.execute(
            "SELECT e.control_state,e.registered_by_agent_id,e.kind,"
            "c.publication_sequence,s.canonical_projection,s.observation_age_ms "
            "FROM execution_executors e JOIN execution_inventory_current c "
            "ON c.server_id=e.server_id AND c.executor_id=e.executor_id "
            "JOIN execution_inventory_snapshots s ON s.server_id=c.server_id "
            "AND s.executor_id=c.executor_id AND "
            "s.publication_sequence=c.publication_sequence "
            "WHERE e.server_id=? AND e.executor_id=? "
            "AND e.revoked_at IS NULL",
            (server_id, executor_id),
        ).fetchone()
        local_agent = uow.connection.execute(
            "SELECT is_active FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
        bound_agent = uow.connection.execute(
            "SELECT 1 FROM execution_bindings b JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id "
            "JOIN agents a ON a.agent_id=ep.agent_id WHERE b.server_id=? AND b.executor_id=? "
            "AND ep.agent_id=? AND a.is_active=1 AND ep.enabled=1 AND ep.activation_state='approved' "
            "AND ep.protocol='nxl-r4' LIMIT 1", (server_id, executor_id, agent_id)).fetchone()
    if (row is None or local_agent is None or (not operator and not local_agent['is_active']) or
            (not operator and row["kind"] == "remote" and row["registered_by_agent_id"] != agent_id and bound_agent is None)):
        raise OktoNexusError(ErrorCode.NOT_FOUND,
                              "No inventory is available for this executor.", {})
    snapshot = json.loads(row["canonical_projection"])
    receipt = fresh_publications.get((server_id, executor_id))
    now = time.monotonic() if monotonic_now is None else monotonic_now
    elapsed_ms = max(0, int((now - receipt[1]) * 1000)) if (
        receipt is not None and receipt[0] == row["publication_sequence"]
    ) else INVENTORY_TTL_MS
    remaining = max(0, INVENTORY_TTL_MS - row["observation_age_ms"] - elapsed_ms)
    if row["control_state"] != "CONTROL_READY":
        freshness = "OFFLINE"
    elif remaining == 0:
        freshness = "STALE"
    else:
        freshness = "FRESH"
    return {"snapshot": snapshot, "freshness": freshness,
            "eligible_for_new_start": False}


def runtime_options_from_inventory(*, agent_id: str, inventory_view: dict) -> dict:
    """Keep Core's technical assessment separate from Nexus authority."""
    snapshot = inventory_view["snapshot"]
    freshness = inventory_view["freshness"]
    options = []
    for row in snapshot["availability"]["availability"]:
        policy_reasons = ["BINDING_REQUIRED"]
        if freshness == "OFFLINE":
            policy_reasons.insert(0, "EXECUTOR_OFFLINE")
        elif freshness != "FRESH":
            policy_reasons.insert(0, "INVENTORY_STALE")
        if row["state"] != "READY_FOR_RUNTIME":
            policy_reasons.append("TECHNICAL_NOT_READY")
        options.append({
            "adapter_id": row["adapter_id"],
            "candidate_ref": row["candidate_ref"],
            "label": row["label"],
            "technical_state": row["state"],
            "technical_reasons": list(row["reasons"]),
            "can_prepare": False,
            "can_bind": False,
            "can_start": False,
            "policy_reasons": policy_reasons,
        })
    return {"agent_id": agent_id,
            "executor_id": snapshot["executor_id"],
            "inventory_revision": snapshot["inventory_revision"],
            "catalog": snapshot["catalog"],
            "availability": snapshot["availability"],
            "freshness": freshness, "options": options}
