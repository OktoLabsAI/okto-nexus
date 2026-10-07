"""Operator CAS and durable native decision admission; no native I/O here."""
from datetime import datetime, timezone
import hashlib
import json
import secrets
import threading
import time

from nexus_connector_core import CoreError, decode_r4_frame, reduce_r4_approval_request, r4_operational_request_hash, native_input_response
from nexus_connector_core.protocol import canonical_json

from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ..adapters.outbound.sqlite.execution_leases import SqliteExecutionLeaseRepository
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError
from .execution_binding_proposals import _agent_guard
from .execution_capabilities import ExecutionCapabilityService
from .execution_leases import ExecutionChannel, require_execution_lane, _stamp
from .execution_native_requests import NATIVE_APPROVAL_ACTION, _SCOPE
from .execution_native_recipient import native_question_recipient
from .execution_input_authority import input_authority, MANAGED_INPUT_PREFIX
from .execution_semantics import execution_intent_hash


_KEY = ("server_id", "executor_id", "binding_id", "agent_id", "workspace_id",
        "session_id", "session_owner_generation", "canonical_request_id", "kind")


def _fail(message, code=ErrorCode.CONFLICT):
    raise OktoNexusError(code, message, {})


def _digest(value):
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


class NativeInputRetention:
    """Bounded producer memory. Restart intentionally loses sensitive input."""
    def __init__(self):
        self._lock = threading.Lock()
        self._values = {}

    def retain(self, reference, response, *, expires_at):
        raw = canonical_json(response)
        if len(raw) > 16384:
            _fail("The native input response exceeds its limit.", ErrorCode.VALIDATION_ERROR)
        remaining = (_stamp(expires_at) - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            _fail("The native input response has expired.")
        with self._lock:
            now = time.monotonic()
            self._values = {key: value for key, value in self._values.items() if value[0] > now}
            prior = self._values.get(reference)
            if prior is not None:
                if prior[1] != raw:
                    _fail("The retained native input has conflicting content.")
                return
            if len(self._values) >= 256:
                _fail("The native input producer is at capacity.", ErrorCode.QUOTA_EXCEEDED)
            self._values[reference] = (now + min(remaining, 120), raw)

    def resolve(self, frame):
        payload = frame["payload"]
        with self._lock:
            entry = self._values.get(payload.get("response_ref"))
            if entry is None or entry[0] <= time.monotonic():
                self._values.pop(payload.get("response_ref"), None)
                _fail("The authorized input must be explicitly supplied again.",
                      "AUTHORIZED_INPUT_UNAVAILABLE")
            raw = entry[1]
        if "sha256:" + hashlib.sha256(raw).hexdigest() != payload["response_digest"]:
            _fail("The retained native input digest does not match.")
        return json.loads(raw)

    def close(self):
        with self._lock:
            self._values.clear()


class ExecutionNativeDecisions:
    def __init__(self, *, factory, access, approvals):
        self.factory, self.access, self.approvals = factory, access, approvals
        self.inputs = NativeInputRetention()

    def _operator(self, uow, context):
        if context is None or not self.access.authenticate(context, uow=uow, require_feature=False):
            _fail("An authenticated operator must decide this native request.",
                  "APPROVAL_AUTHORITY_REQUIRED")

    def _responder(self, uow, context, row, *, recorded_guard=None):
        if context is None:
            _fail("Authentication is required.", "APPROVAL_AUTHORITY_REQUIRED")
        actor, guard, _ = input_authority(uow, factory=self.factory, access=self.access,
            context=context, action='runtime_input_respond',
            workspace_id=json.loads(row['operational_frame_json'])['workspace_id'],
            recorded_guard=recorded_guard)
        if guard.startswith(MANAGED_INPUT_PREFIX):
            native = json.loads(row['operational_frame_json'])['operational_request']
            metadata = native.get('params', {}).get('_meta')
            if row['kind'] != 'native_input' or (
                    native['method'] == 'mcpServer/elicitation/request' and isinstance(metadata, dict) and
                    metadata.get('codex_approval_kind') == 'mcp_tool_call'):
                _fail('Session tools cannot decide native execution permissions.', 'APPROVAL_AUTHORITY_REQUIRED')
        recipient = native_question_recipient(uow.connection, row)
        if not recipient or recipient != actor:
            _fail("Only this request's recipient can answer it.", "APPROVAL_AUTHORITY_REQUIRED")
        return guard

    def pending_inputs(self, *, context, workspace_id=None):
        """Return only live questions addressed to this authenticated caller."""
        from .approvals import approval_to_detail
        with self.factory.unit_of_work(write=False) as uow:
            actor, _, workspace_id = input_authority(uow, factory=self.factory, access=self.access,
                context=context, action='runtime_input_list', workspace_id=workspace_id)
            result = []
            rows = uow.connection.execute(
                "SELECT * FROM execution_native_requests WHERE kind='native_input' "
                "AND state='PENDING' ORDER BY received_at, canonical_request_id")
            for row in rows:
                if native_question_recipient(uow.connection, row) != actor:
                    continue
                frame = json.loads(row["operational_frame_json"])
                if workspace_id is not None and frame["workspace_id"] != workspace_id:
                    continue
                try:
                    self._live(uow, row, frame)
                except OktoNexusError:
                    continue
                approval = self.approvals._approvals.get(uow, row["canonical_request_id"])
                if approval is not None and approval.status == "pending":
                    detail = approval_to_detail(approval)
                    detail["request_payload"]["kwargs"]["recipient_agent_id"] = context.actor_agent_id or "operator"
                    result.append(detail)
            return result

    def confirm(self, *, context, request):
        # Freeze the submitted body before any database or producer work.
        body = self._body(request)
        with self.factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT * FROM execution_native_requests WHERE canonical_request_id=?",
                (body["approval_key"]["canonical_request_id"],)).fetchone()
            if row is None:
                _fail("The native request was not found.", ErrorCode.NOT_FOUND)
            self._responder(uow, context, row)
        current_agent_revisions(self.factory, agent_id=body["approval_key"]["agent_id"])
        result = self.approvals.decide(
            approval_id=body["approval_key"]["canonical_request_id"],
            decision="approve" if body["decision"] == "approve" else "reject",
            decided_by=context.actor_agent_id or "operator", response=body,
            decision_context=context)
        return result["executed_result"], bool(result.get("reused"))

    @staticmethod
    def _body(request):
        if not isinstance(request, dict):
            _fail("Invalid native decision request.", ErrorCode.VALIDATION_ERROR)
        required = {"client_intent_id", "approval_key", "expected_revision", "request_hash",
                    "decision", "cas_token"}
        key = request.get("approval_key")
        if (not required <= request.keys() or request.keys() - required - {"response", "operator_proof_ref"} or
                not isinstance(key, dict) or set(key) != set(_KEY) or
                any(type(key[name]) is not str or not 1 <= len(key[name]) <= 160
                    for name in _KEY if name != "session_owner_generation") or
                type(key["session_owner_generation"]) is not int or key["session_owner_generation"] < 1 or
                key["kind"] not in {"native_approval", "native_input"} or
                type(request["client_intent_id"]) is not str or not 1 <= len(request["client_intent_id"]) <= 160 or
                type(request["expected_revision"]) is not int or request["expected_revision"] < 1 or
                type(request["cas_token"]) is not str or not 16 <= len(request["cas_token"]) <= 4096 or
                type(request["request_hash"]) is not str or
                type(request["decision"]) is not str or request["decision"] not in {"approve", "deny"} or
                request.get("operator_proof_ref") is not None or
                (request.get("response") is not None and not isinstance(request["response"], dict))):
            _fail("Invalid native decision request.", ErrorCode.VALIDATION_ERROR)
        raw = canonical_json(request)
        if len(raw) > 24576:
            _fail("The native decision request exceeds its limit.", ErrorCode.VALIDATION_ERROR)
        return json.loads(raw)

    def _live(self, uow, row, frame):
        conn = uow.connection
        scope = {name: frame[name] for name in _SCOPE}
        authority, grant = ExecutionCapabilityService(factory=self.factory, access=self.access)._authority(uow, scope)
        session = conn.execute("SELECT * FROM execution_sessions WHERE server_id=? AND executor_id=? AND session_id=?",
                               tuple(scope[name] for name in ("server_id", "executor_id", "session_id"))).fetchone()
        lease = SqliteExecutionLeaseRepository().effective(uow, scope)
        now = _stamp(self.access.clock.now_iso())
        if (session is None or session["stream_epoch"] != row["stream_epoch"] or
                session["lifecycle_state"] != "READY" or session["lease_state"] != "ACTIVE" or
                _stamp(row["expires_at"]) <= now or row["state"] not in {"PENDING", "DECIDED"} or
                lease is None or lease["status"] != "ACTIVE" or lease["applied_at"] is None or
                not lease["scope_json"] or json.loads(lease["scope_json"]) != scope or
                _stamp(lease["valid_until_server"]) <= now or lease["grant_id"] != grant["grant_id"] or
                lease["connection_id"] != authority["owner_instance_id"] or
                lease["connection_generation"] != authority["generation"] or
                authority["control_state"] != "CONTROL_READY"):
            _fail("The native request no longer has a live session lease.")
        source = conn.execute("SELECT * FROM execution_operations WHERE server_id=? AND executor_id=? AND operation_id=?",
                              (scope["server_id"], scope["executor_id"], row["source_operation_id"])).fetchone()
        receipt = conn.execute("SELECT stage FROM execution_receipts WHERE server_id=? AND executor_id=? AND operation_id=? "
                               "ORDER BY receipt_revision DESC LIMIT 1",
                               (scope["server_id"], scope["executor_id"], row["source_operation_id"])).fetchone()
        if (source is None or source["action"] != "turn.submit" or
                source["subject_agent_id"] != scope["agent_id"] or
                json.loads(source["expected_revisions_json"]) != scope or
                source["admission_state"] == "RESOLVED_TERMINAL" or
                (receipt is not None and receipt["stage"] in {"SUCCEEDED", "FAILED", "CANCELLED", "UNCERTAIN"})):
            _fail("The native request turn is no longer active.")
        if authority["kind"] == "remote":
            require_execution_lane(uow, scope=scope, channel=ExecutionChannel(
                scope["server_id"], scope["executor_id"], lease["connection_id"], lease["connection_generation"]), now=now)
        self.access.authorize(RuntimeRequestContext(scope["agent_id"], "agent_key",
            credential_binding=authority["api_key_hash"], execution_grant_id=grant["grant_id"]),
            action="send", endpoint_id=authority["endpoint_id"], represented_agent_id=scope["agent_id"],
            workspace_id=scope["workspace_id"], uow=uow, audit=False, check_budget=False)
        return scope

    def decide(self, uow, approval, *, approved, response, context, decided_by, replay):
        body = self._body(response)
        if context is None:
            _fail("Authentication is required.", "APPROVAL_AUTHORITY_REQUIRED")
        if (approval.action != NATIVE_APPROVAL_ACTION or decided_by != (context.actor_agent_id or "operator") or
                approved != (body["decision"] == "approve")):
            _fail("The native decision actor or proposal does not match.")
        conn = uow.connection
        row = conn.execute("SELECT * FROM execution_native_requests WHERE canonical_request_id=?",
                           (approval.approval_id,)).fetchone()
        if row is None:
            _fail("The native request was not found.", ErrorCode.NOT_FOUND)
        actor_guard = self._responder(uow, context, row)
        frame = json.loads(row["operational_frame_json"])
        reduce_r4_approval_request(None, frame)
        if (r4_operational_request_hash(frame["operational_request"]) != row["request_hash"] or
                body["approval_key"] != {name: frame[name] for name in _KEY} or
                body["request_hash"] != row["request_hash"] or body["expected_revision"] != row["request_revision"] or
                not secrets.compare_digest(body["cas_token"], row["cas_token"] or "") or
                approval.agent_id != frame["agent_id"] or approval.workspace_id != frame["workspace_id"]):
            _fail("The native decision does not match the immutable request.")
        answer = body.get("response")
        if (answer is not None and (not approved or row["kind"] != "native_input")) or (
                approved and row["kind"] == "native_input" and answer is None):
            _fail("This native decision requires a matching input response.", ErrorCode.VALIDATION_ERROR)
        if row["kind"] == "native_input":
            try:
                native_input_response(frame["operational_request"], answer, approved=approved)
            except (ValueError, TypeError, KeyError):
                _fail("The response does not match the native question contract.", ErrorCode.VALIDATION_ERROR)
        response_digest = _digest(answer) if answer is not None else None
        semantic_body = {name: value for name, value in body.items() if name not in {"response", "operator_proof_ref"}}
        semantic_body["response_digest"] = response_digest
        body_hash = _digest(semantic_body)
        prior = conn.execute("SELECT * FROM execution_decisions WHERE server_id=? AND actor_agent_id=? AND client_intent_id=?",
                             (frame["server_id"], decided_by, body["client_intent_id"])).fetchone()
        if prior is not None:
            if not replay or prior["body_hash"] != body_hash or prior["canonical_request_id"] != approval.approval_id:
                _fail("The decision client intent has conflicting content.")
            if answer is not None:
                outbox = conn.execute("SELECT dispatch_state FROM execution_dispatch_outbox WHERE server_id=? AND executor_id=? AND operation_id=?",
                                      (prior["server_id"], prior["executor_id"], prior["native_operation_id"])).fetchone()
                if outbox is not None and outbox[0] in {"PENDING", "RESERVED"}:
                    self._live(uow, row, frame)
                    self.inputs.retain(prior["response_ref"], answer, expires_at=row["expires_at"])
            return self._view(uow, prior)
        if replay or row["state"] != "PENDING":
            _fail("The native request already has a decision or is no longer pending.")
        if conn.execute("SELECT 1 FROM execution_client_intents WHERE server_id=? AND actor_agent_id=? AND client_intent_id=?",
                        (frame["server_id"], decided_by, body["client_intent_id"])).fetchone() is not None:
            _fail("The decision client intent is already assigned to another operation.")
        scope = self._live(uow, row, frame)
        decision_id, operation_id = "r4decision_" + secrets.token_hex(16), "r4op_" + secrets.token_hex(16)
        response_ref = "r4input_" + secrets.token_hex(16) if answer is not None else None
        native_decision = "accept" if approved else "cancel" if row["kind"] == "native_input" else "decline"
        payload = dict(canonical_request_id=approval.approval_id, decision_id=decision_id,
                       decision_revision=1, decision=native_decision,
                       request=frame["operational_request"], response_digest=response_digest)
        if response_ref is not None:
            payload["response_ref"] = response_ref
        semantic = dict(action="input.provide" if row["kind"] == "native_input" else "approval.decide",
                        payload=payload, target={"kind": "none", "expected_turn_id": None})
        semantic.update({name: scope[name] for name in (
            "server_id", "executor_id", "binding_id", "agent_id", "workspace_id",
            "workspace_binding_id", "session_id", "configuration_revision")})
        # Hash the actual wire intent now, but persist only its response
        # reference. Dispatch reconstructs it from owned memory and verifies
        # this same hash before SENDING; no new secret transport is needed.
        wire_semantic = dict(semantic)
        if answer is not None:
            wire_semantic["payload"] = {name: value for name, value in payload.items() if name != "response_ref"}
            wire_semantic["payload"]["response"] = answer
        from .execution_capacity import require_admission_capacity
        byte_cost = len(canonical_json(wire_semantic))
        require_admission_capacity(conn, server_id=scope["server_id"], executor_id=scope["executor_id"],
                                   action=semantic["action"], byte_cost=byte_cost)
        if response_ref is not None:
            self.inputs.retain(response_ref, answer, expires_at=row["expires_at"])
        intent_hash = execution_intent_hash(wire_semantic)
        now = self.access.clock.now_iso()
        values = dict(decision_id=decision_id, server_id=scope["server_id"], executor_id=scope["executor_id"],
            binding_id=scope["binding_id"], agent_id=scope["agent_id"], workspace_id=scope["workspace_id"],
            session_id=scope["session_id"], session_owner_generation=scope["session_owner_generation"],
            canonical_request_id=approval.approval_id, kind=row["kind"], revision=1,
            proposal_json=row["operational_frame_json"], proposal_digest=row["request_hash"],
            actor_agent_id=decided_by, decision=native_decision, canonical_state="CONFIRMED" if approved else "DENIED",
            native_operation_id=operation_id, response_digest=response_digest, response_ref=response_ref,
            expires_at=row["expires_at"], client_intent_id=body["client_intent_id"], body_hash=body_hash,
            actor_guard_digest=actor_guard)
        conn.execute("INSERT INTO execution_decisions (" + ",".join(values) + ") VALUES (" +
                     ",".join("?" for _ in values) + ")", tuple(values.values()))
        resolved = dict(scope=scope, intent_hash=intent_hash,
                        resolution_revision=1, operation_id=operation_id, decision_id=decision_id)
        conn.execute("INSERT INTO execution_client_intents(server_id,actor_agent_id,client_intent_id,body_hash,intent_id,operation_id,"
                     "resolution_revision,resolved_json,created_at,source_guard_digest) VALUES (?,?,?,?,?,?,1,?,?,?)",
                     (scope["server_id"], decided_by, body["client_intent_id"], body_hash, "r4decisionintent_"+secrets.token_hex(16),
                      operation_id, canonical_json(resolved).decode(), now, _agent_guard(conn, scope["agent_id"])))
        operation = dict(server_id=scope["server_id"], executor_id=scope["executor_id"], operation_id=operation_id,
            subject_agent_id=scope["agent_id"], actor_agent_id=decided_by, binding_id=scope["binding_id"],
            workspace_id=scope["workspace_id"], workspace_binding_id=scope["workspace_binding_id"],
            session_id=scope["session_id"], action=semantic["action"], intent_hash=intent_hash,
            semantic_payload=canonical_json(semantic).decode(), expected_revisions_json=canonical_json(scope).decode(),
            decision_id=decision_id, delivery_id="delivery_"+secrets.token_hex(16), admission_state="ACCEPTED", created_at=now, admission_bytes=byte_cost)
        conn.execute("INSERT INTO execution_operations (" + ",".join(operation) + ") VALUES (" +
                     ",".join("?" for _ in operation) + ")", tuple(operation.values()))
        conn.execute("INSERT INTO execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state,next_attempt_at) "
                     "VALUES (?,?,?,'PENDING',?)", (scope["server_id"],scope["executor_id"],operation_id,now))
        if conn.execute("UPDATE execution_native_requests SET state='DECIDED' WHERE canonical_request_id=? AND state='PENDING' "
                        "AND cas_token=?", (approval.approval_id, body["cas_token"])).rowcount != 1:
            _fail("The native request changed during its decision.")
        return self._view(uow, values)

    @staticmethod
    def _view(uow, row):
        frame = json.loads(row["proposal_json"])
        if (_digest(frame["operational_request"]) != row["proposal_digest"] or
                any(frame[name] != row[name] for name in _KEY)):
            _fail("Stored native decision integrity validation failed.", ErrorCode.DB_ERROR)
        receipt = uow.connection.execute("SELECT * FROM execution_receipts "
            "WHERE server_id=? AND executor_id=? AND operation_id=? ORDER BY receipt_revision DESC LIMIT 1",
            (row["server_id"], row["executor_id"], row["native_operation_id"])).fetchone()
        stage = "DISPATCH_PENDING"
        if receipt is not None:
            raw = receipt["canonical_frame"]
            if not raw or "sha256:"+hashlib.sha256(raw.encode()).hexdigest() != receipt["frame_digest"]:
                _fail("Stored native receipt integrity validation failed.", ErrorCode.DB_ERROR)
            try:
                parsed = decode_r4_frame(raw.encode())
            except CoreError:
                _fail("Stored native receipt validation failed.", ErrorCode.DB_ERROR)
            operation = uow.connection.execute("SELECT intent_hash FROM execution_operations WHERE server_id=? AND executor_id=? AND operation_id=?",
                (row["server_id"], row["executor_id"], row["native_operation_id"])).fetchone()
            if (operation is None or parsed["intent_hash"] != operation[0] or
                    any(parsed[name] != frame[name] for name in ("server_id", "executor_id", "binding_id", "agent_id", "session_id")) or
                    parsed["operation_id"] != row["native_operation_id"] or
                    any(parsed[name] != receipt[name] for name in ("stage", "possible_effect", "retry_safe"))):
                _fail("The native receipt does not match its decision operation.", ErrorCode.DB_ERROR)
            stage = ("REFUSED_BEFORE_EFFECT" if receipt["stage"] in {"FAILED", "CANCELLED"} and not receipt["possible_effect"]
                     else "SUBMITTED" if receipt["stage"] in {"SUBMITTED", "SUCCEEDED"}
                     else "OUTCOME_UNKNOWN" if receipt["possible_effect"] else "DISPATCH_PENDING")
        else:
            dispatch = uow.connection.execute("SELECT dispatch_state,last_error FROM execution_dispatch_outbox "
                "WHERE server_id=? AND executor_id=? AND operation_id=?",
                (row["server_id"], row["executor_id"], row["native_operation_id"])).fetchone()
            if dispatch and dispatch["dispatch_state"] == "RESOLVED_TERMINAL" and dispatch["last_error"]:
                error = json.loads(dispatch["last_error"])
                stage = "OUTCOME_UNKNOWN" if error.get("possible_effect") else "REFUSED_BEFORE_EFFECT"
        return dict(decision_id=row["decision_id"], client_intent_id=row["client_intent_id"],
            approval_key={name: frame[name] for name in _KEY}, request_hash=row["proposal_digest"],
            request_revision=frame["request_revision"], proposal_decision="approve" if row["decision"] == "accept" else "deny",
            native_decision=row["decision"], actor_agent_id=row["actor_agent_id"], subject_agent_id=row["agent_id"],
            canonical_state=row["canonical_state"], native_operation_id=row["native_operation_id"], native_stage=stage,
            possible_effect=bool(receipt["possible_effect"]) if receipt else False,
            retry_safe=bool(receipt["retry_safe"]) if receipt else stage == "DISPATCH_PENDING",
            response_digest=row["response_digest"], expires_at=row["expires_at"])

    def read(self, *, context, decision_id):
        with self.factory.unit_of_work(write=False) as uow:
            operator = self.access.authenticate(context, uow=uow, require_feature=False)
            row = uow.connection.execute("SELECT * FROM execution_decisions WHERE decision_id=?", (decision_id,)).fetchone()
            if row is None or (not operator and context.actor_agent_id not in {row["agent_id"], row["actor_agent_id"]}):
                _fail("The native decision was not found in this credential scope.", ErrorCode.NOT_FOUND)
            return self._view(uow, row)


