"""Durable pre-send R4 dispatch reservations with an independent control lane."""

from __future__ import annotations

from .executor_inventory import load_current_executor_inventory

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import secrets
import time
from typing import Mapping

from nexus_connector_core import CoreError, R4_PREVIEW_REVISION, decode_r4_frame
from nexus_connector_core.protocol import canonical_json

from ..adapters.outbound.sqlite.connection import ConnectionFactory
from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ..errors import ErrorCode, OktoNexusError
from ..domain.runtime_context import RuntimeRequestContext
from .execution_binding_proposals import _agent_guard
from .execution_leases import ExecutionChannel, require_execution_lane
from .execution_semantics import (
    execution_intent_hash, execution_wire_intent, validate_execution_target,
)


_CONTROL = frozenset({"turn.steer", "turn.interrupt", "runtime.close",
                      "approval.decide", "input.provide"})
_REGULAR = frozenset({"runtime.open", "turn.submit"})


@dataclass(frozen=True, slots=True)
class DispatchReservation:
    server_id: str
    executor_id: str
    operation_id: str
    attempt_token: str
    attempt_no: int
    reservation_class: str
    reserved_bytes: int
    owner_connection_id: str | None = None
    owner_connection_generation: int | None = None


@dataclass(frozen=True, slots=True)
class AuthorizedDispatch:
    reservation: DispatchReservation
    semantic_intent: dict = field(repr=False)
    lease_id: str
    lease_serial: int
    connection_generation: int
    connection_id: str
    grant_id: str
    scope: dict
    frame: dict = field(repr=False)


@dataclass(frozen=True, slots=True)
class AuthorizedOpenBootstrap:
    """An opening envelope that permits selection and lease request only.

    It deliberately has no lease or Core ExecutionContext. The executor must
    install the correlated initial lease before asking Core to prepare/open.
    Sending this envelope fences the operation just like any other send;
    losing its response does not authorize a second dispatch.
    """
    reservation: DispatchReservation
    semantic_intent: dict
    connection_generation: int
    connection_id: str
    grant_id: str
    scope: dict
    frame: dict


