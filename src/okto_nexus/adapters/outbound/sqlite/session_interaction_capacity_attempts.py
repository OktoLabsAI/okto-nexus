"""Keep capacity request identity across a restart before the host replies."""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal

from nexus_connector_core import (
    CapacityConsumption,
    CapacityRequest,
    CapacityReservation,
    capacity_reservation_id,
)
from nexus_connector_core.protocol import canonical_json

from ....domain.execution.keys import SessionKey
from ....domain.session_interaction import InputScope
from .connection import SqliteUnitOfWork
from .session_interaction import PendingInput, _conflict, prepare_dispatch_head


@dataclass(frozen=True, slots=True)
class InputCapacityAttempt:
    request: CapacityRequest
    input_id: str
    input_revision: int
    state: Literal["PREPARED", "STAGED"]
    operation_id: str | None
    reservation: CapacityReservation | None
    consumption: CapacityConsumption | None
    resolved_at: str | None
    resolution: CapacityReservation | None = None


def read_capacity_attempt(
    uow: SqliteUnitOfWork, *, session: SessionKey, attempt_id: str | None = None,
) -> InputCapacityAttempt | None:
    """Read the named attempt, or the single open pre-RPC attempt for this session."""
    predicate = "state='PREPARED' AND resolved_at IS NULL" if attempt_id is None else "attempt_id=:attempt_id"
    row = uow.connection.execute(
        "SELECT * FROM session_interaction_capacity_attempts "
        "WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id AND " + predicate,
        {**asdict(session), "attempt_id": attempt_id},
    ).fetchone()
    if row is None:
        return None
    return InputCapacityAttempt(
        CapacityRequest.from_dict(json.loads(row["request_json"])),
        row["input_id"], row["input_revision"], row["state"], row["operation_id"],
        CapacityReservation.from_dict(json.loads(row["reservation_json"])) if row["reservation_json"] else None,
        CapacityConsumption.from_dict(json.loads(row["consumption_json"])) if row["consumption_json"] else None,
        row["resolved_at"],
        CapacityReservation.from_dict(json.loads(row["resolution_json"])) if row["resolution_json"] else None,
    )


def _matches_scope(request: CapacityRequest, scope: InputScope) -> bool:
    return (type(request) is CapacityRequest and request.unit == "next_turn"
            and all(getattr(request.scope, name) == value for name, value in asdict(scope.session).items())
            and request.scope.session_owner_generation == scope.generation.value
            and all(getattr(request.scope, name) == getattr(scope, name) for name in (
                "agent_id", "binding_id", "workspace_id", "workspace_binding_id")))


def prepare_capacity_attempt(
    uow: SqliteUnitOfWork, *, scope: InputScope, head: PendingInput, request: CapacityRequest, now: datetime,
) -> InputCapacityAttempt:
    """Persist the request before RPC. The caller still owns live authority and host checks."""
    uow.require_active_writer()
    if not _matches_scope(request, scope) or request.attempt_id != f"{head.input_id}:{head.input_revision}":
        raise _conflict("INPUT_CAPACITY_REQUEST_CHANGED", "The request does not match the exact input.")
    prior = read_capacity_attempt(uow, session=scope.session, attempt_id=request.attempt_id)
    if prior is not None:
        if prior.request != request:
            raise _conflict("INPUT_CAPACITY_REQUEST_CHANGED", "The stored capacity request differs.")
        if prior.state == "STAGED" or prior.resolved_at is not None:
            return prior
    unresolved = read_capacity_attempt(uow, session=scope.session)
    if unresolved is not None and unresolved.request != request:
        raise _conflict("INPUT_CAPACITY_ATTEMPT_PENDING", "The session has an unresolved capacity attempt.")
    params = {**asdict(scope.session), "binding_id": scope.binding_id,
              "connection_generation": request.scope.connection_generation,
              "binding_revision": request.scope.binding_revision}
    current = uow.connection.execute("""
        SELECT 1 FROM execution_executors e JOIN execution_bindings b USING (server_id, executor_id)
        WHERE e.server_id=:server_id AND e.executor_id=:executor_id AND e.generation=:connection_generation
          AND e.control_state='CONTROL_READY' AND e.revoked_at IS NULL
          AND b.binding_id=:binding_id AND b.binding_revision=:binding_revision
    """, params).fetchone()
    if current is None:
        raise _conflict("INPUT_CAPACITY_OWNER_CHANGED", "The connection or binding changed before the attempt.")
    if head.source_grant is None or prepare_dispatch_head(uow, scope=scope, now=now) != head:
        raise _conflict("INPUT_CAPACITY_HEAD_CHANGED", "The input is no longer the eligible FIFO head.")
    if prior is not None:
        return prior
    uow.connection.execute("""
        INSERT INTO session_interaction_capacity_attempts (
            server_id, executor_id, session_id, attempt_id, input_id, input_revision, request_json, state, created_at
        ) VALUES (
            :server_id, :executor_id, :session_id, :attempt_id, :input_id, :input_revision, :request, 'PREPARED', :now
        )
    """, {**params, "attempt_id": request.attempt_id, "input_id": head.input_id, "input_revision": head.input_revision,
           "request": canonical_json(request.to_dict()).decode(), "now": now.astimezone(UTC).isoformat()})
    return InputCapacityAttempt(request, head.input_id, head.input_revision, "PREPARED", None, None, None, None)


