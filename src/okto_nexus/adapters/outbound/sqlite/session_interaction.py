"""Durable acceptance of input before it becomes a canonical R4 operation.

Callers must hold a write unit of work and independently prove interactive
authority. This storage layer never wakes a worker or writes to a harness.
"""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from sqlite3 import Connection
from uuid import uuid4

from nexus_connector_core import CapacityConsumption, CapacityReservation
from nexus_connector_core.frame_codec_r4 import MAX_OPERATION_PAYLOAD_BYTES
from nexus_connector_core.protocol import canonical_json

from ....application.capacity_admission import CapacityAdmission
from ....domain.attention import digest
from ....domain.session_interaction import (
    InputAuthor,
    InputDeliveryState,
    InputScope,
    QueuedReceipt,
    validate_input_text,
)
from ....errors import ErrorCode, OktoNexusError
from .connection import SqliteUnitOfWork

MAX_PENDING = 50
PENDING_LIFETIME = timedelta(hours=24)
_PENDING_STATES = """'QUEUED', 'DISPATCHING', 'REFUSED_BEFORE_SEND', 'DELIVERY_UNKNOWN',
                     'BLOCKED_AUTH', 'BLOCKED_SESSION', 'PAUSED'"""


@dataclass(frozen=True, slots=True)
class PendingInput:
    input_id: str
    input_revision: int
    author: InputAuthor
    capability_revision: str
    text: str
    source_grant: tuple[str, int] | None


def _conflict(reason: str, message: str) -> OktoNexusError:
    return OktoNexusError(ErrorCode.CONFLICT, message, {"reason": reason})


def _scope_params(scope: InputScope) -> dict[str, str | int]:
    return {
        **asdict(scope.session), "owner_generation": scope.generation.value, "binding_id": scope.binding_id,
        "workspace_id": scope.workspace_id, "workspace_binding_id": scope.workspace_binding_id,
        "agent_id": scope.agent_id,
    }


def _current_session(conn: Connection, params: dict, *, require_active_lease: bool = False) -> bool:
    return conn.execute("""
        SELECT 1 FROM execution_sessions s
        JOIN execution_bindings b
          ON b.server_id=s.server_id AND b.executor_id=s.executor_id AND b.binding_id=s.binding_id
        JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id
        JOIN execution_workspace_bindings w
          ON w.server_id=s.server_id AND w.executor_id=s.executor_id
          AND w.workspace_binding_id=s.workspace_binding_id AND w.workspace_id=s.workspace_id
        WHERE s.server_id=:server_id AND s.executor_id=:executor_id AND s.session_id=:session_id
          AND s.binding_id=:binding_id AND s.workspace_id=:workspace_id
          AND s.workspace_binding_id=:workspace_binding_id AND s.owner_generation=:owner_generation
          AND b.workspace_binding_id=:workspace_binding_id AND e.agent_id=:agent_id AND e.workspace_id=:workspace_id
          AND s.lifecycle_state='READY' AND (NOT :require_active_lease OR s.lease_state='ACTIVE')
    """, {**params, "require_active_lease": require_active_lease}).fetchone() is not None