def reserve_execution_dispatch(
    factory: ConnectionFactory, *, server_id: str, executor_id: str,
    remote_ready: bool, regular_items: int = 4,
    regular_bytes: int = 256 * 1024, control_items: int = 2,
    control_bytes: int = 128 * 1024,
    channel: ExecutionChannel | None = None,
    retained_operations: tuple[str, ...] = (),
) -> DispatchReservation | None:
    """Reserve one exact row/byte cost before a dispatcher starts a task.

    The write transaction serializes concurrent dispatchers. No network or
    process action occurs here. A crashed reservation stays fenced until a
    separate no-send recovery proves that it can be released.
    """
    if not remote_ready:
        return None
    retained = json.dumps(retained_operations)
    if (any(type(value) is not int or value <= 0 for value in (
            regular_items, regular_bytes, control_items, control_bytes)) or
            not server_id or not executor_id):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid dispatch capacity.", {})
    with factory.unit_of_work() as uow:
        conn = uow.connection
        if channel is not None:
            if channel.server_id != server_id or channel.executor_id != executor_id:
                raise OktoNexusError(ErrorCode.CONFLICT, "The dispatch owner has a different scope.", {})
            if conn.execute(
                    "SELECT 1 FROM execution_executors WHERE server_id=? AND executor_id=? "
                    "AND owner_instance_id=? AND generation=? AND control_state='CONTROL_READY' AND revoked_at IS NULL",
                    (server_id, executor_id, channel.connection_id, channel.connection_generation)).fetchone() is None:
                return None
        from .execution_initial_turns import release_ready_initial_turns
        release_ready_initial_turns(conn, server_id=server_id, executor_id=executor_id)
        from .execution_domain_delivery import project_delivery_refusals
        project_delivery_refusals(conn, server_id=server_id, executor_id=executor_id)
        used = {"regular": [0, 0], "control": [0, 0]}
        for row in conn.execute(
            "SELECT reservation_class,COUNT(*) AS items,"
            "COALESCE(SUM(reserved_bytes),0) AS bytes FROM "
            "execution_dispatch_outbox WHERE server_id=? AND executor_id=? "
            "AND dispatch_state IN ('RESERVED','SENDING','RECONCILING') "
            "AND NOT EXISTS (SELECT 1 FROM execution_agent_recovery r JOIN execution_operations p "
            "USING(server_id,executor_id) WHERE p.operation_id=execution_dispatch_outbox.operation_id "
            "AND p.server_id=execution_dispatch_outbox.server_id AND p.executor_id=execution_dispatch_outbox.executor_id "
            "AND r.agent_id=p.subject_agent_id AND r.state='RECOVERING') "
            "GROUP BY reservation_class",
            (server_id, executor_id),
        ):
            if row["reservation_class"] in used:
                used[row["reservation_class"]] = [row["items"], row["bytes"]]
        # A receipt releases the durable reservation, but an embedded producer
        # may still be returning from its native call. Count those live calls
        # once, without double-counting their still-reserved outbox rows.
        for row in conn.execute(
            "SELECT p.action,length(CAST(p.semantic_payload AS BLOB)) AS bytes "
            "FROM execution_operations p JOIN execution_dispatch_outbox o "
            "USING(server_id,executor_id,operation_id) "
            "WHERE p.server_id=? AND p.executor_id=? "
            "AND p.operation_id IN (SELECT value FROM json_each(?)) "
            "AND o.dispatch_state NOT IN ('RESERVED','SENDING','RECONCILING') "
            "AND NOT EXISTS (SELECT 1 FROM execution_agent_recovery r "
            "WHERE r.server_id=p.server_id AND r.executor_id=p.executor_id "
            "AND r.agent_id=p.subject_agent_id AND r.state='RECOVERING')",
            (server_id, executor_id, retained),
        ):
            lane = 'regular' if row['action'] in _REGULAR else 'control'
            used[lane][0] += 1
            used[lane][1] += row['bytes']
        # Filter each lane by its remaining budget before selecting a row.
        # A fixed mixed window lets a blocked control backlog hide all regular
        # work, or oversized rows hide later controls that still fit.
        for lane, actions, max_items, max_bytes in (
            ("control", sorted(_CONTROL), control_items, control_bytes),
            ("regular", sorted(_REGULAR), regular_items, regular_bytes),
        ):
            remaining = max_bytes - used[lane][1]
            if used[lane][0] >= max_items or remaining <= 0:
                continue
            placeholders = ",".join("?" for _ in actions)
            row = conn.execute(
                "SELECT o.operation_id,o.attempt_no,"
                "length(CAST(p.semantic_payload AS BLOB)) AS byte_cost "
                "FROM execution_dispatch_outbox o JOIN execution_operations p "
                "ON p.server_id=o.server_id AND p.executor_id=o.executor_id "
                "AND p.operation_id=o.operation_id "
                "WHERE o.server_id=? AND o.executor_id=? "
                "AND o.dispatch_state='PENDING' "
                "AND (o.next_attempt_at IS NULL OR o.next_attempt_at<=?) "
                "AND p.admission_state IN ('ACCEPTED','DISPATCH_PENDING') "
                # One agent may open several independent sessions. Until a
                # productive native call is acknowledged, reserve at most one
                # shared worker for that agent so slow opens cannot starve its
                # peers. Controls retain their independent containment budget.
                "AND (?='control' OR NOT EXISTS (SELECT 1 FROM execution_dispatch_outbox busy "
                "JOIN execution_operations active USING(server_id,executor_id,operation_id) "
                "WHERE busy.server_id=p.server_id AND busy.executor_id=p.executor_id "
                "AND active.subject_agent_id=p.subject_agent_id AND active.action IN ('runtime.open','turn.submit') "
                "AND (busy.dispatch_state IN ('RESERVED','SENDING','RECONCILING') "
                "OR busy.operation_id IN (SELECT value FROM json_each(?))))) "
                "AND NOT EXISTS (SELECT 1 FROM execution_agent_recovery r JOIN execution_executors e USING(server_id,executor_id) "
                "WHERE r.server_id=p.server_id AND r.executor_id=p.executor_id AND r.agent_id=p.subject_agent_id "
                "AND (r.state<>'READY' OR r.generation<>e.generation)) "
                "AND p.action IN (" + placeholders + ") "
                "AND length(CAST(p.semantic_payload AS BLOB))<=? "
                # Administrative turns have no domain-delivery mapping. They
                # still share the native session with a delivery awaiting a
                # proven-unsent retry. Its immutable failed attempt identifies
                # that session even after the live mapping is archived.
                "AND (p.action<>'turn.submit' OR NOT EXISTS (SELECT 1 FROM delivery_outbox retry "
                "JOIN execution_operations refused ON (refused.operation_id=retry.attempt_id OR EXISTS ("
                "SELECT 1 FROM execution_domain_deliveries live WHERE live.server_id=refused.server_id "
                "AND live.executor_id=refused.executor_id AND live.operation_id=refused.operation_id "
                "AND live.domain_operation_id=retry.operation_id)) "
                "WHERE retry.status='RETRY_WAIT' AND refused.server_id=p.server_id "
                "AND refused.executor_id=p.executor_id AND refused.session_id=p.session_id "
                "AND NOT EXISTS (SELECT 1 FROM execution_domain_deliveries own "
                "WHERE own.server_id=p.server_id AND own.executor_id=p.executor_id "
                "AND own.operation_id=p.operation_id AND own.domain_operation_id=retry.operation_id))) "
                "AND NOT EXISTS (SELECT 1 FROM execution_domain_deliveries m "
                "JOIN delivery_outbox d ON d.operation_id=m.domain_operation_id "
                "JOIN delivery_outbox earlier ON earlier.endpoint_id=d.endpoint_id "
                "JOIN agent_endpoints endpoint ON endpoint.endpoint_id=d.endpoint_id "
                "LEFT JOIN agent_runtime_overrides policy ON policy.agent_id=endpoint.agent_id "
                "JOIN runtime_policy_defaults global_policy ON global_policy.singleton=1 "
                "WHERE m.server_id=p.server_id AND m.executor_id=p.executor_id AND m.operation_id=p.operation_id "
                "AND (COALESCE(policy.session_policy,global_policy.session_policy)='shared' OR EXISTS (SELECT 1 FROM messages incoming "
                "JOIN messages preceding ON preceding.message_id=earlier.message_id "
                "WHERE incoming.message_id=d.message_id AND incoming.from_agent_id=preceding.from_agent_id "
                "AND (COALESCE(policy.session_policy,global_policy.session_policy)='per_sender' OR "
                "COALESCE((SELECT source_session_key FROM execution_message_origins WHERE message_id=incoming.message_id),'')="
                "COALESCE((SELECT source_session_key FROM execution_message_origins WHERE message_id=preceding.message_id),'')))) "
                "AND (earlier.created_at,earlier.operation_id)<(d.created_at,d.operation_id) "
                "AND earlier.reconciliation_id IS NULL AND earlier.external_completed_at IS NULL "
                "AND earlier.terminal_event_id IS NULL AND (earlier.canonical_terminal_operation_id IS NULL OR earlier.status='RETRY_WAIT') "
                "AND NOT EXISTS (SELECT 1 FROM execution_delivery_releases r WHERE r.domain_operation_id=earlier.operation_id) "
                "AND earlier.status NOT IN ('REJECTED','CANCELLED','FAILED_FINAL')) "
                "ORDER BY p.created_at,p.operation_id LIMIT 1",
                (server_id, executor_id, datetime.now(timezone.utc).isoformat(), lane, retained,
                 *actions, remaining),
            ).fetchone()
            if row is None:
                continue
            cost = row["byte_cost"]
            token = "attempt_" + secrets.token_hex(16)
            now = datetime.now(timezone.utc).isoformat()
            changed = conn.execute(
                "UPDATE execution_dispatch_outbox SET dispatch_state='RESERVED',"
                "attempt_token=?,attempt_no=attempt_no+1,"
                "reservation_class=?,reserved_bytes=?,reserved_at=?,reservation_owner=?,reservation_generation=? "
                "WHERE server_id=? AND executor_id=? AND operation_id=? "
                "AND dispatch_state='PENDING'",
                (token, lane, cost, now,
                 channel.connection_id if channel else None,
                 channel.connection_generation if channel else None, server_id, executor_id,
                 row["operation_id"]),
            ).rowcount
            if changed != 1:
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The dispatch row changed during reservation.", {})
            return DispatchReservation(
                server_id, executor_id, row["operation_id"], token,
                row["attempt_no"] + 1, lane, cost,
                channel.connection_id if channel else None,
                channel.connection_generation if channel else None)
    return None