def record_staged_capacity_attempt(
    uow: SqliteUnitOfWork, *, scope: InputScope, request: CapacityRequest, operation_id: str,
) -> InputCapacityAttempt:
    """Retain the staged proof in the same writer as the input and canonical R4 operation."""
    uow.require_active_writer()
    if not _matches_scope(request, scope):
        raise _conflict("INPUT_CAPACITY_REQUEST_CHANGED", "The request does not match the exact session.")
    attempt = read_capacity_attempt(uow, session=scope.session, attempt_id=request.attempt_id)
    if attempt is None or attempt.request != request or attempt.resolved_at is not None:
        raise _conflict("INPUT_CAPACITY_REQUEST_CHANGED", "The prepared capacity request differs or is unavailable.")
    if attempt.state == "STAGED":
        if attempt.operation_id != operation_id:
            raise _conflict("INPUT_CAPACITY_OPERATION_CHANGED", "The attempt already has a different operation.")
        return attempt
    params = {**asdict(scope.session), "attempt_id": request.attempt_id, "input_id": attempt.input_id,
              "staged_revision": attempt.input_revision + 1, "operation_id": operation_id}
    staged = uow.connection.execute("""
        SELECT i.capacity_reservation_json, i.capacity_consumption_json, p.intent_hash, p.expected_revisions_json
        FROM session_interaction_inputs i
        JOIN execution_operations p USING (server_id, executor_id, operation_id)
        JOIN execution_dispatch_outbox o USING (server_id, executor_id, operation_id)
        WHERE i.server_id=:server_id AND i.executor_id=:executor_id AND i.session_id=:session_id
          AND i.input_id=:input_id AND i.input_revision=:staged_revision AND i.operation_id=:operation_id
          AND i.status='DISPATCHING' AND i.possible_effect=0 AND i.capacity_state='WAITING_CONSUMPTION'
          AND p.session_id=i.session_id AND p.binding_id=i.binding_id AND p.workspace_id=i.workspace_id
          AND p.workspace_binding_id=i.workspace_binding_id AND p.subject_agent_id=i.agent_id
          AND p.actor_agent_id='operator' AND p.action='turn.submit' AND p.admission_state='ACCEPTED'
          AND o.dispatch_state='WAITING_INTERACTION_CAPACITY' AND o.attempt_no=0
    """, params).fetchone()
    if staged is None:
        raise _conflict("INPUT_CAPACITY_OPERATION_CHANGED", "The staged input has no matching held R4 operation.")
    reservation = CapacityReservation.from_dict(json.loads(staged["capacity_reservation_json"]))
    consumption = CapacityConsumption.from_dict(json.loads(staged["capacity_consumption_json"]))
    operation_scope = {key: value for key, value in request.scope.to_dict().items()
                       if key not in {"boot_id", "connection_generation"}}
    if (reservation.request != request or reservation.state != "HELD" or reservation.remaining_ms <= 0
            or reservation.reservation_id != capacity_reservation_id(request)
            or json.loads(staged["expected_revisions_json"]) != operation_scope
            or consumption != CapacityConsumption(operation_id, staged["intent_hash"], None, None)):
        raise _conflict("INPUT_CAPACITY_OPERATION_CHANGED", "The staged reservation or operation identity differs.")
    uow.connection.execute("""
        UPDATE session_interaction_capacity_attempts SET state='STAGED', operation_id=:operation_id,
            reservation_json=:reservation, consumption_json=:consumption
        WHERE server_id=:server_id AND executor_id=:executor_id AND attempt_id=:attempt_id
    """, {**params, "reservation": staged["capacity_reservation_json"], "consumption": staged["capacity_consumption_json"]})
    return InputCapacityAttempt(
        request, attempt.input_id, attempt.input_revision, "STAGED", operation_id, reservation, consumption, None,
    )