def accept_input(
    uow: SqliteUnitOfWork,
    *,
    scope: InputScope,
    author: InputAuthor,
    client_intent_id: str,
    capability_revision: str,
    text: str,
    now: datetime,
    verify_new_authority: Callable[[], tuple[str, int] | None],
) -> QueuedReceipt:
    """Allocate a FIFO sequence and persist one input in the caller's transaction.

    Publish the returned receipt only after the write unit of work commits.
    Exact-scope validation here is additional to the caller's authorization.
    """
    validate_input_text(text)
    if len(canonical_json({"text": text})) > MAX_OPERATION_PAYLOAD_BYTES:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, "The encoded message exceeds the runtime limit.",
                             {"reason": "INPUT_PAYLOAD_TOO_LARGE"})
    if now.utcoffset() is None:
        raise ValueError("Server time must be timezone-aware.")
    now = now.astimezone(UTC)
    fingerprint = digest({"scope": asdict(scope), "mode": "next_turn", "text": text})
    params = {
        **_scope_params(scope), "authority_ref": author.authority_ref, "client_intent_id": client_intent_id,
    }
    uow.require_active_writer()
    connection = uow.connection
    retained = connection.execute("""
        SELECT i.input_id, i.fingerprint, i.enqueue_sequence, i.input_revision, q.revision,
               i.status, i.operation_id, i.possible_effect
        FROM session_interaction_inputs i
        JOIN session_interaction_queues q USING (server_id, executor_id, session_id)
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
          AND authority_ref=:authority_ref AND client_intent_id=:client_intent_id
    """, params).fetchone()
    if retained is not None:
        if retained["fingerprint"] != fingerprint:
            raise _conflict("INPUT_INTENT_CHANGED", "This input ID already identifies a different intent.")
        return QueuedReceipt(
            retained["input_id"], retained["enqueue_sequence"], retained["input_revision"],
            retained["revision"], InputDeliveryState(retained["status"]), retained["operation_id"],
            bool(retained["possible_effect"]),
        )

    if not _current_session(connection, params):
        raise _conflict("INPUT_SESSION_CHANGED", "This exact session is unavailable. Reopen it to inspect its current scope.")
    source_grant = verify_new_authority()
    grant_id, grant_revision = source_grant if source_grant is not None else (None, None)
    pending = connection.execute(f"""
        SELECT count(*) FROM session_interaction_inputs
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
          AND status IN ({_PENDING_STATES})
    """, params).fetchone()[0]
    if pending >= MAX_PENDING:
        raise _conflict("INPUT_QUEUE_FULL", "This session has reached its pending input limit.")

    sequence, revision = connection.execute("""
        INSERT INTO session_interaction_queues
            (server_id, executor_id, session_id, next_sequence, revision)
        VALUES (:server_id, :executor_id, :session_id, 2, 1)
        ON CONFLICT (server_id, executor_id, session_id) DO UPDATE SET
            next_sequence=next_sequence+1, revision=revision+1
        RETURNING next_sequence-1, revision
    """, params).fetchone()
    input_id = "sin_" + uuid4().hex
    connection.execute("""
        INSERT INTO session_interaction_inputs (
            server_id, executor_id, session_id, owner_generation, binding_id, workspace_id, workspace_binding_id,
            agent_id, input_id, authority_ref, surface, client_intent_id, fingerprint, enqueue_sequence,
            capability_revision, content, status, created_at, expires_at, source_grant_id, source_grant_revision
        ) VALUES (
            :server_id, :executor_id, :session_id, :owner_generation, :binding_id, :workspace_id, :workspace_binding_id,
            :agent_id, :input_id, :authority_ref, :surface, :client_intent_id, :fingerprint, :sequence,
            :capability_revision, :text, 'QUEUED', :created_at, :expires_at, :grant_id, :grant_revision
        )
    """, {
        **params, "input_id": input_id, "surface": author.surface, "fingerprint": fingerprint,
        "sequence": sequence, "capability_revision": capability_revision, "text": text,
        "created_at": now.isoformat(), "expires_at": (now + PENDING_LIFETIME).isoformat(),
        "grant_id": grant_id, "grant_revision": grant_revision,
    })
    return QueuedReceipt(input_id, sequence, 0, revision, InputDeliveryState.QUEUED, None, False)


def prepare_dispatch_head(uow: SqliteUnitOfWork, *, scope: InputScope, now: datetime) -> PendingInput | None:
    """Expire unsent entries and select the first pending input in this writer.

    Selection does not reserve capacity or authorize a native effect. A
    dispatcher must still check capability, authority and turn eligibility
    before admitting and linking an operation in the same transaction.
    """
    if now.utcoffset() is None:
        raise ValueError("Server time must be timezone-aware.")
    uow.require_active_writer()
    conn = uow.connection
    key = _scope_params(scope)
    if not _current_session(conn, key, require_active_lease=True):
        return None
    expired = conn.execute("""
        UPDATE session_interaction_inputs SET status='EXPIRED',input_revision=input_revision+1
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
          AND status='QUEUED' AND operation_id IS NULL AND expires_at<=:now
    """, {**key, "now": now.astimezone(UTC).isoformat()}).rowcount
    if expired:
        conn.execute("""
            UPDATE session_interaction_queues SET revision=revision+1
            WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
        """, key)
    head = conn.execute(f"""
        SELECT * FROM session_interaction_inputs
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
          AND status IN ({_PENDING_STATES})
        ORDER BY enqueue_sequence LIMIT 1
    """, key).fetchone()
    if (head is None or head["status"] != InputDeliveryState.QUEUED or head["operation_id"] is not None
            or head["owner_generation"] != scope.generation.value or head["binding_id"] != scope.binding_id
            or head["workspace_id"] != scope.workspace_id or head["workspace_binding_id"] != scope.workspace_binding_id
            or head["agent_id"] != scope.agent_id):
        return None
    source_grant = (head['source_grant_id'], head['source_grant_revision']) if head['source_grant_id'] else None
    return PendingInput(head["input_id"], head["input_revision"], InputAuthor(head["authority_ref"], head["surface"]),
                        head["capability_revision"], head["content"], source_grant)


