"""Prepare R4 bindings as durable, effect-free scoped proposals."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
import time
from typing import Any, Mapping

from nexus_connector_core.protocol import canonical_json

from ..errors import ErrorCode, OktoNexusError
from ..adapters.outbound.sqlite.connection import ConnectionFactory
from ..adapters.outbound.sqlite.execution_agent_revisions import (
    current_agent_revisions,
)


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def _safe_label(value: object, fallback: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 160 or
            any(char in value for char in ("/", "\\", ":"))):
        return fallback
    return value


def _agent_guard(conn, agent_id: str) -> str:
    """Hash source rows under the same transaction as proposal or apply."""
    agent = conn.execute("SELECT * FROM agents WHERE agent_id=?",
                         (agent_id,)).fetchone()
    if agent is None or not agent["is_active"]:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                              "The agent is unavailable.", {})
    methods = [dict(row) for row in conn.execute(
        "SELECT * FROM agent_connection_methods WHERE agent_id=? "
        "ORDER BY method", (agent_id,))]
    endpoints = [dict(row) for row in conn.execute(
        "SELECT * FROM agent_endpoints WHERE agent_id=? ORDER BY endpoint_id",
        (agent_id,))]
    profiles = [dict(row) for row in conn.execute(
        "SELECT DISTINCT p.* FROM runtime_profiles p JOIN agent_endpoints e "
        "ON e.profile_id=p.profile_id WHERE e.agent_id=? ORDER BY p.profile_id",
        (agent_id,))]
    agent_fields = (
        "role", "capabilities", "metadata", "api_key_hash", "is_active",
        "permissions", "preset_id", "tags", "comm_scope", "color",
    )
    endpoint_fields = (
        "endpoint_id", "workspace_id", "adapter_id", "protocol",
        "contract_version", "profile_id", "enabled", "activation_state",
        "health", "priority", "selection_group", "consumption",
        "response_policy", "public_config", "revision",
    )
    profile_fields = (
        "profile_id", "adapter_id", "config", "secret_refs",
        "inherit_ambient", "enabled", "revision",
    )
    return _digest({
        "agent": {key: agent[key] for key in agent_fields},
        "methods": methods,
        "endpoints": [{key: row[key] for key in endpoint_fields}
                      for row in endpoints],
        "profiles": [{key: row[key] for key in profile_fields}
                     for row in profiles],
    })


def prepare_execution_binding(
    factory: ConnectionFactory, *, actor_agent_id: str,
    request: Mapping[str, Any], fresh_publications: Mapping,
) -> dict[str, Any]:
    """Resolve a published local claim into a reviewable proposal, no spawn."""
    required = {
        "client_intent_id", "executor_id", "adapter_id", "candidate_ref",
        "inventory_revision", "realization_ref", "workspace_id", "alias",
    }
    allowed = required | {"agent_id_hint"}
    if (not isinstance(request, Mapping) or not required <= set(request) or
            not set(request) <= allowed):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid binding preparation fields.", {})
    for name in required:
        value = request[name]
        limit = 120 if name == "alias" else 160
        if type(value) is not str or not 1 <= len(value) <= limit:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                                  "Invalid binding preparation field.",
                                  {"field": name})
    if (request.get("agent_id_hint") is not None and
            request["agent_id_hint"] != actor_agent_id):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                              "The agent hint does not match the authenticated agent.", {})
    if any(char in request["alias"] for char in ("/", "\\", ":")):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "A binding alias must not contain a path.", {})
    server_id, revisions, projection = current_agent_revisions(
        factory, agent_id=actor_agent_id)
    body_hash = _digest(dict(request))
    with factory.unit_of_work() as uow:
        conn = uow.connection
        prior = conn.execute(
            "SELECT body_hash,proposal_json FROM execution_proposals WHERE "
            "server_id=? AND actor_agent_id=? AND client_intent_id=?",
            (server_id, actor_agent_id, request["client_intent_id"]),
        ).fetchone()
        if prior is not None:
            if prior["body_hash"] != body_hash or not prior["proposal_json"]:
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The client intent ID has different content.", {})
            return json.loads(prior["proposal_json"])
        executor = conn.execute(
            "SELECT kind,label,revoked_at FROM execution_executors WHERE "
            "server_id=? AND executor_id=?",
            (server_id, request["executor_id"]),
        ).fetchone()
        if executor is None or executor["revoked_at"] is not None:
            raise OktoNexusError(ErrorCode.NOT_FOUND,
                                  "The selected executor is unavailable.", {})
        realization = conn.execute(
            "SELECT r.*,w.workspace_id,w.revision AS workspace_revision,"
            "w.status AS workspace_status,w.realization_handle,"
            "s.display_name FROM execution_realizations r "
            "JOIN execution_workspace_bindings w ON w.server_id=r.server_id "
            "AND w.executor_id=r.executor_id AND "
            "w.workspace_binding_id=r.workspace_binding_id "
            "JOIN workspaces s ON s.workspace_id=w.workspace_id "
            "WHERE r.server_id=? AND r.executor_id=? AND r.realization_ref=? "
            "AND r.subject_agent_id=?",
            (server_id, request["executor_id"],
             request["realization_ref"], actor_agent_id),
        ).fetchone()
        if realization is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND,
                                  "The realization was not found in this scope.", {})
        if (realization["workspace_id"] != request["workspace_id"] or
                realization["candidate_ref"] != request["candidate_ref"] or
                realization["inventory_revision"] != request["inventory_revision"] or
                realization["status"] != "PENDING_APPROVAL" or
                realization["workspace_status"] != "PENDING_APPROVAL"):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The selected realization has changed.", {})
        current = conn.execute(
            "SELECT c.inventory_revision,c.publication_sequence,"
            "s.observation_age_ms,s.canonical_projection "
            "FROM execution_inventory_current c "
            "JOIN execution_inventory_snapshots s ON s.server_id=c.server_id "
            "AND s.executor_id=c.executor_id AND "
            "s.publication_sequence=c.publication_sequence "
            "WHERE c.server_id=? AND c.executor_id=?",
            (server_id, request["executor_id"]),
        ).fetchone()
        fresh = fresh_publications.get((server_id, request["executor_id"]))
        if (current is None or
                current["inventory_revision"] != request["inventory_revision"] or
                fresh is None or fresh[0] != current["publication_sequence"] or
                current["observation_age_ms"] +
                int((time.monotonic() - fresh[1]) * 1000) >= 120_000):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The selected inventory is no longer fresh.", {})
        snapshot = json.loads(current["canonical_projection"])
        if not any(
            item["adapter_id"] == request["adapter_id"] and
            item["candidate_ref"] == request["candidate_ref"]
            for item in snapshot["evidence"]
        ):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The selected candidate is not in this inventory.", {})
        legacy = conn.execute(
            "SELECT endpoint_id FROM agent_endpoints WHERE agent_id=? "
            "AND workspace_id=? AND adapter_id=? LIMIT 2",
            (actor_agent_id, request["workspace_id"],
             request["adapter_id"]),
        ).fetchall()
        blockers = (["existing_endpoint_requires_review"] if legacy else [])
        proposal_id = "prop_" + secrets.token_hex(16)
        binding_id = "bind_" + secrets.token_hex(16)
        endpoint_id = "ep_" + secrets.token_hex(16)
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(minutes=10)).isoformat()
        expected = {
            "authorization_revision": revisions.authorization,
            "configuration_revision": revisions.configuration,
            "inventory_revision": request["inventory_revision"],
            "realization_revision": realization["revision"],
            "root_proof_digest": realization["local_root_proof_digest"],
            "workspace_revision": realization["workspace_revision"],
            "workspace_status": realization["workspace_status"],
            "agent_guard_digest": _agent_guard(conn, actor_agent_id),
            "alias": request["alias"],
        }
        diff_semantic = {
            "server_id": server_id, "executor_id": request["executor_id"],
            "agent_id": actor_agent_id, "binding_id": binding_id,
            "endpoint_id": endpoint_id,
            "workspace_id": request["workspace_id"],
            "workspace_binding_id": realization["workspace_binding_id"],
            "adapter_id": request["adapter_id"],
            "candidate_ref": request["candidate_ref"],
            "realization_ref": request["realization_ref"],
            "alias": request["alias"], "expected": expected,
        }
        diff_hash = _digest(diff_semantic)
        metadata = projection["metadata"]
        agent_name = _safe_label(
            metadata.get("display_name") if isinstance(metadata, dict) else None,
            actor_agent_id)
        host_name = _safe_label(executor["label"], request["executor_id"])
        project_name = _safe_label(realization["display_name"],
                                   request["workspace_id"])
        summary = (f"Connect {agent_name} to {request['adapter_id']} "
                   f"installation {request['candidate_ref']} on {host_name} "
                   f"for {project_name} as {request['alias']}.")
        proposal = {
            "proposal_id": proposal_id, "proposal_revision": 1,
            "expires_at": expires_at, "server_id": server_id,
            "executor_id": request["executor_id"],
            "agent_id": actor_agent_id, "binding_id": binding_id,
            "endpoint_id": endpoint_id, "profile_id": None,
            "workspace_id": request["workspace_id"],
            "workspace_binding_id": realization["workspace_binding_id"],
            "adapter_id": request["adapter_id"],
            "candidate_ref": request["candidate_ref"],
            "inventory_revision": request["inventory_revision"],
            "realization_ref": request["realization_ref"],
            "realization_revision": realization["revision"],
            "authorization_revision": revisions.authorization,
            "configuration_revision": revisions.configuration,
            "required_approvals": ["agent_confirmation"],
            "diff": {
                "fields_changed": ["agent", "host", "installation",
                                   "project", "scope", "endpoint", "binding"],
                "approved_diff_hash": diff_hash,
                "requires_operator": bool(blockers),
                "summary": summary,
            },
            "can_apply": not blockers,
        }
        conn.execute(
            "INSERT INTO execution_proposals(proposal_id,server_id,"
            "client_intent_id,actor_agent_id,subject_agent_id,executor_id,"
            "binding_id,expected_revisions_json,diff_hash,expires_at,status,"
            "created_at,body_hash,proposal_revision,proposal_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,'PREPARED',?,?,1,?)",
            (proposal_id, server_id, request["client_intent_id"],
             actor_agent_id, actor_agent_id, request["executor_id"],
             binding_id, canonical_json(expected).decode("utf-8"),
             diff_hash, expires_at, now.isoformat(), body_hash,
             canonical_json(proposal).decode("utf-8")),
        )
        return proposal


def apply_execution_binding(
    factory: ConnectionFactory, *, actor_agent_id: str,
    request: Mapping[str, Any], fresh_publications: Mapping,
) -> dict[str, Any]:
    """CAS a reviewed proposal into one canonical binding, without effect."""
    required = {"client_intent_id", "proposal_id", "proposal_revision",
                "approved_diff_hash"}
    if (not isinstance(request, Mapping) or not required <= set(request) or
            not set(request) <= required | {"operator_proof_ref"} or
            any(type(request[name]) is not str or not 1 <= len(request[name]) <= 160
                for name in ("client_intent_id", "proposal_id",
                             "approved_diff_hash")) or
            type(request["proposal_revision"]) is not int or
            request["proposal_revision"] < 1 or
            (request.get("operator_proof_ref") is not None and
             (type(request["operator_proof_ref"]) is not str or
              not 1 <= len(request["operator_proof_ref"]) <= 160))):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid binding apply fields.", {})
    server_id, revisions, _ = current_agent_revisions(
        factory, agent_id=actor_agent_id)
    body_hash = _digest(dict(request))
    with factory.unit_of_work() as uow:
        conn = uow.connection
        prior = conn.execute(
            "SELECT proposal_id,apply_body_hash,applied_json FROM "
            "execution_proposals WHERE server_id=? AND actor_agent_id=? "
            "AND apply_client_intent_id=?",
            (server_id, actor_agent_id, request["client_intent_id"]),
        ).fetchone()
        if prior is not None:
            if (prior["proposal_id"] != request["proposal_id"] or
                    prior["apply_body_hash"] != body_hash or
                    not prior["applied_json"]):
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The apply intent ID has different content.", {})
            return json.loads(prior["applied_json"])
        row = conn.execute(
            "SELECT * FROM execution_proposals WHERE proposal_id=? AND "
            "server_id=? AND actor_agent_id=?",
            (request["proposal_id"], server_id, actor_agent_id),
        ).fetchone()
        if row is None or not row["proposal_json"]:
            raise OktoNexusError(ErrorCode.NOT_FOUND,
                                  "The binding proposal was not found.", {})
        if row["status"] != "PREPARED":
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The binding proposal was already applied or revoked.", {})
        proposal = json.loads(row["proposal_json"])
        expected = json.loads(row["expected_revisions_json"])
        if (row["proposal_revision"] != request["proposal_revision"] or
                row["diff_hash"] != request["approved_diff_hash"] or
                not proposal["can_apply"] or
                proposal["diff"]["requires_operator"] or
                (request.get("operator_proof_ref") is not None) or
                datetime.fromisoformat(row["expires_at"].replace(
                    "Z", "+00:00")) <= datetime.now(timezone.utc)):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The binding proposal cannot be applied.", {})
        if (revisions.authorization != expected["authorization_revision"] or
                revisions.configuration != expected["configuration_revision"] or
                _agent_guard(conn, actor_agent_id) != expected["agent_guard_digest"]):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "Agent policy or configuration changed.", {})
        executor = conn.execute(
            "SELECT revoked_at FROM execution_executors WHERE server_id=? "
            "AND executor_id=?",
            (server_id, proposal["executor_id"]),
        ).fetchone()
        realization = conn.execute(
            "SELECT r.revision,r.status,r.local_root_proof_digest,"
            "r.candidate_ref,r.inventory_revision,r.workspace_binding_id,"
            "w.revision AS workspace_revision,w.status AS workspace_status,"
            "w.workspace_id FROM execution_realizations r "
            "JOIN execution_workspace_bindings w ON w.server_id=r.server_id "
            "AND w.executor_id=r.executor_id AND "
            "w.workspace_binding_id=r.workspace_binding_id "
            "WHERE r.server_id=? AND r.executor_id=? AND r.realization_ref=? "
            "AND r.subject_agent_id=?",
            (server_id, proposal["executor_id"],
             proposal["realization_ref"], actor_agent_id),
        ).fetchone()
        if (executor is None or executor["revoked_at"] is not None or
                realization is None or
                realization["revision"] != expected["realization_revision"] or
                realization["local_root_proof_digest"] != expected["root_proof_digest"] or
                realization["workspace_revision"] != expected["workspace_revision"] or
                realization["workspace_status"] != expected["workspace_status"] or
                realization["status"] != "PENDING_APPROVAL" or
                realization["candidate_ref"] != proposal["candidate_ref"] or
                realization["inventory_revision"] != proposal["inventory_revision"] or
                realization["workspace_binding_id"] != proposal["workspace_binding_id"] or
                realization["workspace_id"] != proposal["workspace_id"]):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The selected realization has changed.", {})
        current = conn.execute(
            "SELECT c.inventory_revision,c.publication_sequence,"
            "s.observation_age_ms FROM execution_inventory_current c "
            "JOIN execution_inventory_snapshots s ON s.server_id=c.server_id "
            "AND s.executor_id=c.executor_id AND "
            "s.publication_sequence=c.publication_sequence "
            "WHERE c.server_id=? AND c.executor_id=?",
            (server_id, proposal["executor_id"]),
        ).fetchone()
        fresh = fresh_publications.get((server_id, proposal["executor_id"]))
        if (current is None or
                current["inventory_revision"] != expected["inventory_revision"] or
                fresh is None or fresh[0] != current["publication_sequence"] or
                current["observation_age_ms"] +
                int((time.monotonic() - fresh[1]) * 1000) >= 120_000):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The selected inventory is no longer fresh.", {})
        existing = conn.execute(
            "SELECT 1 FROM agent_endpoints WHERE agent_id=? AND "
            "workspace_id=? AND adapter_id=? LIMIT 1",
            (actor_agent_id, proposal["workspace_id"],
             proposal["adapter_id"]),
        ).fetchone()
        if existing is not None:
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "An endpoint was added after preparation.", {})
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,"
            "adapter_id,protocol,enabled,activation_state,public_config,"
            "created_at,updated_at) VALUES (?,?,?,?,'nxl-r4',0,'approved',?,?,?)",
            (proposal["endpoint_id"], actor_agent_id, proposal["workspace_id"],
             proposal["adapter_id"],
             canonical_json({"alias": expected["alias"]}).decode("utf-8"),
             now, now),
        )
        conn.execute(
            "UPDATE execution_workspace_bindings SET status='READY',revision=revision+1 "
            "WHERE server_id=? AND executor_id=? AND workspace_binding_id=?",
            (server_id, proposal["executor_id"],
             proposal["workspace_binding_id"]),
        )
        conn.execute(
            "UPDATE execution_realizations SET status='READY' WHERE server_id=? "
            "AND executor_id=? AND realization_ref=?",
            (server_id, proposal["executor_id"],
             proposal["realization_ref"]),
        )
        conn.execute(
            "INSERT INTO execution_bindings(server_id,binding_id,executor_id,"
            "endpoint_id,workspace_binding_id,candidate_ref,inventory_revision,"
            "realization_ref,realization_revision,binding_revision) "
            "VALUES (?,?,?,?,?,?,?,?,?,1)",
            (server_id, proposal["binding_id"], proposal["executor_id"],
             proposal["endpoint_id"], proposal["workspace_binding_id"],
             proposal["candidate_ref"], proposal["inventory_revision"],
             proposal["realization_ref"], proposal["realization_revision"]),
        )
        view = {
            "binding_id": proposal["binding_id"], "server_id": server_id,
            "executor_id": proposal["executor_id"],
            "agent_id": actor_agent_id, "endpoint_id": proposal["endpoint_id"],
            "workspace_id": proposal["workspace_id"],
            "workspace_binding_id": proposal["workspace_binding_id"],
            "adapter_id": proposal["adapter_id"],
            "candidate_ref": proposal["candidate_ref"],
            "inventory_revision": proposal["inventory_revision"],
            "realization_ref": proposal["realization_ref"],
            "realization_revision": proposal["realization_revision"],
            "binding_revision": 1,
            "authorization_revision": revisions.authorization + 1,
            "configuration_revision": revisions.configuration + 1,
            "state": "APPROVED",
        }
        conn.execute(
            "UPDATE execution_proposals SET status='APPLIED',"
            "apply_client_intent_id=?,apply_body_hash=?,applied_json=? "
            "WHERE proposal_id=? AND status='PREPARED'",
            (request["client_intent_id"], body_hash,
             canonical_json(view).decode("utf-8"), row["proposal_id"]),
        )
    # Materialize the two dimensions changed by the new endpoint for /me.
    current_agent_revisions(factory, agent_id=actor_agent_id)
    return view
