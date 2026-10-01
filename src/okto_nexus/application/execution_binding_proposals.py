"""Prepare R4 bindings as durable, effect-free scoped proposals."""

from __future__ import annotations

from .executor_inventory import load_current_executor_inventory

from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
import time
from typing import Any, Mapping

from nexus_connector_core.protocol import canonical_json
from nexus_connector_core.catalog import get_runtime_catalog

from ..errors import ErrorCode, OktoNexusError
from ..adapters.outbound.sqlite.endpoints_repo import SqliteEndpointRepo
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
def _binding_operator(uow, *, actor_agent_id, context, access) -> bool:
    """Revalidate middleware authority inside the binding transaction."""
    if context is None and access is None:
        # Internal compatibility callers can only create disabled bindings.
        return False
    if context is None or access is None or context.actor_agent_id != actor_agent_id:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                              "The binding principal is invalid.", {})
    operator = access.authenticate(context, uow=uow, require_feature=False)
    if operator:
        access.authorize(context, uow=uow, audit=False)
    return operator


def _require_binding_method(conn, *, subject_agent_id, adapter_id):
    denied = conn.execute(
        "SELECT 1 FROM agent_connection_methods WHERE agent_id=? AND method=? "
        "AND enabled=0", (subject_agent_id, adapter_id),
    ).fetchone()
    if denied:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                              "Connection method is disabled for this agent.", {})


def _binding_alias_conflicts(conn, *, server_id, subject_agent_id, executor_id,
                             workspace_id, adapter_id, alias):
    """Canonical aliases are scoped to an agent, executor and workspace."""
    return conn.execute(
        "SELECT ep.endpoint_id FROM agent_endpoints ep LEFT JOIN execution_bindings b "
        "ON b.endpoint_id=ep.endpoint_id WHERE ep.agent_id=? AND ep.workspace_id=? "
        "AND ((b.binding_id IS NULL AND ep.adapter_id=?) OR "
        "(b.server_id=? AND b.executor_id=? AND "
        "CASE WHEN json_valid(ep.public_config) THEN json_extract(ep.public_config,'$.alias') END=?)) "
        "LIMIT 2",
        (subject_agent_id, workspace_id, adapter_id, server_id, executor_id, alias),
    ).fetchall()


