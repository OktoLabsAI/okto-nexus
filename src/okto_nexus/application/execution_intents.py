"""Durable, effect-free R4 intent resolution for a canonical agent."""

from __future__ import annotations

from .executor_inventory import load_current_executor_inventory

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
from .execution_binding_proposals import _agent_guard
from .execution_semantics import execution_intent_hash, validate_execution_target


_INTENTS = {"runtime.start": "runtime.open", "turn.submit": "turn.submit",
            "turn.steer": "turn.steer", "turn.interrupt": "turn.interrupt",
            "runtime.close": "runtime.close"}


def resolve_execution_intent(
    factory: ConnectionFactory, *, actor_agent_id: str,
    request: Mapping[str, Any], remote_ready: bool = False,
    fresh_publications: Mapping | None = None, access=None, context=None,
    session_metadata: Mapping | None = None, one_shot_slot_id: str | None = None,
) -> dict[str, Any]:
    """Store a stable resolution; never write an effect outbox or call Core."""
    required = {"client_intent_id", "intent", "binding_id",
                "workspace_binding_id"}
    allowed = required | {"agent_id", "session_id", "new_session", "text", "target"}
    if (not isinstance(request, Mapping) or not required <= set(request) or
            not set(request) <= allowed or
            any(type(request[name]) is not str or
                not 1 <= len(request[name]) <= 160 for name in required) or
            request["intent"] not in _INTENTS):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid execution intent.", {})
    if ("new_session" in request and type(request["new_session"]) is not bool):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid session selection.", {})
    if (request["intent"] == "runtime.start" and
            ((request.get("text") is not None and (type(request["text"]) is not str or not 1 <= len(request["text"]) <= 65536)) or
             (request.get("new_session") is True and request.get("session_id") is not None) or
             (request.get("session_id") is not None and
              (type(request["session_id"]) is not str or not 1 <= len(request["session_id"]) <= 160)))):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Select either a new session or an existing session with valid optional turn text.", {})
    if request["intent"] != "runtime.start" and (
            type(request.get("session_id")) is not str or
            not 1 <= len(request["session_id"]) <= 160 or
            request.get("new_session") is True):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "An existing session is required.", {})
    if request["intent"] in {"turn.submit", "turn.steer"} and (
            type(request.get("text")) is not str or
            not 1 <= len(request["text"]) <= 65536):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "A session and turn text are required.", {})
    if request["intent"] in {"turn.interrupt", "runtime.close"} and "text" in request and (
            type(request["text"]) is not str or len(request["text"]) > 1024):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "The control reason must contain at most 1024 characters.", {})
    target = request.get("target", {"kind": "none", "expected_turn_id": None})
    subject_agent_id = request.get("agent_id", actor_agent_id)
    if type(subject_agent_id) is not str or not 1 <= len(subject_agent_id) <= 160:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid represented agent.', {})
    from .execution_operator_authority import require_operator_request
    with factory.unit_of_work(write=False) as uow:
        require_operator_request(uow, actor=actor_agent_id, subject=subject_agent_id,
                                 access=access, context=context, binding_id=request['binding_id'],
                                 action=_INTENTS[request['intent']])
    server_id, revisions, _ = current_agent_revisions(
        factory, agent_id=subject_agent_id)
    hash_body = dict(request)
    if session_metadata is not None:
        if request['intent'] != 'runtime.start' or request.get('new_session') is not True:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Annotations require a new session.', {})
        from .execution_session_metadata import normalize_metadata
        session_metadata = normalize_metadata(session_metadata)
        hash_body['_session_metadata'] = session_metadata
    body_hash = "sha256:" + hashlib.sha256(canonical_json(hash_body)).hexdigest()
    with factory.unit_of_work() as uow:
        conn = uow.connection
        actor_guard = require_operator_request(uow, actor=actor_agent_id, subject=subject_agent_id,
                                               access=access, context=context, binding_id=request['binding_id'],
                                               action=_INTENTS[request['intent']])
        prior = conn.execute(
            "SELECT body_hash,resolved_json FROM execution_client_intents "
            "WHERE server_id=? AND actor_agent_id=? AND client_intent_id=?",
            (server_id, actor_agent_id, request["client_intent_id"]),
        ).fetchone()
        if prior is not None:
            if prior["body_hash"] != body_hash:
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The client intent ID has different content.", {})
            return json.loads(prior["resolved_json"])
        binding = conn.execute(
            "SELECT b.*,ep.agent_id,ep.adapter_id,ep.profile_id,ep.protocol,"
            "w.workspace_id,w.status AS workspace_status,"
            "r.status AS realization_status,"
            "r.revision AS current_realization_revision,"
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
            "WHERE b.server_id=? AND b.binding_id=? AND ep.agent_id=?",
            (server_id, request["binding_id"], subject_agent_id),
        ).fetchone()
        if (binding is None or
                binding["workspace_binding_id"] != request["workspace_binding_id"]):
            raise OktoNexusError(ErrorCode.NOT_FOUND,
                                  "The binding was not found in this agent scope.", {})
        action = _INTENTS[request["intent"]]
        from .runtime_policy import effective
        if effective(conn, subject_agent_id)['session_policy'] == 'one_shot' and action in ('runtime.open', 'turn.submit'):
            slot = conn.execute('SELECT * FROM one_shot_slots WHERE slot_id=? AND agent_id=? AND executor_id=? AND binding_id=?',
                (one_shot_slot_id, subject_agent_id, binding['executor_id'], binding['binding_id'])).fetchone()
            valid = slot is not None and (
                action == 'runtime.open' and slot['state'] == 'STARTING' and slot['session_id'] is None or
                action == 'turn.submit' and slot['state'] == 'CLAIMED' and slot['call_id'] is not None
                and slot['session_id'] == request.get('session_id'))
            if not valid:
                raise OktoNexusError(ErrorCode.CONFLICT,
                    'One-shot sessions are allocated per message or handoff within the configured capacity.', {})
        validate_execution_target(binding["adapter_id"], action, target)
        containment = action in {"turn.interrupt", "runtime.close"}
        if not containment:
            from .execution_identity_owner import require_identity_host
            require_identity_host(conn, server_id=server_id,
                                  agent_id=subject_agent_id, executor_id=binding["executor_id"])
            from .agent_execution_policy import require_execution_location
            require_execution_location(uow, agent_id=subject_agent_id,
                executor_id=binding["executor_id"], adapter_id=binding["adapter_id"])
        blockers = []
        if access is not None:
            try:
                access.require_admission(action)
            except OktoNexusError as error:
                if error.details.get("reason") != "RUNTIME_DRAINING":
                    raise
                blockers.append("runtime_draining")
        from .execution_agent_recovery import agent_recovering
        if agent_recovering(conn, server_id, binding['executor_id'], subject_agent_id):
            blockers.append('agent_recovering')
        if not remote_ready:
            blockers.append("remote_execution_unavailable")
        if (binding["protocol"] != "nxl-r4" or
                binding["control_state"] != "CONTROL_READY" or
                binding["revoked_at"] is not None):
            blockers.append("executor_not_ready")
        if (binding["workspace_status"] != "READY" or
                binding["realization_status"] != "READY" or
                binding["realization_revision"] !=
                binding["current_realization_revision"]):
            blockers.append("realization_not_ready")
        current = conn.execute(
            "SELECT c.inventory_revision,c.publication_sequence,"
            "s.observation_age_ms,s.canonical_projection "
            "FROM execution_inventory_current c "
            "JOIN execution_inventory_snapshots s ON s.server_id=c.server_id "
            "AND s.executor_id=c.executor_id AND "
            "s.publication_sequence=c.publication_sequence "
            "WHERE c.server_id=? AND c.executor_id=?",
            (server_id, binding["executor_id"]),
        ).fetchone()
        fresh = (fresh_publications or {}).get(
            (server_id, binding["executor_id"]))
        from .execution_inventory_revalidation import accepts_binding
        if not containment and (current is None or fresh is None or
                fresh[0] != current["publication_sequence"] or
                current["observation_age_ms"] +
                max(0, int((time.monotonic() - fresh[1]) * 1000)) >= 120_000):
            blockers.append("inventory_not_fresh")
        elif not containment and not accepts_binding(conn, binding, current['inventory_revision'],
                                                     server_id, binding['executor_id']):
            blockers.append("inventory_binding_review_required")
        elif not containment:
            try:
                snapshot = load_current_executor_inventory(current["canonical_projection"])
            except OktoNexusError:
                blockers.append("inventory_incompatible")
            else:
                if not any(
                    item["adapter_id"] == binding["adapter_id"] and
                    item["candidate_ref"] == binding["candidate_ref"]
                    for item in snapshot["evidence"]
                ):
                    blockers.append("candidate_not_current")
        session_id = ("ses_" + secrets.token_hex(16)
                      if action == "runtime.open" else request["session_id"])
        owner_generation = 1
        if action != "runtime.open":
            session = conn.execute(
                "SELECT binding_id,workspace_id,workspace_binding_id,"
                "owner_generation,lifecycle_state,lease_state "
                "FROM execution_sessions "
                "WHERE server_id=? AND executor_id=? AND session_id=?",
                (server_id, binding["executor_id"], session_id),
            ).fetchone()
            if (session is None or session["binding_id"] != request["binding_id"] or
                    session["workspace_id"] != binding["workspace_id"] or
                    session["workspace_binding_id"] !=
                    binding["workspace_binding_id"] or
                    session["lifecycle_state"] != "READY" or
                    session["lease_state"] not in (
                        ('ACTIVE', 'REVOKED') if containment and actor_agent_id != subject_agent_id
                        else ('ACTIVE',))):
                blockers.append("session_not_ready")
            else:
                owner_generation = session["owner_generation"]
        scope = {
            "server_id": server_id, "executor_id": binding["executor_id"],
            "binding_id": binding["binding_id"],
            "agent_id": subject_agent_id,
            "workspace_id": binding["workspace_id"],
            "workspace_binding_id": binding["workspace_binding_id"],
            "session_id": session_id,
            "session_owner_generation": owner_generation,
            "authorization_revision": revisions.authorization,
            "configuration_revision": revisions.configuration,
            "binding_revision": binding["binding_revision"],
            "credential_epoch": revisions.credential_epoch,
        }
        if containment and actor_agent_id != subject_agent_id:
            # A current operator may stop the existing authority, even after
            # its productive grant was revoked. Address the applied lease's
            # revisions rather than inventing a renewed execution context.
            from ..adapters.outbound.sqlite.execution_leases import SqliteExecutionLeaseRepository
            applied = SqliteExecutionLeaseRepository().effective(uow, scope)
            if applied is not None and applied['applied_at'] and applied['scope_json']:
                old_scope = json.loads(applied['scope_json'])
                for name in ('authorization_revision', 'configuration_revision', 'credential_epoch'):
                    scope[name] = old_scope[name]
        profile = conn.execute(
            "SELECT enabled,revision,launch_revision FROM runtime_profiles WHERE profile_id=?",
            (binding["profile_id"],),
        ).fetchone() if binding["profile_id"] else None
        payload = (
            {"adapter_id": binding["adapter_id"],
             "candidate_ref": binding["candidate_ref"],
             "inventory_revision": binding["inventory_revision"],
             "realization_ref": binding["realization_ref"],
             "realization_revision": binding["realization_revision"],
             "profile_revision": profile["launch_revision"] if profile else 1,
             "mode": "managed"}
            if action == "runtime.open" else
            {"reason": request.get("text", "Close requested by the authorized agent."),
             "drain_seconds": 30, "interrupt_seconds": 15}
            if action == "runtime.close" else
            {"reason": request.get("text", "Interrupt requested by the authorized agent.")}
            if action == "turn.interrupt" else {"text": request["text"]}
        )
        if action == 'runtime.open':
            from .runtime_mcp_presets import snapshot
            preset = snapshot(conn, binding['endpoint_id'])
            if preset['servers']:
                payload['mcp_preset'] = preset['servers']
            endpoint_config = conn.execute('SELECT public_config FROM agent_endpoints WHERE endpoint_id=?',
                                          (binding['endpoint_id'],)).fetchone()
            settings = dict(json.loads(endpoint_config[0]).get('harness_settings', {}))
            from .runtime_policy import harness_mcp_settings
            settings = harness_mcp_settings(conn, subject_agent_id, binding['adapter_id'], settings)
            model = settings.pop('model', None)
            if model is not None:
                payload['model'] = model
            if settings:
                from nexus_connector_core import validate_harness_settings
                validate_harness_settings(binding['adapter_id'], settings)
                payload['harness_settings'] = settings
        # The wire bound is UTF-8 JSON bytes, not the HTTP string's character
        # count. An oversized intent must not enter an undispatchable outbox.
        if len(canonical_json(payload)) > 65536:
            blockers.append("operation_payload_too_large")
        if action == "runtime.open" and request.get("text") is not None and len(canonical_json({"text": request["text"]})) > 65536:
            blockers.append("operation_payload_too_large")
        if action == "runtime.open" and (
                profile is None or not profile["enabled"]):
            blockers.append("profile_unresolved")
        semantic = {
            **{name: scope[name] for name in (
                "server_id", "executor_id", "binding_id", "agent_id",
                "workspace_id", "workspace_binding_id", "session_id",
                "configuration_revision")},
            "action": action, "target": dict(target), "payload": payload,
        }
        reuse = None
        if action == "runtime.open" and request.get("new_session") is not True:
            from .execution_session_reuse import reusable_opening
            reuse = reusable_opening(uow, factory=factory, access=access, context=context,
                server_id=server_id, executor_id=binding["executor_id"], binding_id=binding["binding_id"],
                session_id=request.get("session_id"), payload=payload, fresh_publications=fresh_publications)
            if reuse is not None:
                scope, semantic, session_id = reuse["scope"], reuse["semantic_intent"], reuse["session_id"]
        operation_id = "op_" + secrets.token_hex(16)
        if reuse is not None:
            operation_id = reuse["operation_id"]
        if actor_guard and actor_guard.startswith('delegated:'):
            # Native context identifies the authenticated sender; caller text
            # cannot replace the operation or represented identity.
            payload['text'] = json.dumps(dict(operation_id=operation_id,
                sender_agent_id=actor_agent_id, recipient_agent_id=subject_agent_id,
                workspace_id=scope['workspace_id'], content=[dict(type='text', text=request['text'])]))
            if len(canonical_json(payload)) > 65536 and 'operation_payload_too_large' not in blockers:
                blockers.append('operation_payload_too_large')
        intent_id = "r4intent_" + secrets.token_hex(16)
        resolved = {
            "client_intent_id": request["client_intent_id"],
            "intent_id": intent_id, "operation_id": operation_id,
            "session_id": session_id, "reuse": reuse is not None,
            "scope": scope, "semantic_intent": semantic,
            "intent_hash": execution_intent_hash(semantic),
            "resolution_revision": 1,
            "expires_at": (datetime.now(timezone.utc) +
                           timedelta(minutes=10)).isoformat(),
            "can_submit": not blockers, "blockers": blockers,
            "dispatch_owner": "server",
        }
        if session_metadata is not None:
            resolved['_session_metadata'] = session_metadata
        conn.execute(
            "INSERT INTO execution_client_intents(server_id,actor_agent_id,"
            "client_intent_id,body_hash,intent_id,operation_id,"
            "resolution_revision,resolved_json,created_at,source_guard_digest,session_selection,actor_guard_digest) "
            "VALUES (?,?,?,?,?,?,1,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'),?,?,?)",
            (server_id, actor_agent_id, request["client_intent_id"],
             body_hash, intent_id, operation_id,
             canonical_json(resolved).decode("utf-8"),
             _agent_guard(conn, subject_agent_id), "reuse" if reuse is not None else
             "automatic" if action == "runtime.open" and request.get("new_session") is not True else "explicit", actor_guard),
        )
        if action == "runtime.open" and request.get("text") is not None:
            from .execution_initial_turns import plan_initial_turn
            plan_initial_turn(conn, resolved=resolved, text=request["text"], actor_agent_id=actor_agent_id)
        return resolved


