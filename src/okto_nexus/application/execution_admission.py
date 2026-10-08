"""Atomic R4 operation admission from a previously resolved client intent."""

from __future__ import annotations

from .executor_inventory import load_current_executor_inventory

from datetime import datetime, timezone
import json
import secrets
import time
from typing import Any, Mapping

from nexus_connector_core.protocol import canonical_json

from ..adapters.outbound.sqlite.connection import ConnectionFactory
from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ..adapters.outbound.sqlite.execution_receipts import read_execution_operation_history
from ..errors import ErrorCode, OktoNexusError
from .execution_binding_proposals import _agent_guard
from .execution_semantics import execution_intent_hash, validate_execution_target


def submit_execution_operation(
    factory: ConnectionFactory, *, actor_agent_id: str,
    request: Mapping[str, Any], fresh_publications: Mapping,
    remote_ready: bool, access=None, context=None,
) -> tuple[dict[str, Any], bool]:
    """Commit one operation, dispatch row and optional session claim before ACK.

    Readiness is supplied by the HTTP protocol gate. An existing operation is
    recoverable even if readiness subsequently drops. No executor call occurs
    inside this transaction.
    """
    required = {"client_intent_id", "operation_id", "resolution_revision",
                "intent_hash"}
    if (not isinstance(request, Mapping) or set(request) != required or
            any(type(request[name]) is not str or
                not 1 <= len(request[name]) <= 160
                for name in ("client_intent_id", "operation_id", "intent_hash")) or
            type(request["resolution_revision"]) is not int or
            request["resolution_revision"] < 1):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid operation submission.", {})
    server_id, revisions, _ = current_agent_revisions(
        factory, agent_id=actor_agent_id)
    reused = False
    executor_id = ""
    operation_id = request["operation_id"]
    with factory.unit_of_work() as uow:
        conn = uow.connection
        intent = conn.execute(
            "SELECT resolved_json,operation_id,source_guard_digest,actor_guard_digest,session_selection,reuse_admitted_at FROM "
            "execution_client_intents WHERE server_id=? AND actor_agent_id=? "
            "AND client_intent_id=? AND intent_id GLOB 'r4intent_*'",
            (server_id, actor_agent_id, request["client_intent_id"]),
        ).fetchone()
        if intent is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND,
                                  "The resolved intent was not found.", {})
        resolved = json.loads(intent["resolved_json"])
        if (intent["operation_id"] != operation_id or
                resolved["resolution_revision"] !=
                request["resolution_revision"] or
                resolved["intent_hash"] != request["intent_hash"] or
                execution_intent_hash(resolved["semantic_intent"]) !=
                request["intent_hash"]):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The operation does not match its resolution.", {})
        scope = resolved["scope"]
        subject_agent_id = scope['agent_id']
        operator_containment = (actor_agent_id != subject_agent_id and
            resolved['semantic_intent']['action'] in {'turn.interrupt', 'runtime.close'})
        from .execution_operator_authority import require_operator_request, require_recorded_operator
        require_operator_request(uow, actor=actor_agent_id, subject=subject_agent_id, access=access, context=context,
            binding_id=scope['binding_id'], action=resolved['semantic_intent']['action'])
        require_recorded_operator(uow, actor=actor_agent_id, subject=subject_agent_id,
                                  guard=intent['actor_guard_digest'], access=access)
        if subject_agent_id != actor_agent_id:
            _, revisions, _ = current_agent_revisions(factory, agent_id=subject_agent_id, uow=uow)
        connection_key_id = None
        boot_authority = None
        if context is not None and context.authentication_source == "runtime_boot":
            from .execution_boot_authority import require_boot_authority
            endpoint = conn.execute(
                "SELECT endpoint_id FROM execution_bindings WHERE server_id=? AND executor_id=? AND binding_id=?",
                (server_id, scope["executor_id"], scope["binding_id"])).fetchone()
            if resolved["semantic_intent"]["action"] != "runtime.open" or endpoint is None or access is None:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Boot authority permits opening only.", {})
            boot_authority = canonical_json(require_boot_authority(uow, access=access,
                agent_id=actor_agent_id, endpoint_id=endpoint[0], context=context)).decode()
        if context is not None and context.authentication_source == "connection_key":
            from .execution_connection_keys import require_connection_key
            endpoint = conn.execute(
                "SELECT endpoint_id FROM execution_bindings WHERE server_id=? AND executor_id=? AND binding_id=?",
                (server_id, scope["executor_id"], scope["binding_id"])).fetchone()
            if resolved["semantic_intent"]["action"] != "runtime.open" or endpoint is None or access is None:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Connection credentials authorize opening only.", {})
            connection_key_id = require_connection_key(uow, access=access,
                agent_id=actor_agent_id, endpoint_id=endpoint[0],
                key_hash=context.credential_binding)["key_id"]
        executor_id = scope["executor_id"]
        key = (server_id, executor_id, operation_id)
        prior = conn.execute(
            "SELECT operation_id,connection_key_id,boot_authority_json FROM execution_operations WHERE server_id=? "
            "AND executor_id=? AND operation_id=?", key,
        ).fetchone()
        if prior is not None and connection_key_id is not None and prior["connection_key_id"] != connection_key_id:
            raise OktoNexusError(ErrorCode.CONFLICT, "The opening belongs to a different connection credential.", {})
        if prior is not None and boot_authority is not None and prior["boot_authority_json"] != boot_authority:
            raise OktoNexusError(ErrorCode.CONFLICT, "The opening belongs to a different boot authority.", {})
        if resolved["reuse"]:
            if prior is None or intent["session_selection"] != "reuse":
                raise OktoNexusError(ErrorCode.CONFLICT, "The reused opening is unavailable.", {})
            if intent["reuse_admitted_at"] is None:
                if (not remote_ready or not resolved["can_submit"] or resolved["blockers"]
                        or datetime.fromisoformat(resolved["expires_at"]) <= datetime.now(timezone.utc)
                        or intent["source_guard_digest"] != _agent_guard(conn, subject_agent_id)):
                    raise OktoNexusError(ErrorCode.CONFLICT, "The reuse intent is no longer eligible.", {})
                from .execution_session_reuse import reusable_opening
                selected = reusable_opening(uow, factory=factory, access=access, context=context,
                    server_id=server_id, executor_id=executor_id, binding_id=scope["binding_id"],
                    session_id=scope["session_id"], payload=resolved["semantic_intent"]["payload"],
                    fresh_publications=fresh_publications)
                if selected["operation_id"] != operation_id or selected["intent_hash"] != request["intent_hash"]:
                    raise OktoNexusError(ErrorCode.CONFLICT, "The reused opening changed.", {})
                conn.execute("UPDATE execution_client_intents SET reuse_admitted_at=? WHERE server_id=? "
                    "AND actor_agent_id=? AND client_intent_id=? AND reuse_admitted_at IS NULL",
                    (datetime.now(timezone.utc).isoformat(), server_id, actor_agent_id, request["client_intent_id"]))
            reused = True
        elif prior is not None:
            reused = True
        else:
            if access is not None:
                access.require_admission(resolved["semantic_intent"]["action"])
            if (not remote_ready or not resolved["can_submit"] or
                    resolved["blockers"]):
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "This intent is not eligible for execution.", {})
            if (datetime.fromisoformat(resolved["expires_at"]) <=
                    datetime.now(timezone.utc)):
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The intent resolution has expired.", {})
            if (not intent["source_guard_digest"] or
                    intent["source_guard_digest"] !=
                    _agent_guard(conn, subject_agent_id) or
                    (not operator_containment and (scope["authorization_revision"] != revisions.authorization or
                    scope["configuration_revision"] != revisions.configuration or
                    scope["credential_epoch"] != revisions.credential_epoch))):
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The agent authority has changed.", {})
            binding = conn.execute(
                "SELECT b.*,ep.agent_id,ep.protocol,ep.adapter_id,"
                "ep.profile_id,ep.activation_state,ep.revision AS endpoint_revision,"
                "w.workspace_id,w.status AS workspace_status,"
                "r.status AS realization_status,r.revision AS current_realization_revision,"
                "e.control_state,e.revoked_at,e.registered_by_agent_id "
                "FROM execution_bindings b "
                "JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id "
                "JOIN execution_workspace_bindings w ON w.server_id=b.server_id "
                "AND w.executor_id=b.executor_id AND "
                "w.workspace_binding_id=b.workspace_binding_id "
                "JOIN execution_realizations r ON r.server_id=b.server_id "
                "AND r.executor_id=b.executor_id AND r.realization_ref=b.realization_ref "
                "JOIN execution_executors e ON e.server_id=b.server_id "
                "AND e.executor_id=b.executor_id "
                "WHERE b.server_id=? AND b.executor_id=? AND b.binding_id=?",
                (server_id, executor_id, scope["binding_id"]),
            ).fetchone()
            from .execution_agent_recovery import require_agent_ready
            require_agent_ready(conn, server_id, executor_id, subject_agent_id)
            if (binding is None or binding["agent_id"] != subject_agent_id or
                    binding["protocol"] != "nxl-r4" or
                    binding["control_state"] != "CONTROL_READY" or
                    binding["revoked_at"] is not None or
                    binding["binding_revision"] != scope["binding_revision"] or
                    binding["workspace_id"] != scope["workspace_id"] or
                    binding["workspace_binding_id"] !=
                    scope["workspace_binding_id"] or
                    binding["workspace_status"] != "READY" or
                    binding["realization_status"] != "READY" or
                    binding["realization_revision"] !=
                    binding["current_realization_revision"]):
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The execution binding is no longer ready.", {})
            action = resolved["semantic_intent"]["action"]
            validate_execution_target(binding["adapter_id"], action,
                                      resolved["semantic_intent"]["target"])
            containment = action in {"turn.interrupt", "runtime.close"}
            current = conn.execute(
                "SELECT c.inventory_revision,c.publication_sequence,"
                "s.observation_age_ms,s.canonical_projection "
                "FROM execution_inventory_current c "
                "JOIN execution_inventory_snapshots s ON s.server_id=c.server_id "
                "AND s.executor_id=c.executor_id AND "
                "s.publication_sequence=c.publication_sequence "
                "WHERE c.server_id=? AND c.executor_id=?",
                (server_id, executor_id),
            ).fetchone()
            fresh = fresh_publications.get((server_id, executor_id))
            from .execution_inventory_revalidation import accepts_binding
            if not containment and (current is None or fresh is None or
                    not accepts_binding(conn, binding, current['inventory_revision'], server_id, executor_id) or
                    fresh[0] != current["publication_sequence"] or
                    current["observation_age_ms"] +
                    max(0, int((time.monotonic() - fresh[1]) * 1000)) >= 120_000):
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The selected inventory is no longer fresh.", {})
            snapshot = (load_current_executor_inventory(current["canonical_projection"])
                        if not containment else None)
            if not containment and not any(item["adapter_id"] == binding["adapter_id"] and
                       item["candidate_ref"] == binding["candidate_ref"]
                       for item in snapshot["evidence"]):
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The selected candidate has changed.", {})
            action = resolved["semantic_intent"]["action"]
            session_id = scope["session_id"]
            if boot_authority is not None and conn.execute(
                    "SELECT 1 FROM execution_sessions WHERE server_id=? AND executor_id=? AND binding_id=? "
                    "AND lifecycle_state NOT IN ('CLOSED','FAILED') AND lease_state<>'REVOKED' LIMIT 1",
                    (server_id, executor_id, scope["binding_id"])).fetchone():
                raise OktoNexusError(ErrorCode.CONFLICT, "An existing session requires reconciliation before boot.", {})
            if action == "runtime.open" and intent["session_selection"] == "automatic":
                existing = conn.execute("SELECT 1 FROM execution_sessions WHERE server_id=? AND executor_id=? "
                    "AND binding_id=? AND lifecycle_state NOT IN ('CLOSED','FAILED') AND lease_state<>'REVOKED' LIMIT 1",
                    (server_id, executor_id, scope["binding_id"])).fetchone()
                if existing:
                    raise OktoNexusError(ErrorCode.CONFLICT, "Another session claim requires explicit selection.", {})
            if action == "runtime.open":
                from .execution_identity_owner import require_identity_host
                require_identity_host(conn, server_id=server_id,
                                      agent_id=subject_agent_id, executor_id=executor_id)
                profile = conn.execute(
                    "SELECT enabled,revision,launch_revision FROM runtime_profiles "
                    "WHERE profile_id=?", (binding["profile_id"],),
                ).fetchone() if binding["profile_id"] else None
                if (profile is None or not profile["enabled"] or
                        profile["launch_revision"] !=
                        resolved["semantic_intent"]["payload"]["profile_revision"]):
                    raise OktoNexusError(ErrorCode.CONFLICT,
                                          "The runtime profile is no longer ready.", {})
                if conn.execute(
                    "SELECT 1 FROM execution_sessions WHERE server_id=? "
                    "AND executor_id=? AND session_id=?",
                    (server_id, executor_id, session_id),
                ).fetchone() is not None:
                    raise OktoNexusError(ErrorCode.CONFLICT,
                                          "The session claim already exists.", {})
            elif action in {"turn.submit", "turn.steer", "turn.interrupt", "runtime.close"}:
                session = conn.execute(
                    "SELECT binding_id,workspace_id,workspace_binding_id,"
                    "owner_generation,lifecycle_state,lease_state "
                    "FROM execution_sessions WHERE server_id=? AND executor_id=? "
                    "AND session_id=?", (server_id, executor_id, session_id),
                ).fetchone()
                if (session is None or session["binding_id"] != scope["binding_id"] or
                        session["workspace_id"] != scope["workspace_id"] or
                        session["workspace_binding_id"] !=
                        scope["workspace_binding_id"] or
                        session["owner_generation"] !=
                        scope["session_owner_generation"] or
                        session["lifecycle_state"] != "READY" or
                        session["lease_state"] not in (
                            ('ACTIVE', 'REVOKED') if containment and actor_agent_id != subject_agent_id
                            else ('ACTIVE',))):
                    raise OktoNexusError(ErrorCode.CONFLICT,
                                          "The session is no longer ready.", {})
            else:
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                                      "Unsupported execution action.", {})
            from .execution_capacity import require_admission_capacity
            encoded_semantic = canonical_json(resolved["semantic_intent"])
            require_admission_capacity(conn, server_id=server_id, executor_id=executor_id,
                                       action=action, byte_cost=len(encoded_semantic))
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO execution_operations(server_id,executor_id,"
                "operation_id,subject_agent_id,actor_agent_id,binding_id,"
                "workspace_id,workspace_binding_id,session_id,action,intent_hash,"
                "semantic_payload,expected_revisions_json,delivery_id,"
                "admission_state,created_at,admission_bytes,connection_key_id,boot_authority_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*key, subject_agent_id, actor_agent_id, scope["binding_id"],
                 scope["workspace_id"], scope["workspace_binding_id"],
                 session_id, action, request["intent_hash"],
                 encoded_semantic.decode("utf-8"),
                 canonical_json(scope).decode("utf-8"),
                 "delivery_" + secrets.token_hex(16), "ACCEPTED", now, len(encoded_semantic), connection_key_id, boot_authority),
            )
            if action == "runtime.open":
                conn.execute(
                    "INSERT INTO execution_sessions(server_id,executor_id,"
                    "session_id,binding_id,workspace_id,workspace_binding_id,"
                    "open_operation_id,owner_generation,lifecycle_state,lease_state,metadata_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (server_id, executor_id, session_id, scope["binding_id"],
                     scope["workspace_id"], scope["workspace_binding_id"],
                     operation_id, scope["session_owner_generation"],
                     "OPEN_PENDING", "NONE", canonical_json(resolved.get('_session_metadata', {})).decode('utf-8')),
                )
            conn.execute(
                "INSERT INTO execution_dispatch_outbox(server_id,executor_id,"
                "operation_id,dispatch_state,next_attempt_at) VALUES (?,?,?,'PENDING',?)",
                (*key, now),
            )
        from .execution_initial_turns import admit_initial_turn
        admit_initial_turn(conn, server_id=server_id, actor_agent_id=actor_agent_id,
                           client_intent_id=request["client_intent_id"])
    view = read_execution_operation_history(
        factory, server_id=server_id, executor_id=executor_id,
        operation_id=operation_id, subject_agent_id=subject_agent_id,
    ).public_view()
    if actor_agent_id != subject_agent_id and view.get('result') is not None:
        from .execution_operator_authority import require_delegated_result_read
        try:
            with factory.unit_of_work(write=False) as uow:
                require_delegated_result_read(uow, operation_id=operation_id, context=context, access=access)
        except OktoNexusError as error:
            if error.code != ErrorCode.PERMISSION_DENIED:
                raise
            # Replaying a send is not an alternate result-reading authority.
            view['result'] = None
    return view, reused