def retire_prepared_capacity_attempt(uow: SqliteUnitOfWork, *, scope: InputScope,
                                     observed: CapacityReservation, now: datetime) -> InputCapacityAttempt:
    """Record a definitive host refusal while leaving the original intent retained."""
    uow.require_active_writer()
    if (type(observed) is not CapacityReservation or observed.state not in ('EXPIRED_UNCONSUMED', 'RELEASED')
            or observed.consumption is not None or not _matches_scope(observed.request, scope)
            or observed.reservation_id != capacity_reservation_id(observed.request) or now.utcoffset() is None):
        raise _conflict('INPUT_CAPACITY_PROOF_CHANGED', 'The host did not prove an exact unconsumed attempt.')
    attempt = read_capacity_attempt(uow, session=scope.session, attempt_id=observed.request.attempt_id)
    if attempt is None or attempt.request != observed.request or attempt.state != 'PREPARED':
        raise _conflict('INPUT_CAPACITY_REQUEST_CHANGED', 'The prepared capacity request differs or is unavailable.')
    if attempt.resolved_at is not None:
        return attempt
    conn = uow.connection
    params = {**asdict(scope.session), 'attempt_id': observed.request.attempt_id, 'input_id': attempt.input_id,
              'input_revision': attempt.input_revision, 'resolved_at': now.astimezone(UTC).isoformat(),
              'proof': canonical_json(observed.to_dict()).decode()}
    conn.execute("""
        UPDATE session_interaction_capacity_attempts SET resolved_at=:resolved_at,resolution_json=:proof
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id AND attempt_id=:attempt_id
    """, params)
    changed = conn.execute("""
        UPDATE session_interaction_inputs SET status='REFUSED_BEFORE_SEND',input_revision=input_revision+1
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id AND input_id=:input_id
          AND input_revision=:input_revision AND status='QUEUED' AND operation_id IS NULL AND possible_effect=0
    """, params).rowcount
    if changed:
        conn.execute("""
            UPDATE session_interaction_queues SET revision=revision+1
            WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
        """, params)
    return read_capacity_attempt(uow, session=scope.session, attempt_id=observed.request.attempt_id)


def block_unstaged_input_authority(uow: SqliteUnitOfWork, *, scope: InputScope, input_id: str, input_revision: int):
    uow.require_active_writer()
    params = {**asdict(scope.session), 'input_id': input_id, 'input_revision': input_revision,
              'owner_generation': scope.generation.value}
    conn = uow.connection
    changed = conn.execute("""
        UPDATE session_interaction_inputs SET status='BLOCKED_AUTH',input_revision=input_revision+1
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id AND input_id=:input_id
          AND input_revision=:input_revision AND owner_generation=:owner_generation
          AND status='QUEUED' AND operation_id IS NULL AND possible_effect=0
    """, params).rowcount
    if changed:
        conn.execute("""
            UPDATE session_interaction_queues SET revision=revision+1
            WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id
        """, params)


def fence_prepared_capacity_release(uow: SqliteUnitOfWork, *, scope: InputScope, request: CapacityRequest,
                                    authority_denied: bool = False) -> bool:
    """Prove this request cannot stage before sending its exact release to Core."""
    uow.require_active_writer()
    if not _matches_scope(request, scope):
        return False
    attempt = read_capacity_attempt(uow, session=scope.session, attempt_id=request.attempt_id)
    if attempt is None or attempt.request != request or attempt.state != 'PREPARED' or attempt.resolved_at is not None:
        return False
    conn = uow.connection
    params = {**asdict(scope.session), 'input_id': attempt.input_id, 'input_revision': attempt.input_revision,
              'owner_generation': scope.generation.value}
    if authority_denied:
        block_unstaged_input_authority(uow, scope=scope, input_id=attempt.input_id, input_revision=attempt.input_revision)
    return conn.execute("""
        SELECT 1 FROM session_interaction_inputs
        WHERE server_id=:server_id AND executor_id=:executor_id AND session_id=:session_id AND input_id=:input_id
          AND owner_generation=:owner_generation AND operation_id IS NULL AND possible_effect=0
          AND status IN ('BLOCKED_AUTH','BLOCKED_SESSION','CANCELLED','EXPIRED')
    """, params).fetchone() is not None