def prepare_execution_binding(
    factory: ConnectionFactory, *, actor_agent_id: str,
    request: Mapping[str, Any], fresh_publications: Mapping,
    context=None, access=None, approvals=None,
) -> dict[str, Any]:
    """Resolve a published local claim into a reviewable proposal, no spawn."""
    required = {
        "client_intent_id", "executor_id", "adapter_id", "candidate_ref",
        "inventory_revision", "realization_ref", "workspace_id", "alias",
    }
    allowed = required | {"agent_id_hint", "replace_binding_id", "adopt_endpoint_id"}
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
    if request.get("replace_binding_id") is not None and (
            type(request["replace_binding_id"]) is not str or not 1 <= len(request["replace_binding_id"]) <= 160):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid replacement binding ID.", {})
    if request.get("adopt_endpoint_id") is not None and (
            type(request["adopt_endpoint_id"]) is not str or not 1 <= len(request["adopt_endpoint_id"]) <= 160
            or request.get("replace_binding_id") is not None):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "Invalid endpoint adoption request.", {})
    subject_agent_id = request.get("agent_id_hint") or actor_agent_id
    if type(subject_agent_id) is not str or not 1 <= len(subject_agent_id) <= 160:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid binding subject.", {})
    with factory.unit_of_work(write=False) as uow:
        operator = _binding_operator(uow, actor_agent_id=actor_agent_id,
                                     context=context, access=access)
        if subject_agent_id != actor_agent_id and not operator:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                  "The agent hint does not match the authenticated agent.", {})
    if any(char in request["alias"] for char in ("/", "\\", ":")):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "A binding alias must not contain a path.", {})
    server_id, revisions, projection = current_agent_revisions(
        factory, agent_id=subject_agent_id)
    body_hash = _digest(dict(request))
    with factory.unit_of_work() as uow:
        conn = uow.connection
        operator = _binding_operator(uow, actor_agent_id=actor_agent_id,
                                     context=context, access=access)
        if subject_agent_id != actor_agent_id and not operator:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                  "Only an operator may represent another agent.", {})
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
             request["realization_ref"], subject_agent_id),
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
        snapshot = load_current_executor_inventory(current["canonical_projection"])
        if not any(
            item["adapter_id"] == request["adapter_id"] and
            item["candidate_ref"] == request["candidate_ref"]
            for item in snapshot["evidence"]
        ):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The selected candidate is not in this inventory.", {})
        legacy = _binding_alias_conflicts(conn, server_id=server_id,
            subject_agent_id=subject_agent_id, executor_id=request["executor_id"],
            workspace_id=request["workspace_id"], adapter_id=request["adapter_id"],
            alias=request["alias"])
        replacement = None
        if request.get("replace_binding_id") is not None:
            from .execution_binding_replacement import replacement_target
            replacement = replacement_target(conn, server_id=server_id, subject_agent_id=subject_agent_id,
                executor_id=request["executor_id"], workspace_id=request["workspace_id"],
                adapter_id=request["adapter_id"], alias=request["alias"],
                binding_id=request["replace_binding_id"])
            legacy = [row for row in legacy if row["endpoint_id"] != replacement["endpoint_id"]]
        adoption = None
        if request.get("adopt_endpoint_id") is not None:
            if not operator:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Endpoint migration requires an operator.", {})
            from .execution_binding_migration import migration_target
            adoption = migration_target(conn, server_id=server_id, executor_id=request["executor_id"],
                subject_agent_id=subject_agent_id, workspace_id=request["workspace_id"],
                adapter_id=request["adapter_id"], endpoint_id=request["adopt_endpoint_id"])
            legacy = [item for item in legacy if item["endpoint_id"] != adoption["endpoint_id"]]
        blockers = (["existing_endpoint_requires_review"] if legacy else [])

        request_operator_proof = bool(
            not operator and access is not None and
            access.config.feature_harness_integrations)
        if request_operator_proof and approvals is None:
            raise OktoNexusError(ErrorCode.INTERNAL_ERROR,
                                  "Binding approval is not available.", {})
        enable_requested = operator or request_operator_proof
        if replacement is not None and not enable_requested:
            blockers.append("replacement_requires_operator")
        if enable_requested:
            _require_binding_method(conn, subject_agent_id=subject_agent_id,
                                    adapter_id=request["adapter_id"])
        descriptor = next((item for item in get_runtime_catalog().runtimes
                           if item.adapter_id == request["adapter_id"]), None)
        if descriptor is None:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                                  "The selected adapter is not supported.", {})
        profile_id = ("profile_" + secrets.token_hex(16)
                      if enable_requested and descriptor.connection_mode == "managed" else None)
        if (enable_requested and descriptor.connection_mode == "attach" and
                not access.config.feature_harness_attach):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                  "Attach connections are disabled.", {})
        approval_id = ("apr_" + secrets.token_hex(16)
                       if request_operator_proof and not blockers else None)
        proposal_id = "prop_" + secrets.token_hex(16)
        binding_id = "bind_" + secrets.token_hex(16)
        endpoint_id = "ep_" + secrets.token_hex(16)
        if adoption is not None:
            endpoint_id = adoption["endpoint_id"]
        if replacement is not None:
            binding_id, endpoint_id, profile_id = (replacement["binding_id"],
                replacement["endpoint_id"], replacement["profile_id"])
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
            "agent_guard_digest": _agent_guard(conn, subject_agent_id),
            "operator_approved": operator,
            "operator_approval_id": approval_id,
            "operator_guard_digest": _agent_guard(conn, actor_agent_id) if operator else None,
            "configuration_digest": realization["configuration_digest"],
            "alias": request["alias"],
        }
        if replacement is not None:
            expected["replacement"] = replacement
        if adoption is not None:
            expected["migration_adoption"] = adoption
        diff_semantic = {
            "server_id": server_id, "executor_id": request["executor_id"],
            "agent_id": subject_agent_id, "binding_id": binding_id,
            "endpoint_id": endpoint_id, "profile_id": profile_id,
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
            subject_agent_id)
        host_name = _safe_label(executor["label"], request["executor_id"])
        project_name = _safe_label(realization["display_name"],
                                   request["workspace_id"])
        summary = (f"Connect {agent_name} to {request['adapter_id']} "
                   f"installation {request['candidate_ref']} on {host_name} "
                   f"for {project_name} as {request['alias']}.")
        if replacement is not None:
            summary = (f"Replace binding {binding_id} revision {replacement['binding_revision']} "
                       f"from realization {replacement['realization_ref']} to {request['realization_ref']}. "
                       "Preserve the agent, endpoint and profile. " + summary)
        if adoption is not None:
            summary = (f"Adopt legacy endpoint {endpoint_id} revision {adoption['revision']}. "
                       f"Preserve enabled={bool(adoption['enabled'])} and activation_state={adoption['activation_state']}. "
                       "Retain the legacy profile and use the newly approved realization configuration. " + summary)
        if enable_requested and replacement is None and adoption is None:
            summary += (" Enable the approved endpoint and its managed profile."
                        if profile_id else " Enable the approved attach endpoint.")
            summary += " Execution still requires a separate scoped grant."
        proposal = {
            "proposal_id": proposal_id, "proposal_revision": 1,
            "expires_at": expires_at, "server_id": server_id,
            "executor_id": request["executor_id"],
            "agent_id": subject_agent_id, "binding_id": binding_id,
            "endpoint_id": endpoint_id, "profile_id": profile_id,
            "workspace_id": request["workspace_id"],
            "workspace_binding_id": realization["workspace_binding_id"],
            "adapter_id": request["adapter_id"],
            "candidate_ref": request["candidate_ref"],
            "inventory_revision": request["inventory_revision"],
            "realization_ref": request["realization_ref"],
            "realization_revision": realization["revision"],
            "authorization_revision": revisions.authorization,
            "configuration_revision": revisions.configuration,
            "required_approvals": ["operator_confirmation" if operator else "agent_confirmation"] + ([approval_id] if approval_id else []),
            "diff": {
                "fields_changed": (["adapter", "protocol", "profile", "public_config", "binding", "workspace_binding", "endpoint_revision"] if adoption else
                    ["realization", "installation", "workspace_binding", "binding_revision"] if replacement else
                    ["agent", "host", "installation", "project", "scope", "endpoint", "binding"] +
                    (["profile", "enabled"] if enable_requested else [])),
                "approved_diff_hash": diff_hash,
                "requires_operator": enable_requested or bool(blockers),
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
             actor_agent_id, subject_agent_id, request["executor_id"],
             binding_id, canonical_json(expected).decode("utf-8"),
             diff_hash, expires_at, now.isoformat(), body_hash,
             canonical_json(proposal).decode("utf-8")),
        )
        if approval_id:
            from .execution_binding_approvals import BINDING_APPROVAL_ACTION
            approvals.intercept(
                uow, workspace_id=proposal["workspace_id"],
                agent_id=subject_agent_id, action=BINDING_APPROVAL_ACTION,
                policy_id="execution.binding.operator-required",
                approval_id=approval_id,
                kwargs={"proposal_id": proposal_id, "server_id": server_id,
                        "proposal_revision": 1, "approved_diff_hash": diff_hash,
                        "summary": summary},
            )
        return proposal


