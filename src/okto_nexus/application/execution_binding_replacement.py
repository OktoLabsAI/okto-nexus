"""Explicit, reviewed replacement of one idle binding's realization."""
import json

from ..errors import ErrorCode, OktoNexusError


def replacement_target(conn, *, server_id, subject_agent_id, executor_id,
                       workspace_id, adapter_id, alias, binding_id):
    row = conn.execute(
        "SELECT b.*,ep.agent_id,ep.workspace_id,ep.adapter_id,ep.profile_id,ep.public_config,"
        "ep.enabled,ep.activation_state,ep.protocol FROM execution_bindings b "
        "JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id WHERE b.server_id=? "
        "AND b.executor_id=? AND b.binding_id=? AND ep.agent_id=?",
        (server_id, executor_id, binding_id, subject_agent_id)).fetchone()
    if row is None:
        raise OktoNexusError(ErrorCode.NOT_FOUND, "The replacement binding was not found in this scope.", {})
    if (row["workspace_id"] != workspace_id or row["adapter_id"] != adapter_id
            or row["protocol"] != "nxl-r4" or not row["enabled"]
            or row["activation_state"] != "approved"
            or json.loads(row["public_config"] or "{}").get("alias") != alias):
        raise OktoNexusError(ErrorCode.CONFLICT, "The replacement must preserve the approved binding scope.", {})
    if conn.execute("SELECT 1 FROM execution_sessions WHERE server_id=? AND executor_id=? "
                    "AND binding_id=? AND lifecycle_state<>'CLOSED' "
                    "AND NOT (lifecycle_state='FAILED' AND lease_state='CLOSED') LIMIT 1",
                    (server_id, executor_id, binding_id)).fetchone():
        raise OktoNexusError(ErrorCode.CONFLICT,
            "Close or reconcile the binding's active sessions before replacing its realization.", {})
    return {key: row[key] for key in ("binding_id", "endpoint_id", "profile_id", "binding_revision",
        "workspace_binding_id", "candidate_ref", "inventory_revision", "realization_ref", "realization_revision")}


def apply_replacement(conn, *, proposal, expected):
    changed = conn.execute(
        "UPDATE execution_bindings SET workspace_binding_id=?,candidate_ref=?,inventory_revision=?,"
        "realization_ref=?,realization_revision=?,binding_revision=binding_revision+1 "
        "WHERE server_id=? AND executor_id=? AND binding_id=? AND binding_revision=?",
        (proposal["workspace_binding_id"], proposal["candidate_ref"], proposal["inventory_revision"],
         proposal["realization_ref"], proposal["realization_revision"], proposal["server_id"],
         proposal["executor_id"], proposal["binding_id"], expected["binding_revision"])).rowcount
    if changed != 1:
        raise OktoNexusError(ErrorCode.CONFLICT, "The replacement binding changed after review.", {})
