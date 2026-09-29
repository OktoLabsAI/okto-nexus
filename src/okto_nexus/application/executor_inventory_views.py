"""Agent-scoped inventory read model with process-local freshness proof."""

from __future__ import annotations

import json
import time

from ..errors import ErrorCode, OktoNexusError


INVENTORY_TTL_MS = 120_000


def read_executor_inventory(factory, *, server_id: str, executor_id: str,
                            agent_id: str,
                            fresh_publications: dict,
                            monotonic_now: float | None = None) -> dict:
    """Read only the authenticated agent's executor and current projection.

    After restart the in-memory receipt time is gone. A persisted snapshot
    remains viewable but cannot be treated as fresh for new execution.
    """
    with factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            "SELECT e.control_state,e.registered_by_agent_id,"
            "c.publication_sequence,s.canonical_projection,s.observation_age_ms "
            "FROM execution_executors e JOIN execution_inventory_current c "
            "ON c.server_id=e.server_id AND c.executor_id=e.executor_id "
            "JOIN execution_inventory_snapshots s ON s.server_id=c.server_id "
            "AND s.executor_id=c.executor_id AND "
            "s.publication_sequence=c.publication_sequence "
            "WHERE e.server_id=? AND e.executor_id=? AND e.kind='remote' "
            "AND e.revoked_at IS NULL",
            (server_id, executor_id),
        ).fetchone()
    if row is None or row["registered_by_agent_id"] != agent_id:
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
