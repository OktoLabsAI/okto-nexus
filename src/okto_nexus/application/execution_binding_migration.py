"""Reviewed adoption of a migrated local endpoint, preserving its identity."""
import hashlib
import json

from ..errors import ErrorCode, OktoNexusError


def migration_target(conn, *, server_id, executor_id, subject_agent_id,
                     workspace_id, adapter_id, endpoint_id):
    row = conn.execute("SELECT * FROM agent_endpoints WHERE endpoint_id=? AND agent_id=? AND workspace_id=?",
                       (endpoint_id, subject_agent_id, workspace_id)).fetchone()
    mapping = conn.execute("SELECT * FROM execution_migration_map WHERE source='nexus-r4-catalog-v1' "
                           "AND source_type='agent_endpoints' AND legacy_id=?", (endpoint_id,)).fetchone()
    if row is None or mapping is None:
        raise OktoNexusError(ErrorCode.NOT_FOUND, "The migrated endpoint was not found in this scope.", {})
    ref = json.loads(mapping["canonical_ref"])
    digest = hashlib.sha256(json.dumps(dict(row),sort_keys=True,separators=(",",":"),
                                       ensure_ascii=True).encode()).hexdigest()
    if (mapping["state"] != "REDISCOVERY_REQUIRED" or mapping["row_digest_before"] != digest
            or ref.get("server_id") != server_id or ref.get("executor_id") != executor_id
            or ref.get("canonical_adapter_id") != adapter_id
            or conn.execute("SELECT 1 FROM execution_bindings WHERE endpoint_id=?", (endpoint_id,)).fetchone()):
        raise OktoNexusError(ErrorCode.CONFLICT, "The migrated endpoint requires a new review.", {})
    try:
        config = json.loads(row["public_config"])
    except (TypeError, ValueError):
        config = None
    if not isinstance(config, dict):
        raise OktoNexusError(ErrorCode.CONFLICT, "Review the legacy endpoint configuration before adoption.", {})
    if conn.execute("SELECT 1 FROM harness_sessions WHERE endpoint_id=? "
                    "AND (upper(status)<>'ENDED' OR ended_at IS NULL "
                    "OR lifecycle_state NOT IN ('stopped','legacy_unlinked')) LIMIT 1", (endpoint_id,)).fetchone():
        raise OktoNexusError(ErrorCode.CONFLICT,
            "Drain or reconcile the legacy endpoint sessions before adopting this endpoint.", {})
    return {"endpoint_id": endpoint_id, "revision": row["revision"],
            "enabled": row["enabled"], "activation_state": row["activation_state"],
            "profile_id": row["profile_id"], "source_digest": digest}


def apply_migration(conn, *, proposal, expected, profile_id, alias, now):
    changed = conn.execute("UPDATE agent_endpoints SET adapter_id=?,protocol='nxl-r4',profile_id=?,"
        "public_config=json_set(public_config,?,?),revision=revision+1,updated_at=? WHERE endpoint_id=? AND revision=?",
        (proposal["adapter_id"],profile_id,"$.alias",alias,
         now,expected["endpoint_id"],expected["revision"])).rowcount
    if changed != 1:
        raise OktoNexusError(ErrorCode.CONFLICT, "The migrated endpoint changed after review.", {})
    changed = conn.execute("UPDATE execution_migration_map SET state='BINDING_ADOPTED' "
        "WHERE source='nexus-r4-catalog-v1' AND source_type='agent_endpoints' AND legacy_id=? "
        "AND row_digest_before=? AND state='REDISCOVERY_REQUIRED'",
        (expected["endpoint_id"],expected["source_digest"])).rowcount
    if changed != 1:
        raise OktoNexusError(ErrorCode.CONFLICT, "The migration record changed after review.", {})


def record_adoption(conn, *, proposal):
    def digest(row):
        return hashlib.sha256(json.dumps(dict(row),sort_keys=True,separators=(",",":"),
                                         ensure_ascii=True).encode()).hexdigest()
    endpoint = conn.execute("SELECT * FROM agent_endpoints WHERE endpoint_id=?", (proposal["endpoint_id"],)).fetchone()
    profile = conn.execute("SELECT * FROM runtime_profiles WHERE profile_id=?", (endpoint["profile_id"],)).fetchone()
    binding = conn.execute("SELECT * FROM execution_bindings WHERE server_id=? AND binding_id=?",
                           (proposal["server_id"],proposal["binding_id"])).fetchone()
    row = conn.execute("SELECT canonical_ref FROM execution_migration_map WHERE source='nexus-r4-catalog-v1' "
                       "AND source_type='agent_endpoints' AND legacy_id=? AND state='BINDING_ADOPTED'",
                       (proposal["endpoint_id"],)).fetchone()
    if row is None:
        raise OktoNexusError(ErrorCode.CONFLICT, "The adoption record is unavailable.", {})
    ref = json.loads(row[0])
    ref["adoption"] = {"proposal_id":proposal["proposal_id"],"endpoint_digest":digest(endpoint),
                      "profile_id":endpoint["profile_id"],"profile_digest":digest(profile) if profile else None,
                      "binding_id":proposal["binding_id"],"binding_digest":digest(binding)}
    conn.execute("UPDATE execution_migration_map SET canonical_ref=? WHERE source='nexus-r4-catalog-v1' "
                 "AND source_type='agent_endpoints' AND legacy_id=?",
                 (json.dumps(ref,sort_keys=True,separators=(",",":")),proposal["endpoint_id"]))