def release_unsent_dispatch(factory: ConnectionFactory, *,
                            reservation: DispatchReservation) -> None:
    """Release only the exact RESERVED token when no send has begun."""
    if not isinstance(reservation, DispatchReservation):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid dispatch reservation.", {})
    with factory.unit_of_work() as uow:
        changed = uow.connection.execute(
            "UPDATE execution_dispatch_outbox SET dispatch_state='PENDING',"
            "attempt_token=NULL,reservation_class=NULL,reserved_bytes=0,"
            "reserved_at=NULL,reservation_owner=NULL,reservation_generation=NULL WHERE server_id=? AND executor_id=? "
            "AND operation_id=? AND attempt_token=? AND attempt_no=? "
            "AND dispatch_state='RESERVED' AND reservation_class=? "
            "AND reserved_bytes=? AND reservation_owner IS ? AND reservation_generation IS ?",
            (reservation.server_id, reservation.executor_id,
             reservation.operation_id, reservation.attempt_token,
             reservation.attempt_no, reservation.reservation_class,
             reservation.reserved_bytes, reservation.owner_connection_id,
             reservation.owner_connection_generation),
        ).rowcount
        if changed != 1:
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch reservation is no longer unsent.", {})


def begin_execution_send(
    factory: ConnectionFactory, *, reservation: DispatchReservation,
    remote_ready: bool, fresh_publications: Mapping, access,
    channel: ExecutionChannel | None = None,
    resolve_native_input=None,
) -> AuthorizedDispatch | AuthorizedOpenBootstrap:
    """Revalidate after queue wait, then fence the exact attempt as SENDING.

    The caller may perform I/O only after this transaction commits. A crashed
    SENDING attempt is never returned to PENDING by unsent release.
    """
    if not isinstance(reservation, DispatchReservation) or not remote_ready:
        raise OktoNexusError(ErrorCode.CONFLICT,
                              "The dispatch channel is unavailable.", {})
    with factory.unit_of_work(write=False) as uow:
        subject = uow.connection.execute(
            "SELECT subject_agent_id FROM execution_operations WHERE "
            "server_id=? AND executor_id=? AND operation_id=?",
            (reservation.server_id, reservation.executor_id,
             reservation.operation_id),
        ).fetchone()
    if subject is None:
        raise OktoNexusError(ErrorCode.NOT_FOUND,
                              "The dispatch operation was not found.", {})
    server_id, revisions, _ = current_agent_revisions(
        factory, agent_id=subject["subject_agent_id"])
    if server_id != reservation.server_id:
        raise OktoNexusError(ErrorCode.CONFLICT,
                              "The dispatch installation changed.", {})
    key = (reservation.server_id, reservation.executor_id,
           reservation.operation_id)
    with factory.unit_of_work() as uow:
        conn = uow.connection
        row = conn.execute(
            "SELECT p.server_id,p.executor_id,p.operation_id,o.dispatch_state,o.attempt_token,o.attempt_no,"
            "o.reservation_class,o.reserved_bytes,o.reservation_owner,o.reservation_generation,"
            "p.subject_agent_id,p.actor_agent_id,p.binding_id,p.workspace_id,"
            "p.workspace_binding_id,p.session_id,p.action,p.semantic_payload,"
            "p.expected_revisions_json,p.admission_state,p.intent_hash,p.decision_id,p.boot_authority_json "
            "FROM execution_dispatch_outbox o JOIN execution_operations p "
            "ON p.server_id=o.server_id AND p.executor_id=o.executor_id "
            "AND p.operation_id=o.operation_id WHERE o.server_id=? "
            "AND o.executor_id=? AND o.operation_id=?", key,
        ).fetchone()
        if (row is None or row["dispatch_state"] != "RESERVED" or
                row["attempt_token"] != reservation.attempt_token or
                row["attempt_no"] != reservation.attempt_no or
                row["reservation_class"] != reservation.reservation_class or
                row["reserved_bytes"] != reservation.reserved_bytes or
                row["reservation_owner"] != reservation.owner_connection_id or
                row["reservation_generation"] != reservation.owner_connection_generation or
                row["admission_state"] not in {
                    "ACCEPTED", "DISPATCH_PENDING"}):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch reservation changed.", {})
        from .execution_initial_turns import require_current_parent_readiness
        require_current_parent_readiness(conn, server_id=server_id,
            executor_id=reservation.executor_id, operation_id=reservation.operation_id)
        provenance = conn.execute(
            "SELECT source_guard_digest,actor_guard_digest FROM execution_client_intents "
            "WHERE server_id=? AND actor_agent_id=? AND operation_id=? "
            "AND intent_id GLOB ? AND session_selection<>\'reuse\'",
            (server_id, row["actor_agent_id"], reservation.operation_id,
             'r4decisionintent_*' if row["action"] in {"approval.decide", "input.provide"} else 'r4intent_*'),
        ).fetchall()
        scope = json.loads(row["expected_revisions_json"])
        native_decision = row["action"] in {"approval.decide", "input.provide"}
        operator_containment = (row['actor_agent_id'] != row['subject_agent_id'] and
            row['action'] in {'turn.interrupt', 'runtime.close'})
        if (len(provenance) != 1 or
                not provenance[0]["source_guard_digest"] or
                provenance[0]["source_guard_digest"] !=
                _agent_guard(conn, row["subject_agent_id"]) or
                (not operator_containment and (scope["authorization_revision"] != revisions.authorization or
                scope["configuration_revision"] != revisions.configuration or
                scope["credential_epoch"] != revisions.credential_epoch))):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch authority changed.", {})
        operator_context = None
        if not native_decision:
            from .execution_operator_authority import require_recorded_operator
            operator_context = require_recorded_operator(uow, actor=row['actor_agent_id'], subject=row['subject_agent_id'],
                                      guard=provenance[0]['actor_guard_digest'], access=access)
        binding = conn.execute(
            "SELECT b.endpoint_id,b.binding_revision,b.inventory_revision,b.candidate_ref,"
            "b.realization_revision,ep.agent_id,ep.adapter_id,ep.protocol,"
            "ep.profile_id,w.workspace_id,w.status AS workspace_status,"
            "r.status AS realization_status,r.revision AS current_realization_revision,"
            "e.kind,e.control_state,e.revoked_at,e.generation,e.owner_instance_id "
            "FROM execution_bindings b "
            "JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id "
            "JOIN execution_workspace_bindings w ON w.server_id=b.server_id "
            "AND w.executor_id=b.executor_id AND "
            "w.workspace_binding_id=b.workspace_binding_id "
            "JOIN execution_realizations r ON r.server_id=b.server_id "
            "AND r.executor_id=b.executor_id AND r.realization_ref=b.realization_ref "
            "JOIN execution_executors e ON e.server_id=b.server_id "
            "AND e.executor_id=b.executor_id "
            "WHERE b.server_id=? AND b.executor_id=? AND b.binding_id=? "
            "AND b.workspace_binding_id=?",
            (server_id, reservation.executor_id, row["binding_id"],
             row["workspace_binding_id"]),
        ).fetchone()
        from .execution_agent_recovery import require_agent_ready
        require_agent_ready(conn, server_id, reservation.executor_id, row["subject_agent_id"])
        if (binding is None or binding["binding_revision"] !=
                scope["binding_revision"] or
                binding["agent_id"] != row["subject_agent_id"] or
                binding["protocol"] != "nxl-r4" or
                binding["workspace_id"] != row["workspace_id"] or
                binding["workspace_status"] != "READY" or
                binding["realization_status"] != "READY" or
                binding["realization_revision"] !=
                binding["current_realization_revision"] or
                binding["control_state"] != "CONTROL_READY" or
                binding["revoked_at"] is not None):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch binding changed.", {})
        if reservation.owner_connection_id is not None and (
                binding["owner_instance_id"] != reservation.owner_connection_id or
                binding["generation"] != reservation.owner_connection_generation):
            raise OktoNexusError(ErrorCode.CONFLICT, "The dispatch reservation owner changed.", {})
        if channel is not None and (
                channel.server_id != server_id or channel.executor_id != reservation.executor_id or
                channel.connection_id != binding["owner_instance_id"] or
                channel.connection_generation != binding["generation"]):
            raise OktoNexusError(ErrorCode.CONFLICT, "The dispatch source connection changed.", {})
        semantic = json.loads(row["semantic_payload"])
        if native_decision:
            from .execution_native_decisions import validate_native_dispatch
            validate_native_dispatch(uow, operation=row, semantic=semantic, access=access)
            if semantic["payload"].get("response_ref") is not None:
                if resolve_native_input is None:
                    raise OktoNexusError("AUTHORIZED_INPUT_UNAVAILABLE",
                                        "The authorized input must be explicitly supplied again.", {})
                response = resolve_native_input(semantic)
                semantic["payload"] = {name: value for name, value in semantic["payload"].items() if name != "response_ref"}
                semantic["payload"]["response"] = response
        if (semantic["action"] != row["action"] or
                execution_intent_hash(semantic) != row["intent_hash"]):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The stored dispatch intent changed.", {})
        validate_execution_target(binding["adapter_id"], row["action"], semantic["target"])
        from .execution_domain_delivery import require_domain_delivery
        require_domain_delivery(uow, access=access, server_id=server_id,
            executor_id=reservation.executor_id, operation_id=reservation.operation_id)
        containment = row["action"] in {"turn.interrupt", "runtime.close"}
        operator_containment = containment and operator_context is not None
        current = conn.execute(
            "SELECT c.inventory_revision,c.publication_sequence,"
            "s.observation_age_ms,s.canonical_projection "
            "FROM execution_inventory_current c "
            "JOIN execution_inventory_snapshots s ON s.server_id=c.server_id "
            "AND s.executor_id=c.executor_id AND "
            "s.publication_sequence=c.publication_sequence "
            "WHERE c.server_id=? AND c.executor_id=?",
            (server_id, reservation.executor_id),
        ).fetchone()
        fresh = fresh_publications.get((server_id, reservation.executor_id))
        from .execution_inventory_revalidation import accepts_binding
        if not containment and (current is None or fresh is None or
                not accepts_binding(conn, binding, current['inventory_revision'], server_id, reservation.executor_id) or
                fresh[0] != current["publication_sequence"] or
                current["observation_age_ms"] +
                max(0, int((time.monotonic() - fresh[1]) * 1000)) >= 120_000):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch inventory is no longer fresh.", {})
        if not containment and not any(
            item["adapter_id"] == binding["adapter_id"] and
            item["candidate_ref"] == binding["candidate_ref"]
            for item in load_current_executor_inventory(current["canonical_projection"])["evidence"]
        ):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch candidate changed.", {})
        session = conn.execute(
            "SELECT s.binding_id,s.workspace_id,s.workspace_binding_id,"
            "s.owner_generation,s.lifecycle_state,s.lease_state,p.semantic_payload AS opening_intent,p.connection_key_id "
            "FROM execution_sessions s LEFT JOIN execution_operations p "
            "ON p.server_id=s.server_id AND p.executor_id=s.executor_id "
            "AND p.operation_id=s.open_operation_id "
            "WHERE s.server_id=? AND s.executor_id=? AND s.session_id=?",
            (server_id, reservation.executor_id, row["session_id"]),
        ).fetchone()
        if (session is None or session["binding_id"] != row["binding_id"] or
                session["workspace_id"] != row["workspace_id"] or
                session["workspace_binding_id"] != row["workspace_binding_id"] or
                session["owner_generation"] !=
                scope["session_owner_generation"] or
                (row["action"] == "runtime.open" and
                 session["lifecycle_state"] != "OPEN_PENDING") or
                (row["action"] != "runtime.open" and
                 (session["lifecycle_state"] != "READY" or
                  session["lease_state"] not in (('ACTIVE', 'REVOKED') if operator_containment else ('ACTIVE',))))):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch session changed.", {})
        opening = json.loads(session['opening_intent']) if session['opening_intent'] else {}
        connection_key = None
        if session["connection_key_id"] is not None and not containment:
            from .execution_connection_keys import require_connection_key
            connection_key = require_connection_key(uow, access=access,
                agent_id=row["subject_agent_id"], endpoint_id=binding["endpoint_id"],
                key_id=session["connection_key_id"])
        mode = opening.get('payload', {}).get('mode')
        if opening.get('action') != 'runtime.open' or mode not in ('managed', 'attach'):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The session has no canonical execution mode.", {})
        if row["action"] == "runtime.open":
            if row["boot_authority_json"] is not None:
                from .execution_boot_authority import require_boot_authority
                require_boot_authority(uow, access=access, agent_id=row["subject_agent_id"],
                    endpoint_id=binding["endpoint_id"], proof=json.loads(row["boot_authority_json"]))
            profile = conn.execute(
                "SELECT enabled,revision,launch_revision FROM runtime_profiles WHERE profile_id=?",
                (binding["profile_id"],),
            ).fetchone() if binding["profile_id"] else None
            if (profile is None or not profile["enabled"] or
                    profile["launch_revision"] != semantic["payload"]["profile_revision"]):
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The dispatch profile changed.", {})
        from ..adapters.outbound.sqlite.execution_leases import SqliteExecutionLeaseRepository
        lease = SqliteExecutionLeaseRepository().effective(uow, scope)
        authority_now = datetime.fromisoformat(access.clock.now_iso().replace("Z", "+00:00"))
        bootstrap = row["action"] == "runtime.open" and lease is None
        if bootstrap and session["lease_state"] != "NONE":
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The initial lease requires reconciliation.", {})
        if not bootstrap and (lease is None or lease["status"] not in
                (('ACTIVE', 'REVOKED') if operator_containment else ('ACTIVE',)) or row["action"] not in
                json.loads(lease["allowed_actions_json"]) or
                lease["applied_at"] is None or lease["scope_json"] is None or
                json.loads(lease["scope_json"]) != scope or
                lease["connection_id"] != binding["owner_instance_id"] or
                lease["connection_generation"] != binding["generation"] or
                lease["authorization_revision"] != scope['authorization_revision'] or
                lease["configuration_revision"] != scope['configuration_revision'] or
                lease["credential_epoch"] != scope['credential_epoch'] or
                lease["owner_generation"] != scope["session_owner_generation"] or
                (not containment and datetime.fromisoformat(lease["valid_until_server"].replace(
                    "Z", "+00:00")) <= authority_now)):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "An applied dispatch lease is required.", {})
        # Lease application does not spend or replace per-operation authority.
        # Revalidate the canonical grant and consume its budget in this same
        # transaction as the RESERVED -> SENDING transition. A lost send ACK
        # cannot spend it a second time by replaying this reservation.
        action = {"runtime.open": "open", "turn.submit": "send", "turn.steer": "steer",
                  "turn.interrupt": "interrupt", "runtime.close": "close",
                  "approval.decide": "send", "input.provide": "send"}.get(row['action'])
        if action is None:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                  "This operation requires governance authorization.", {})
        connection_id = binding["owner_instance_id"] if bootstrap else lease["connection_id"]
        connection_generation = binding["generation"] if bootstrap else lease["connection_generation"]
        if binding['kind'] == 'remote':
            require_execution_lane(uow, scope=scope,
                channel=ExecutionChannel(server_id, reservation.executor_id,
                    connection_id, connection_generation), now=authority_now,
                operator_containment=operator_containment)
        # The operator initiates and remains audited; execution still consumes
        # the represented subject's separately issued canonical grant.
        actor = access.agents.get(uow, row['subject_agent_id'])
        if actor is None or not actor.is_active:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "The dispatch actor is unavailable.", {})
        context = RuntimeRequestContext(
            actor.agent_id, 'agent_key', credential_binding=actor.api_key_hash,
            execution_grant_id=(connection_key["source_grant_id"] if connection_key else None)
                if bootstrap else lease['grant_id'])
        if operator_containment:
            # Revoking productive authority must not prevent an authenticated
            # operator from stopping the exact already-leased session. Keep
            # the applied lease identity and actions; never issue new authority.
            access.authorize(operator_context, action=action, endpoint_id=binding['endpoint_id'],
                represented_agent_id=row['subject_agent_id'], workspace_id=row['workspace_id'],
                substrate=mode, consume=False, check_budget=False, uow=uow)
            grant_id = lease['grant_id']
        else:
            if not native_decision:
                from .execution_operator_authority import consume_recorded_delegation
                consume_recorded_delegation(uow, actor=row['actor_agent_id'], subject=row['subject_agent_id'],
                    guard=provenance[0]['actor_guard_digest'], access=access)
            grant = access.authorize(context, action=action, endpoint_id=binding['endpoint_id'],
                             represented_agent_id=row['subject_agent_id'], workspace_id=row['workspace_id'],
                             substrate=mode, consume=not bootstrap and not native_decision,
                             check_budget=not native_decision, uow=uow)
            if grant is None:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                      "A canonical execution grant is required for dispatch.", {})
            grant_id = grant['grant_id']
        frame = {
            "protocol_major": 1, "contract_revision": R4_PREVIEW_REVISION,
            "type": "operation.submit", **scope, **execution_wire_intent(semantic),
            "operation_id": reservation.operation_id, "intent_hash": row["intent_hash"],
            "connection_id": connection_id,
            "connection_generation": connection_generation,
            "grant_id": grant_id,
        }
        if any(frame.get(name) != value for name, value in scope.items()):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch intent has a different scope.", {})
        try:
            frame = decode_r4_frame(canonical_json(frame))
        except CoreError as exc:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                                  "The dispatch operation is incompatible with the Core contract.", {}) from exc
        phase = "OPEN_AUTHORIZED_PENDING_LEASE" if bootstrap else "LEASE_AUTHORIZED"
        changed = conn.execute(
            "UPDATE execution_dispatch_outbox SET dispatch_state='SENDING',"
            "lease_id=?,lease_serial=?,connection_generation=?,"
            "dispatch_phase=?,dispatch_grant_id=?,dispatch_connection_id=? "
            "WHERE server_id=? AND executor_id=? AND operation_id=? "
            "AND dispatch_state='RESERVED' AND attempt_token=?",
            (None if bootstrap else lease["lease_id"],
             None if bootstrap else lease["lease_serial"],
             connection_generation, phase, grant_id, connection_id, *key,
             reservation.attempt_token),
        ).rowcount
        if changed != 1:
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch attempt changed before send.", {})
        if bootstrap:
            return AuthorizedOpenBootstrap(
                reservation, semantic, connection_generation, connection_id,
                grant_id, scope, frame)
        return AuthorizedDispatch(
            reservation, semantic, lease["lease_id"],
            lease["lease_serial"], lease["connection_generation"],
            lease["connection_id"], lease["grant_id"], scope, frame)
