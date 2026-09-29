"""Persist executor-owned R4 realization claims without resolving remote paths.

Publication records evidence, not approval or authority to start a process.
The producing executor must retain the local root/candidate mapping and local
consent proof; the Server stores only opaque references and digests.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import secrets
from typing import Any, Mapping

from nexus_connector_core.protocol import canonical_json

from ..errors import ErrorCode, OktoNexusError
from ..adapters.outbound.sqlite.connection import ConnectionFactory
from ..adapters.outbound.sqlite.execution_tickets import VerifiedExecutionTicket


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_CANDIDATE = re.compile(r"^nexus-install-v1:[0-9a-f]{64}$")
_LOCAL_REF = re.compile(r"^root_[A-Za-z0-9_-]{16,128}$")


@dataclass(frozen=True, slots=True)
class RealizationPublication:
    server_id: str
    executor_id: str
    realization_ref: str
    local_realization_ref: str
    realization_revision: int
    agent_id: str
    workspace_id: str
    workspace_binding_id: str
    inventory_revision: str
    configuration_digest: str
    reused: bool

    def public_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id, "executor_id": self.executor_id,
            "realization_ref": self.realization_ref,
            "local_realization_ref": self.local_realization_ref,
            "realization_revision": self.realization_revision,
            "agent_id": self.agent_id, "workspace_id": self.workspace_id,
            "workspace_binding_id": self.workspace_binding_id,
            "inventory_revision": self.inventory_revision,
            "configuration_digest": self.configuration_digest,
        }


def publish_executor_realization(
    factory: ConnectionFactory, *, principal: VerifiedExecutionTicket,
    request: Mapping[str, Any],
) -> RealizationPublication:
    """Record a scoped, idempotent claim after exact inventory comparison."""
    if principal.binding_id is not None or "realization:publish" not in principal.scopes:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                              "A realization publication ticket is required.", {})
    required = {
        "client_intent_id", "agent_id", "local_realization_ref",
        "realization_revision", "workspace_id", "workspace_label",
        "adapter_id", "candidate_ref", "inventory_revision",
        "local_root_proof_digest", "configuration_digest", "local_consent_id",
    }
    if not isinstance(request, Mapping) or set(request) != required:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid realization publication fields.", {})
    for name in ("client_intent_id", "agent_id", "local_realization_ref",
                 "adapter_id", "local_consent_id"):
        value = request[name]
        if type(value) is not str or not 1 <= len(value) <= 160:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                                  "Invalid realization publication field.",
                                  {"field": name})
    if (request["agent_id"] != principal.agent_id or
            not _LOCAL_REF.fullmatch(request["local_realization_ref"]) or
            type(request["realization_revision"]) is not int or
            request["realization_revision"] < 1 or
            (request["workspace_id"] is not None and
             (type(request["workspace_id"]) is not str or
              not 1 <= len(request["workspace_id"]) <= 160)) or
            type(request["workspace_label"]) is not str or
            len(request["workspace_label"]) > 160 or
            type(request["candidate_ref"]) is not str or
            not _CANDIDATE.fullmatch(request["candidate_ref"]) or
            any(type(request[name]) is not str or
                not _DIGEST.fullmatch(request[name]) for name in (
                "inventory_revision", "local_root_proof_digest",
                "configuration_digest"))):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid realization publication scope or evidence.", {})
    if ("/" in request["workspace_label"] or
            "\\" in request["workspace_label"] or
            ":" in request["workspace_label"]):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "A workspace label must not contain a path.", {})
    body_hash = "sha256:" + hashlib.sha256(canonical_json(dict(request))).hexdigest()
    with factory.unit_of_work() as uow:
        conn = uow.connection
        old = conn.execute(
            "SELECT r.*,w.workspace_id FROM execution_realizations r "
            "JOIN execution_workspace_bindings w ON w.server_id=r.server_id "
            "AND w.executor_id=r.executor_id AND "
            "w.workspace_binding_id=r.workspace_binding_id "
            "WHERE r.server_id=? AND r.executor_id=? AND r.subject_agent_id=? "
            "AND r.client_intent_id=?",
            (principal.server_id, principal.executor_id, principal.agent_id,
             request["client_intent_id"]),
        ).fetchone()
        if old is not None:
            if old["body_hash"] != body_hash:
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The client intent ID has different content.", {})
            return RealizationPublication(
                principal.server_id, principal.executor_id,
                old["realization_ref"], old["local_realization_ref"],
                old["revision"], principal.agent_id, old["workspace_id"],
                old["workspace_binding_id"], old["inventory_revision"],
                old["configuration_digest"], True)
        current = conn.execute(
            "SELECT c.inventory_revision,s.canonical_projection FROM "
            "execution_inventory_current c JOIN execution_inventory_snapshots s "
            "ON s.server_id=c.server_id AND s.executor_id=c.executor_id "
            "AND s.publication_sequence=c.publication_sequence "
            "WHERE c.server_id=? AND c.executor_id=?",
            (principal.server_id, principal.executor_id),
        ).fetchone()
        if current is None or current["inventory_revision"] != request["inventory_revision"]:
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The selected inventory revision is stale.", {})
        snapshot = json.loads(current["canonical_projection"])
        if not any(
            evidence["adapter_id"] == request["adapter_id"] and
            evidence["candidate_ref"] == request["candidate_ref"]
            for evidence in snapshot["evidence"]
        ):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The selected candidate is not in this inventory.", {})
        duplicate = conn.execute(
            "SELECT 1 FROM execution_realizations WHERE server_id=? AND "
            "executor_id=? AND local_realization_ref=? AND revision=?",
            (principal.server_id, principal.executor_id,
             request["local_realization_ref"], request["realization_revision"]),
        ).fetchone()
        if duplicate is not None:
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The local realization revision is already registered.", {})
        workspace_id = request["workspace_id"]
        if workspace_id is None:
            workspace_id = "wsr_" + secrets.token_hex(16)
            conn.execute(
                "INSERT INTO workspaces(workspace_id,display_name,created_at) "
                "VALUES (?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
                (workspace_id, request["workspace_label"]),
            )
        elif conn.execute("SELECT 1 FROM workspaces WHERE workspace_id=?",
                          (workspace_id,)).fetchone() is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND,
                                  "The logical workspace was not found.", {})
        workspace_binding_id = "wxb_" + secrets.token_hex(16)
        realization_ref = "real_" + secrets.token_hex(16)
        handle = "root_" + secrets.token_hex(16)
        conn.execute(
            "INSERT INTO execution_workspace_bindings(server_id,"
            "workspace_binding_id,executor_id,workspace_id,realization_handle,"
            "revision,status) VALUES (?,?,?,?,?,1,'PENDING_APPROVAL')",
            (principal.server_id, workspace_binding_id, principal.executor_id,
             workspace_id, handle),
        )
        conn.execute(
            "INSERT INTO execution_realizations(server_id,executor_id,"
            "realization_ref,local_realization_ref,subject_agent_id,"
            "workspace_binding_id,candidate_ref,inventory_revision,"
            "configuration_digest,local_root_proof_digest,revision,status,"
            "client_intent_id,body_hash,local_consent_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,'PENDING_APPROVAL',?,?,?)",
            (principal.server_id, principal.executor_id, realization_ref,
             request["local_realization_ref"], principal.agent_id,
             workspace_binding_id, request["candidate_ref"],
             request["inventory_revision"], request["configuration_digest"],
             request["local_root_proof_digest"],
             request["realization_revision"], request["client_intent_id"],
             body_hash, request["local_consent_id"]),
        )
        return RealizationPublication(
            principal.server_id, principal.executor_id, realization_ref,
            request["local_realization_ref"], request["realization_revision"],
            principal.agent_id, workspace_id, workspace_binding_id,
            request["inventory_revision"], request["configuration_digest"],
            False)