def validate_native_dispatch(uow, *, operation, semantic, access):
    """Revalidate a committed human decision at the RESERVED -> SENDING CAS."""
    if not access.config.feature_hitl:
        _fail("Native decision dispatch is disabled.", ErrorCode.PERMISSION_DENIED)
    conn = uow.connection
    decision = conn.execute("SELECT * FROM execution_decisions WHERE decision_id=?",
                            (operation["decision_id"],)).fetchone()
    if decision is None:
        _fail("The native operation has no canonical decision.")
    request = conn.execute("SELECT * FROM execution_native_requests WHERE canonical_request_id=?",
                           (decision["canonical_request_id"],)).fetchone()
    approval = conn.execute("SELECT * FROM approvals WHERE approval_id=?",
                            (decision["canonical_request_id"],)).fetchone()
    if (request is None or request["state"] != "DECIDED" or approval is None or
            approval["action"] != NATIVE_APPROVAL_ACTION or
            approval["status"] != ("approved" if decision["decision"] == "accept" else "rejected") or
            approval["decided_by"] != operation["actor_agent_id"] or
            decision["actor_agent_id"] != operation["actor_agent_id"] or
            decision["native_operation_id"] != operation["operation_id"] or
            decision["server_id"] != operation["server_id"] or
            decision["executor_id"] != operation["executor_id"] or
            decision["agent_id"] != operation["subject_agent_id"] or
            decision["proposal_json"] != request["operational_frame_json"] or
            decision["proposal_digest"] != request["request_hash"] or
            not decision["actor_guard_digest"]):
        _fail("The native decision authority changed before dispatch.")
    actor = access.agents.get(uow, operation["actor_agent_id"])
    checker = ExecutionNativeDecisions(factory=access.cf, access=access, approvals=None)
    managed = decision['actor_guard_digest'].startswith(MANAGED_INPUT_PREFIX)
    checker._responder(uow, RuntimeRequestContext(operation["actor_agent_id"],
        'session_capability' if managed else 'agent_key',
        credential_binding=None if managed else actor.api_key_hash if actor else None), request,
        recorded_guard=decision['actor_guard_digest'])
    frame = json.loads(decision["proposal_json"])
    reduce_r4_approval_request(None, frame)
    scope = checker._live(uow, request, frame)
    expected = dict(canonical_request_id=decision["canonical_request_id"], decision_id=decision["decision_id"],
                    decision_revision=decision["revision"], decision=decision["decision"],
                    request=frame["operational_request"], response_digest=decision["response_digest"])
    if decision["response_ref"] is not None:
        expected["response_ref"] = decision["response_ref"]
    if (canonical_json(semantic["payload"]) != canonical_json(expected) or
            semantic["action"] != ("input.provide" if decision["kind"] == "native_input" else "approval.decide") or
            json.loads(operation["expected_revisions_json"]) != scope):
        _fail("The native dispatch operation differs from its confirmed decision.")