def stage_dispatch(uow: SqliteUnitOfWork, *, scope: InputScope, head: PendingInput,
                   operation_id: str, reservation: CapacityReservation, now: datetime) -> CapacityConsumption:
    """Link an unsent R4 operation and its held capacity in the admission writer.

    The caller owns this transaction and rolls it back on error, including
    the R4 operation. The host must confirm capacity consumption before the
    operation can compete for the shared dispatch pump.
    """
    if (head.source_grant is None or prepare_dispatch_head(uow, scope=scope, now=now) != head
            or type(reservation) is not CapacityReservation or reservation.state != 'HELD'
            or reservation.remaining_ms <= 0 or reservation.consumption is not None
            or reservation.request.unit != 'next_turn'
            or reservation.request.attempt_id != f'{head.input_id}:{head.input_revision}'):
        raise _conflict('INPUT_DISPATCH_CHANGED', 'The input or its capacity reservation changed.')
    params = {**_scope_params(scope), 'operation_id': operation_id, 'input_id': head.input_id,
              'input_revision': head.input_revision}
    conn = uow.connection
    operation = conn.execute("""
        SELECT p.semantic_payload,p.expected_revisions_json,p.intent_hash,e.generation
        FROM execution_operations p
        JOIN execution_dispatch_outbox o USING (server_id,executor_id,operation_id)
        JOIN execution_executors e USING (server_id,executor_id)
        WHERE p.server_id=:server_id AND p.executor_id=:executor_id AND p.operation_id=:operation_id
          AND p.session_id=:session_id AND p.binding_id=:binding_id AND p.workspace_id=:workspace_id
          AND p.workspace_binding_id=:workspace_binding_id AND p.subject_agent_id=:agent_id
          AND p.actor_agent_id='operator' AND p.action='turn.submit' AND p.admission_state='ACCEPTED'
          AND o.dispatch_state='PENDING' AND o.attempt_no=0 AND e.control_state='CONTROL_READY'
    """, params).fetchone()
    if operation is None:
        raise _conflict('INPUT_OPERATION_CHANGED', 'The input has no matching unsent R4 operation.')
    if conn.execute("""
        SELECT 1 FROM execution_operations
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
          AND operation_id<>:operation_id AND action IN ('turn.submit', 'runtime.close')
          AND admission_state<>'RESOLVED_TERMINAL' LIMIT 1
    """, params).fetchone() is not None:
        raise _conflict('INPUT_EARLIER_WORK_PENDING', 'The session already has admitted work.')
    operation_scope = json.loads(operation['expected_revisions_json'])
    held_scope = reservation.request.scope.to_dict()
    if (operation_scope != {key: value for key, value in held_scope.items() if key not in {'boot_id', 'connection_generation'}}
            or held_scope['session_owner_generation'] != scope.generation.value
            or held_scope['connection_generation'] != operation['generation']
            or json.loads(operation['semantic_payload']).get('payload') != {'text': head.text}):
        raise _conflict('INPUT_OPERATION_CHANGED', 'The R4 operation differs from the reserved session or input.')
    consumption = CapacityConsumption(operation_id, operation['intent_hash'], None, None)
    changed = conn.execute("""
        UPDATE session_interaction_inputs SET operation_id=:operation_id, status='DISPATCHING',
            input_revision=input_revision+1, capacity_reservation_json=:reservation,
            capacity_consumption_json=:consumption, capacity_state='WAITING_CONSUMPTION'
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id AND input_id=:input_id
          AND input_revision=:input_revision AND status='QUEUED' AND operation_id IS NULL
    """, {**params, 'reservation': canonical_json(reservation.to_dict()).decode(),
           'consumption': canonical_json(consumption.to_dict()).decode()}).rowcount
    if changed != 1:
        raise _conflict('INPUT_DISPATCH_CHANGED', 'The input changed before it was linked to the R4 operation.')
    held_outbox = conn.execute("""
        UPDATE execution_dispatch_outbox SET dispatch_state='WAITING_INTERACTION_CAPACITY'
        WHERE server_id=:server_id AND executor_id=:executor_id AND operation_id=:operation_id
          AND dispatch_state='PENDING' AND attempt_no=0
    """, params).rowcount
    if held_outbox != 1:
        raise _conflict('INPUT_OPERATION_CHANGED', 'The outbox entry changed before the capacity hold.')
    conn.execute("""
        UPDATE session_interaction_queues SET revision=revision+1
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
    """, params)
    return consumption