def read_execution_intent(factory: ConnectionFactory, *, actor_agent_id: str,
                          client_intent_id: str, access=None, context=None) -> dict[str, Any]:
    """Recover the original resolution; never resolve a missing intent."""
    if not isinstance(client_intent_id, str) or not 1 <= len(client_intent_id) <= 160:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid client intent ID.", {})
    server_id, _, _ = current_agent_revisions(factory, agent_id=actor_agent_id)
    with factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            "SELECT resolved_json FROM execution_client_intents WHERE "
            "server_id=? AND actor_agent_id=? AND client_intent_id=? "
            "AND intent_id GLOB 'r4intent_*'",
            (server_id, actor_agent_id, client_intent_id),
        ).fetchone()
    if row is None:
        raise OktoNexusError(ErrorCode.NOT_FOUND,
                              "The client intent was not found.", {})
    resolution = json.loads(row["resolved_json"])
    resolution.pop('_session_metadata', None)
    subject = resolution['scope']['agent_id']
    from .execution_operator_authority import require_operator_request
    with factory.unit_of_work(write=False) as uow:
        require_operator_request(uow, actor=actor_agent_id, subject=subject,
                                 access=access, context=context, require_feature=False,
                                 binding_id=resolution['scope']['binding_id'],
                                 action=resolution['semantic_intent']['action'])
        from .execution_operator_authority import require_delegated_result_read
        require_delegated_result_read(uow, operation_id=resolution['operation_id'], context=context, access=access)
    from ..adapters.outbound.sqlite.execution_receipts import (
        read_execution_operation_history,
    )
    try:
        operation = read_execution_operation_history(
            factory, server_id=server_id,
            executor_id=resolution["scope"]["executor_id"],
            operation_id=resolution["operation_id"],
            subject_agent_id=subject, actor_agent_id=actor_agent_id,
        ).public_view()
    except OktoNexusError as exc:
        if exc.code != ErrorCode.NOT_FOUND:
            raise
        operation = None
    return {"resolution": resolution, "operation": operation}
