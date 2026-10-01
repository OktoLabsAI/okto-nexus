"""Project authenticated, contiguous native requests without applying decisions."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets

from nexus_connector_core import (
    R4_PREVIEW_REVISION, reduce_r4_approval_request, r4_operational_request_hash,
)
from nexus_connector_core.protocol import canonical_json

from ..adapters.outbound.harness.event_journal import redact


_SCOPE = (
    "server_id", "executor_id", "binding_id", "agent_id", "workspace_id",
    "workspace_binding_id", "session_id", "session_owner_generation",
    "authorization_revision", "configuration_revision", "binding_revision",
    "credential_epoch",
)
_TTL_SECONDS = 120
NATIVE_APPROVAL_ACTION = "execution.native.respond"


def project_native_request(conn, *, event, session, channel, received_at, uow=None, approvals=None):
    """Run only inside event ingress's transaction and contiguous prefix.

    The source operation supplies immutable authority. Payload fields cannot
    nominate another subject, binding, workspace, or owner generation.
    """
    key = tuple(event[name] for name in (
        "server_id", "executor_id", "session_id", "stream_epoch"))
    operation_id = event.get("operation_id")
    payload = event["payload"]
    if event["category"] == "turn_state" and payload.get("delivery_phase") == "terminal":
        conn.execute(
            "UPDATE execution_native_requests SET state='STALE' WHERE "
            "server_id=? AND executor_id=? AND session_id=? AND stream_epoch=? "
            "AND source_operation_id=? AND state='PENDING'", (*key, operation_id))
        return
    if event["category"] not in {"approval_request", "input_request"}:
        return
    request = payload.get("native_approval")
    display = payload.get("native_approval_display")
    if (not isinstance(request, dict) or not isinstance(display, dict) or
            len(canonical_json(request)) > 16384 or
            display.get("request_hash") != request.get("request_hash")):
        raise ValueError("The native request has no intact proposal and display.")
    native_id = request.get("request_id")
    if not ((type(native_id) is str and 1 <= len(native_id) <= 256) or
            (type(native_id) is int and 0 <= native_id <= 9007199254740991)):
        raise ValueError("The native request identifier is invalid.")
    # A native request cannot enter through the administrative schema branch.
    native_hash = request.get("request_hash")
    if (type(native_hash) is not str or len(native_hash) != 64 or
            any(c not in "0123456789abcdef" for c in native_hash)):
        raise ValueError("The native request hash is invalid.")
    operation = conn.execute(
        "SELECT * FROM execution_operations WHERE server_id=? AND executor_id=? "
        "AND session_id=? AND operation_id=?", (*key[:3], operation_id)).fetchone()
    if operation is None or operation["action"] != "turn.submit":
        raise ValueError("The native request has no admitted turn.")
    scope = json.loads(operation["expected_revisions_json"])
    if not isinstance(scope, dict) or any(name not in scope for name in _SCOPE):
        raise ValueError("The native request turn has incomplete authority.")
    expected = dict(zip(("server_id", "executor_id", "session_id"), key[:3]))
    expected.update(binding_id=session["binding_id"], agent_id=session["agent_id"],
                    workspace_id=session["workspace_id"],
                    workspace_binding_id=session["workspace_binding_id"])
    if (any(scope[name] != value for name, value in expected.items()) or
            operation["subject_agent_id"] != scope["agent_id"] or
            operation["binding_id"] != scope["binding_id"] or
            operation["workspace_id"] != scope["workspace_id"] or
            operation["workspace_binding_id"] != scope["workspace_binding_id"] or
            type(scope["session_owner_generation"]) is not int or
            not 1 <= scope["session_owner_generation"] <= session["owner_generation"]):
        raise ValueError("The native request turn is outside its session authority.")
    namespace = [*key, scope["session_owner_generation"], native_id]
    canonical_id = "r4request_" + hashlib.sha256(canonical_json(namespace)).hexdigest()
    kind = "native_input" if event["category"] == "input_request" else "native_approval"
    digest = r4_operational_request_hash(request)
    frame = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION,
                 type="approval.request", **{name: scope[name] for name in _SCOPE},
                 connection_id=channel.connection_id,
                 connection_generation=channel.connection_generation,
                 canonical_request_id=canonical_id, request_hash=digest,
                 request_revision=1, kind=kind, expires_in=_TTL_SECONDS,
                 operational_request=request)
    # Core owns native method/type classification and strict schema validation.
    reduce_r4_approval_request(None, frame)
    prior = conn.execute("SELECT * FROM execution_native_requests WHERE canonical_request_id=?",
                         (canonical_id,)).fetchone()
    if prior is not None:
        original = json.loads(prior["operational_frame_json"])
        if (prior["request_hash"] != digest or prior["kind"] != kind or
                prior["source_operation_id"] != operation_id or
                any(original[name] != scope[name] for name in _SCOPE) or
                canonical_json(original["operational_request"]) != canonical_json(request)):
            raise ValueError("The native request identifier has conflicting content.")
        return  # Replay cannot extend expiry, rewrite display, or reopen a request.
    received = datetime.fromisoformat(received_at)
    expires = received + timedelta(seconds=_TTL_SECONDS)
    stale = (scope["session_owner_generation"] != session["owner_generation"] or
             session["lifecycle_state"] != "READY")
    # A delayed request after its terminal fact is retained as non-actionable.
    terminal = conn.execute(
        "SELECT 1 FROM execution_event_ingress WHERE server_id=? AND executor_id=? "
        "AND session_id=? AND stream_epoch=? AND sequence<? AND event_type='turn_state' "
        "AND json_extract(payload_json,'$.operation_id')=? "
        "AND json_extract(payload_json,'$.payload.delivery_phase')='terminal' LIMIT 1",
        (*key, event["sequence"], operation_id)).fetchone()
    state = ("STALE" if stale or terminal else
             "EXPIRED" if expires <= datetime.now(timezone.utc) else "PENDING")
    public_display = redact(display)
    public_display["request_hash"] = native_hash  # Correlation hashes are not credentials.
    values = dict(canonical_request_id=canonical_id, server_id=key[0], executor_id=key[1],
                  session_id=key[2], stream_epoch=key[3],
                  session_owner_generation=scope["session_owner_generation"],
                  source_operation_id=operation_id, source_sequence=event["sequence"],
                  native_request_id_json=canonical_json(native_id).decode(), kind=kind,
                  request_revision=1, request_hash=digest,
                  operational_frame_json=canonical_json(frame).decode(),
                  display_json=canonical_json(public_display).decode(), state=state,
                  received_at=received_at, expires_at=expires.isoformat(),
                  cas_token=secrets.token_urlsafe(32))
    conn.execute("INSERT INTO execution_native_requests (" + ",".join(values) + ") VALUES (" +
                 ",".join("?" for _ in values) + ")", tuple(values.values()))
    if approvals is not None and state == "PENDING":
        # The canonical queue receives only a redacted presentation and the
        # immutable request reference. It must never serialize the original.
        approvals.intercept(uow, workspace_id=scope["workspace_id"], agent_id=scope["agent_id"],
            action=NATIVE_APPROVAL_ACTION, policy_id="native-runtime-permission",
            approval_id=canonical_id, kwargs={
                "approval_key": {name: frame[name] for name in (
                    "server_id", "executor_id", "binding_id", "agent_id", "workspace_id",
                    "session_id", "session_owner_generation", "canonical_request_id", "kind")},
                "request_hash": digest, "expected_revision": 1,
                "cas_token": values["cas_token"], "expires_at": values["expires_at"],
                "display": public_display})