def _capacity_claim_row(conn: Connection, params: dict):
    return conn.execute("""
        SELECT i.*,e.generation,e.control_state,e.revoked_at FROM session_interaction_inputs i
        JOIN execution_executors e USING (server_id,executor_id)
        WHERE i.server_id=:server_id AND i.executor_id=:executor_id AND i.session_id=:session_id
          AND i.operation_id=:operation_id AND i.owner_generation=:owner_generation AND i.binding_id=:binding_id
          AND i.workspace_id=:workspace_id AND i.workspace_binding_id=:workspace_binding_id AND i.agent_id=:agent_id
    """, params).fetchone()


def read_dispatch_capacity(uow: SqliteUnitOfWork, *, scope: InputScope, operation_id: str) -> CapacityAdmission:
    """Read immutable claim identities for the original host round trip."""
    linked = _capacity_claim_row(uow.connection, {**_scope_params(scope), 'operation_id': operation_id})
    if linked is None or linked['capacity_state'] is None:
        raise _conflict('INPUT_DISPATCH_CHANGED', 'The input has no matching staged capacity claim.')
    return CapacityAdmission(operation_id, CapacityReservation.from_dict(json.loads(linked['capacity_reservation_json'])),
        CapacityConsumption.from_dict(json.loads(linked['capacity_consumption_json'])), linked['capacity_state'])


def mark_dispatch_capacity_uncertain(uow: SqliteUnitOfWork, *, scope: InputScope, operation_id: str) -> None:
    uow.require_active_writer()
    uow.connection.execute("""
        UPDATE session_interaction_inputs SET capacity_state='NEEDS_RECONCILIATION'
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
          AND operation_id=:operation_id AND owner_generation=:owner_generation AND binding_id=:binding_id
          AND workspace_id=:workspace_id AND workspace_binding_id=:workspace_binding_id AND agent_id=:agent_id
          AND capacity_state='WAITING_CONSUMPTION'
    """, {**_scope_params(scope), 'operation_id': operation_id})


def confirm_dispatch_capacity(uow: SqliteUnitOfWork, *, scope: InputScope, operation_id: str,
                              observed: CapacityReservation) -> None:
    """Release the exact outbox hold after the authenticated host confirms it."""
    uow.require_active_writer()
    if type(observed) is not CapacityReservation or observed.state != 'CONSUMED':
        raise _conflict('INPUT_CAPACITY_UNCONFIRMED', 'The host has not confirmed input capacity consumption.')
    conn = uow.connection
    params = {**_scope_params(scope), 'operation_id': operation_id}
    linked = _capacity_claim_row(conn, params)
    if linked is None or linked['capacity_state'] not in ('WAITING_CONSUMPTION', 'NEEDS_RECONCILIATION', 'CONSUMED'):
        raise _conflict('INPUT_DISPATCH_CHANGED', 'The input has no matching staged capacity claim.')
    expected = CapacityReservation.from_dict(json.loads(linked['capacity_reservation_json']))
    consumption = CapacityConsumption.from_dict(json.loads(linked['capacity_consumption_json']))
    if (observed.request != expected.request or observed.reservation_id != expected.reservation_id
            or observed.consumption != consumption or observed.capacity_revision < expected.capacity_revision):
        raise _conflict('INPUT_CAPACITY_CHANGED', 'The host confirmed a different input capacity claim.')
    if linked['capacity_state'] == 'CONSUMED':
        return
    if (linked['status'] != 'DISPATCHING' or linked['possible_effect']
            or not _current_session(conn, params, require_active_lease=True) or linked['revoked_at'] is not None
            or linked['control_state'] != 'CONTROL_READY' or linked['generation'] != observed.request.scope.connection_generation):
        raise _conflict('INPUT_SESSION_CHANGED', 'The input session owner changed before dispatch.')
    reopened = conn.execute("""
        UPDATE execution_dispatch_outbox SET dispatch_state='PENDING'
        WHERE server_id=:server_id AND executor_id=:executor_id AND operation_id=:operation_id
          AND dispatch_state='WAITING_INTERACTION_CAPACITY' AND attempt_no=0
    """, params).rowcount
    if reopened != 1:
        raise _conflict('INPUT_OPERATION_CHANGED', 'The held outbox entry changed before confirmation.')
    conn.execute("""
        UPDATE session_interaction_inputs SET capacity_state='CONSUMED',input_revision=input_revision+1,
            capacity_reservation_json=:reservation
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id AND operation_id=:operation_id
    """, {**params, 'reservation': canonical_json(observed.to_dict()).decode()})
    conn.execute("""
        UPDATE session_interaction_queues SET revision=revision+1
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
    """, params)