def apply_execution_binding(
    factory: ConnectionFactory, *, actor_agent_id: str,
    request: Mapping[str, Any], fresh_publications: Mapping,
    context=None, access=None,
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
    with factory.unit_of_work(write=False) as uow:
        _binding_operator(uow, actor_agent_id=actor_agent_id,
                          context=context, access=access)
        scoped = uow.connection.execute(
            "SELECT subject_agent_id FROM execution_proposals WHERE proposal_id=? "
            "AND server_id=? AND actor_agent_id=?",
            (request["proposal_id"], server_id, actor_agent_id),
        ).fetchone()
        if scoped is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND,
                                  "The binding proposal was not found.", {})
        subject_agent_id = scoped["subject_agent_id"]
    server_id, revisions, _ = current_agent_revisions(
        factory, agent_id=subject_agent_id)
    body_hash = _digest(dict(request))
    with factory.unit_of_work() as uow:
        conn = uow.connection
        operator = _binding_operator(uow, actor_agent_id=actor_agent_id,
                                     context=context, access=access)
        if subject_agent_id != actor_agent_id and not operator:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                  "Only an operator may represent another agent.", {})
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
                (proposal["diff"]["requires_operator"] and not operator and
                 not expected.get("operator_approval_id")) or
                (request.get("operator_proof_ref") is not None and
                 not expected.get("operator_approval_id")) or
                datetime.fromisoformat(row["expires_at"].replace(
                    "Z", "+00:00")) <= datetime.now(timezone.utc)):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The binding proposal cannot be applied.", {})
        operator_approved = expected.get("operator_approved", False)
        if operator_approved and (not operator or
                _agent_guard(conn, actor_agent_id) != expected["operator_guard_digest"]):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                  "Operator authority changed after preparation.", {})
        if (revisions.authorization != expected["authorization_revision"] or
                revisions.configuration != expected["configuration_revision"] or
                _agent_guard(conn, subject_agent_id) != expected["agent_guard_digest"]):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "Agent policy or configuration changed.", {})
        if expected.get("operator_approval_id"):
            from .execution_binding_approvals import verify_binding_operator_proof
            verify_binding_operator_proof(
                conn, proposal_row=row, expected=expected,
                proof_ref=request.get("operator_proof_ref"))
            # Delegated proof approves this immutable diff, never an actor
            # change or a runtime grant. Apply still belongs to the agent.
            operator_approved = True
        if operator_approved:
            if access is None or not access.config.feature_harness_integrations:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                      "Harness integrations are disabled.", {})
            _require_binding_method(conn, subject_agent_id=subject_agent_id,
                                    adapter_id=proposal["adapter_id"])
        executor = conn.execute(
            "SELECT revoked_at FROM execution_executors WHERE server_id=? "
            "AND executor_id=?",
            (server_id, proposal["executor_id"]),
        ).fetchone()
        realization = conn.execute(
            "SELECT r.revision,r.status,r.local_root_proof_digest,r.configuration_digest,"
            "r.candidate_ref,r.inventory_revision,r.workspace_binding_id,"
            "w.revision AS workspace_revision,w.status AS workspace_status,"
            "w.workspace_id FROM execution_realizations r "
            "JOIN execution_workspace_bindings w ON w.server_id=r.server_id "
            "AND w.executor_id=r.executor_id AND "
            "w.workspace_binding_id=r.workspace_binding_id "
            "WHERE r.server_id=? AND r.executor_id=? AND r.realization_ref=? "
            "AND r.subject_agent_id=?",
            (server_id, proposal["executor_id"],
             proposal["realization_ref"], subject_agent_id),
        ).fetchone()
        if (executor is None or executor["revoked_at"] is not None or
                realization is None or
                realization["revision"] != expected["realization_revision"] or
                ("configuration_digest" in expected and
                 realization["configuration_digest"] != expected["configuration_digest"]) or
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
        existing = _binding_alias_conflicts(conn, server_id=server_id,
            subject_agent_id=subject_agent_id, executor_id=proposal["executor_id"],
            workspace_id=proposal["workspace_id"], adapter_id=proposal["adapter_id"],
            alias=expected["alias"])
        replacement = expected.get("replacement")
        if replacement is not None:
            from .execution_binding_replacement import replacement_target
            actual = replacement_target(conn, server_id=server_id, subject_agent_id=subject_agent_id,
                executor_id=proposal["executor_id"], workspace_id=proposal["workspace_id"],
                adapter_id=proposal["adapter_id"], alias=expected["alias"], binding_id=proposal["binding_id"])
            if actual != replacement or not operator_approved:
                raise OktoNexusError(ErrorCode.CONFLICT, "The replacement binding changed after review.", {})
            existing = [item for item in existing if item["endpoint_id"] != replacement["endpoint_id"]]
        adoption = expected.get("migration_adoption")
        if adoption is not None:
            from .execution_binding_migration import migration_target
            actual = migration_target(conn, server_id=server_id, executor_id=proposal["executor_id"],
                subject_agent_id=subject_agent_id, workspace_id=proposal["workspace_id"],
                adapter_id=proposal["adapter_id"], endpoint_id=proposal["endpoint_id"])
            if actual != adoption or not operator_approved:
                raise OktoNexusError(ErrorCode.CONFLICT, "The migrated endpoint changed after review.", {})
            existing = [item for item in existing if item["endpoint_id"] != adoption["endpoint_id"]]
        if existing:
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The binding alias is already in use in this executor and workspace.", {})
        now = datetime.now(timezone.utc).isoformat()
        profile_id = proposal["profile_id"] if operator_approved else None
        if replacement is None:
            endpoint_repo = SqliteEndpointRepo()
            if profile_id:
                # Technical configuration remains in the approved realization on
                # the executor. No remote command, path or secret is resolved here.
                endpoint_repo.put_profile(
                    uow, profile_id=profile_id, adapter_id=proposal["adapter_id"],
                    config={}, secret_refs={}, inherit_ambient=False,
                    enabled=True, now=now)
                endpoint_repo.audit_configuration(
                    uow, context=context, kind="profile", resource_id=profile_id,
                    old_revision=None, new_revision=1,
                    fields=["enabled", "config"], now=now)
            if adoption is not None:
                from .execution_binding_migration import apply_migration
                apply_migration(conn, proposal=proposal, expected=adoption,
                                profile_id=profile_id, alias=expected["alias"], now=now)
            else:
                conn.execute(
                    "INSERT INTO agent_endpoints(endpoint_id,agent_id,workspace_id,"
                    "adapter_id,protocol,profile_id,enabled,activation_state,public_config,"
                    "created_at,updated_at) VALUES (?,?,?,?,'nxl-r4',?,?,'approved',?,?,?)",
                    (proposal["endpoint_id"], subject_agent_id, proposal["workspace_id"],
                     proposal["adapter_id"], profile_id, int(operator_approved),
                     canonical_json({"alias": expected["alias"]}).decode("utf-8"),
                     now, now),
                )
            if context is not None:
                endpoint_repo.audit_configuration(
                    uow, context=context, kind="endpoint",
                    resource_id=proposal["endpoint_id"], old_revision=adoption["revision"] if adoption else None,
                    new_revision=adoption["revision"]+1 if adoption else 1,
                    fields=["adapter_id", "protocol", "profile_id", "public_config"] if adoption else ["enabled", "profile_id", "public_config"],
                    now=now)
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
        if replacement is not None:
            from .execution_binding_replacement import apply_replacement
            apply_replacement(conn, proposal=proposal, expected=replacement)
        else:
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
            "agent_id": subject_agent_id, "endpoint_id": proposal["endpoint_id"],
            "workspace_id": proposal["workspace_id"],
            "workspace_binding_id": proposal["workspace_binding_id"],
            "adapter_id": proposal["adapter_id"],
            "candidate_ref": proposal["candidate_ref"],
            "inventory_revision": proposal["inventory_revision"],
            "realization_ref": proposal["realization_ref"],
            "realization_revision": proposal["realization_revision"],
            "binding_revision": replacement["binding_revision"] + 1 if replacement else 1,
            "authorization_revision": revisions.authorization + int(replacement is None),
            "configuration_revision": revisions.configuration + int(replacement is None),
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
    current_agent_revisions(factory, agent_id=subject_agent_id)
    return view