def record_input_delivery(conn: Connection, *, operation_key: tuple[str, str, str],
                          state: InputDeliveryState, require_unsent: bool = False) -> None:
    """Project canonical delivery evidence without replacing the R4 outcome."""
    if state not in (InputDeliveryState.ACCEPTED_NATIVE, InputDeliveryState.REFUSED_BEFORE_SEND,
                     InputDeliveryState.DELIVERY_UNKNOWN):
        raise ValueError('Invalid canonical input delivery observation.')
    affected = conn.execute("""
        UPDATE session_interaction_inputs SET status=?,possible_effect=?,input_revision=input_revision+1
        WHERE server_id=? AND executor_id=? AND operation_id=?
          AND status IN ('DISPATCHING', 'DELIVERY_UNKNOWN') AND status<>?
          AND (NOT ? OR (status='DISPATCHING' AND possible_effect=0))
        RETURNING session_id
    """, (state.value, state is not InputDeliveryState.REFUSED_BEFORE_SEND,
          *operation_key, state.value, require_unsent)).fetchone()
    if affected is not None:
        conn.execute("""
            UPDATE session_interaction_queues SET revision=revision+1
            WHERE server_id=? AND executor_id=? AND session_id=?
        """, (*operation_key[:2], affected['session_id']))


def project_input_receipt(conn: Connection, *, operation_key: tuple[str, str, str],
                          stage: str, possible_effect: bool, native_id: str | None) -> None:
    if stage in ('ACCEPTED', 'RUNNING', 'WAITING_INPUT', 'SUCCEEDED'):
        state = InputDeliveryState.ACCEPTED_NATIVE
    elif stage in ('FAILED', 'CANCELLED') and not possible_effect and native_id is None:
        state = InputDeliveryState.REFUSED_BEFORE_SEND
    elif stage in ('OUTCOME_UNKNOWN', 'FAILED', 'CANCELLED'):
        state = InputDeliveryState.DELIVERY_UNKNOWN
    else:
        # Receipt of the command or its submission alone does not prove native acceptance.
        return
    record_input_delivery(conn, operation_key=operation_key, state=state)


def retire_unconsumed_dispatch(uow: SqliteUnitOfWork, *, scope: InputScope, operation_id: str,
                               observed: CapacityReservation) -> None:
    """Retire the existing operation only with matching host and local no-effect proof."""
    from .execution_dispatch_ownership import _error

    uow.require_active_writer()
    claim = read_dispatch_capacity(uow, scope=scope, operation_id=operation_id)
    if (type(observed) is not CapacityReservation or observed.state not in ('RELEASED', 'EXPIRED_UNCONSUMED')
            or observed.consumption is not None or observed.request != claim.reservation.request
            or observed.reservation_id != claim.reservation.reservation_id
            or observed.capacity_revision < claim.reservation.capacity_revision):
        raise _conflict('INPUT_CAPACITY_CHANGED', 'The proof does not match the unconsumed input reservation.')
    if claim.state == 'CANCELLED_NO_EFFECT':
        return
    if claim.state not in ('WAITING_CONSUMPTION', 'NEEDS_RECONCILIATION'):
        raise _conflict('INPUT_DISPATCH_CHANGED', 'The input already crossed its capacity hold.')
    conn = uow.connection
    key = (scope.session.server_id, scope.session.executor_id, operation_id)
    refusal = _error('CAPACITY_NOT_CONSUMED', 'The input reservation ended before dispatch.',
                     possible_effect=False, operation_id=operation_id)
    held = conn.execute("""
        UPDATE execution_dispatch_outbox SET dispatch_state='RESOLVED_TERMINAL',last_error=?
        WHERE server_id=? AND executor_id=? AND operation_id=?
          AND dispatch_state='WAITING_INTERACTION_CAPACITY' AND attempt_no=0
          AND NOT EXISTS (SELECT 1 FROM execution_receipts r WHERE r.server_id=execution_dispatch_outbox.server_id
              AND r.executor_id=execution_dispatch_outbox.executor_id AND r.operation_id=execution_dispatch_outbox.operation_id)
    """, (refusal, *key)).rowcount
    if held != 1:
        raise _conflict('INPUT_OPERATION_CHANGED', 'The held operation has no definitive pre-send proof.')
    terminal = conn.execute("""
        UPDATE execution_operations SET admission_state='RESOLVED_TERMINAL'
        WHERE server_id=? AND executor_id=? AND operation_id=? AND admission_state='ACCEPTED'
    """, key).rowcount
    settled = conn.execute("""
        UPDATE session_interaction_inputs SET capacity_state='CANCELLED_NO_EFFECT',capacity_reservation_json=?
        WHERE server_id=? AND executor_id=? AND operation_id=? AND status='DISPATCHING' AND possible_effect=0
    """, (canonical_json(observed.to_dict()).decode(), *key)).rowcount
    if terminal != 1 or settled != 1:
        raise _conflict('INPUT_DISPATCH_CHANGED', 'The linked input changed before no-effect retirement.')
    record_input_delivery(conn, operation_key=key, state=InputDeliveryState.REFUSED_BEFORE_SEND, require_unsent=True)


def has_unsent_capacity_proof(uow: SqliteUnitOfWork, *, scope: InputScope, claim: CapacityAdmission) -> bool:
    """Identify a pre-send dispatch refusal, independently of the host's slot state."""
    return uow.connection.execute("""
        SELECT 1 FROM session_interaction_inputs i
        JOIN execution_operations o USING (server_id,executor_id,operation_id)
        JOIN execution_dispatch_outbox x USING (server_id,executor_id,operation_id)
        JOIN execution_unsent_dispatch_proofs p USING (server_id,executor_id,operation_id,attempt_no)
        WHERE i.server_id=:server_id AND i.executor_id=:executor_id AND i.session_id=:session_id
          AND i.operation_id=:operation_id AND o.intent_hash=:intent_hash AND o.action='turn.submit'
          AND i.owner_generation=:owner_generation AND i.binding_id=:binding_id AND i.workspace_id=:workspace_id
          AND i.workspace_binding_id=:workspace_binding_id AND i.agent_id=:agent_id
          AND i.status='REFUSED_BEFORE_SEND' AND i.possible_effect=0
          AND i.capacity_state='CONSUMED' AND o.admission_state='RESOLVED_TERMINAL'
          AND x.dispatch_state='RESOLVED_TERMINAL' AND x.attempt_token=p.attempt_token
          AND x.reservation_owner=p.previous_owner AND x.reservation_generation=p.previous_generation
          AND json_extract(x.last_error,'$.stage')='dispatch' AND json_extract(x.last_error,'$.possible_effect')=0
          AND NOT EXISTS (SELECT 1 FROM execution_receipts r WHERE r.server_id=i.server_id
              AND r.executor_id=i.executor_id AND r.operation_id=i.operation_id)
    """, {**_scope_params(scope), 'operation_id': claim.operation_id,
           'intent_hash': claim.consumption.turn_intent_hash}).fetchone() is not None


def record_unsent_capacity_release(uow: SqliteUnitOfWork, *, scope: InputScope, operation_id: str,
                                   observed: CapacityReservation) -> None:
    """Keep the refusal and original R4 operation after release of its unused slot."""
    uow.require_active_writer()
    claim = read_dispatch_capacity(uow, scope=scope, operation_id=operation_id)
    if (type(observed) is not CapacityReservation or observed.state != 'RELEASED'
            or observed.request != claim.reservation.request or observed.reservation_id != claim.reservation.reservation_id
            or observed.consumption != claim.consumption or observed.capacity_revision < claim.reservation.capacity_revision):
        raise _conflict('INPUT_CAPACITY_CHANGED', 'The released slot does not match the refused input.')
    if claim.state == 'CANCELLED_NO_EFFECT':
        return
    if not has_unsent_capacity_proof(uow, scope=scope, claim=claim):
        raise _conflict('INPUT_UNSENT_PROOF_REQUIRED', 'The canonical operation has no matching pre-send refusal.')
    uow.connection.execute("""
        UPDATE session_interaction_inputs SET capacity_state='CANCELLED_NO_EFFECT',capacity_reservation_json=?
        WHERE server_id=? AND executor_id=? AND operation_id=?
    """, (canonical_json(observed.to_dict()).decode(), scope.session.server_id, scope.session.executor_id, operation_id))
