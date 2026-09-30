"""Durable pre-send R4 dispatch reservations with an independent control lane."""

from __future__ import annotations

from .executor_inventory import load_current_executor_inventory

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import secrets
import time
from typing import Mapping

from ..adapters.outbound.sqlite.connection import ConnectionFactory
from ..adapters.outbound.sqlite.execution_agent_revisions import current_agent_revisions
from ..errors import ErrorCode, OktoNexusError
from .execution_binding_proposals import _agent_guard


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


@dataclass(frozen=True, slots=True)
class AuthorizedDispatch:
    reservation: DispatchReservation
    semantic_intent: dict
    lease_id: str
    lease_serial: int
    connection_generation: int


def reserve_execution_dispatch(
    factory: ConnectionFactory, *, server_id: str, executor_id: str,
    remote_ready: bool, regular_items: int = 4,
    regular_bytes: int = 256 * 1024, control_items: int = 2,
    control_bytes: int = 16 * 1024,
) -> DispatchReservation | None:
    """Reserve one exact row/byte cost before a dispatcher starts a task.

    The write transaction serializes concurrent dispatchers. No network or
    process action occurs here. A crashed reservation stays fenced until a
    separate no-send recovery proves that it can be released.
    """
    if not remote_ready:
        return None
    if (any(type(value) is not int or value <= 0 for value in (
            regular_items, regular_bytes, control_items, control_bytes)) or
            not server_id or not executor_id):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid dispatch capacity.", {})
    with factory.unit_of_work() as uow:
        conn = uow.connection
        used = {"regular": [0, 0], "control": [0, 0]}
        for row in conn.execute(
            "SELECT reservation_class,COUNT(*) AS items,"
            "COALESCE(SUM(reserved_bytes),0) AS bytes FROM "
            "execution_dispatch_outbox WHERE server_id=? AND executor_id=? "
            "AND dispatch_state IN ('RESERVED','SENDING') "
            "GROUP BY reservation_class",
            (server_id, executor_id),
        ):
            if row["reservation_class"] in used:
                used[row["reservation_class"]] = [row["items"], row["bytes"]]
        rows = conn.execute(
            "SELECT o.operation_id,o.attempt_no,p.action,p.semantic_payload "
            "FROM execution_dispatch_outbox o JOIN execution_operations p "
            "ON p.server_id=o.server_id AND p.executor_id=o.executor_id "
            "AND p.operation_id=o.operation_id "
            "WHERE o.server_id=? AND o.executor_id=? "
            "AND o.dispatch_state='PENDING' "
            "AND (o.next_attempt_at IS NULL OR o.next_attempt_at<=?) "
            "AND p.admission_state IN ('ACCEPTED','DISPATCH_PENDING') "
            "ORDER BY CASE WHEN p.action IN ('turn.steer','turn.interrupt',"
            "'runtime.close','approval.decide','input.provide') THEN 0 ELSE 1 END,"
            "p.created_at,p.operation_id LIMIT 32",
            (server_id, executor_id, datetime.now(timezone.utc).isoformat()),
        ).fetchall()
        for row in rows:
            action = row["action"]
            lane = "control" if action in _CONTROL else "regular"
            if action not in _CONTROL | _REGULAR:
                continue
            cost = len(row["semantic_payload"].encode("utf-8"))
            max_items, max_bytes = ((control_items, control_bytes)
                                    if lane == "control" else
                                    (regular_items, regular_bytes))
            if (cost > max_bytes or used[lane][0] >= max_items or
                    used[lane][1] + cost > max_bytes):
                continue
            token = "attempt_" + secrets.token_hex(16)
            now = datetime.now(timezone.utc).isoformat()
            changed = conn.execute(
                "UPDATE execution_dispatch_outbox SET dispatch_state='RESERVED',"
                "attempt_token=?,attempt_no=attempt_no+1,"
                "reservation_class=?,reserved_bytes=?,reserved_at=? "
                "WHERE server_id=? AND executor_id=? AND operation_id=? "
                "AND dispatch_state='PENDING'",
                (token, lane, cost, now, server_id, executor_id,
                 row["operation_id"]),
            ).rowcount
            if changed != 1:
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The dispatch row changed during reservation.", {})
            return DispatchReservation(
                server_id, executor_id, row["operation_id"], token,
                row["attempt_no"] + 1, lane, cost)
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
            "reserved_at=NULL WHERE server_id=? AND executor_id=? "
            "AND operation_id=? AND attempt_token=? AND attempt_no=? "
            "AND dispatch_state='RESERVED' AND reservation_class=? "
            "AND reserved_bytes=?",
            (reservation.server_id, reservation.executor_id,
             reservation.operation_id, reservation.attempt_token,
             reservation.attempt_no, reservation.reservation_class,
             reservation.reserved_bytes),
        ).rowcount
        if changed != 1:
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch reservation is no longer unsent.", {})


def begin_execution_send(
    factory: ConnectionFactory, *, reservation: DispatchReservation,
    remote_ready: bool, fresh_publications: Mapping,
) -> AuthorizedDispatch:
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
            "SELECT o.dispatch_state,o.attempt_token,o.attempt_no,"
            "o.reservation_class,o.reserved_bytes,"
            "p.subject_agent_id,p.actor_agent_id,p.binding_id,p.workspace_id,"
            "p.workspace_binding_id,p.session_id,p.action,p.semantic_payload,"
            "p.expected_revisions_json,p.admission_state "
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
                row["admission_state"] not in {
                    "ACCEPTED", "DISPATCH_PENDING"}):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch reservation changed.", {})
        provenance = conn.execute(
            "SELECT source_guard_digest FROM execution_client_intents "
            "WHERE server_id=? AND actor_agent_id=? AND operation_id=? "
            "AND intent_id GLOB 'r4intent_*'",
            (server_id, row["actor_agent_id"], reservation.operation_id),
        ).fetchall()
        scope = json.loads(row["expected_revisions_json"])
        if (len(provenance) != 1 or
                not provenance[0]["source_guard_digest"] or
                provenance[0]["source_guard_digest"] !=
                _agent_guard(conn, row["subject_agent_id"]) or
                row["actor_agent_id"] != row["subject_agent_id"] or
                scope["authorization_revision"] != revisions.authorization or
                scope["configuration_revision"] != revisions.configuration or
                scope["credential_epoch"] != revisions.credential_epoch):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch authority changed.", {})
        binding = conn.execute(
            "SELECT b.binding_revision,b.inventory_revision,b.candidate_ref,"
            "b.realization_revision,ep.agent_id,ep.adapter_id,ep.protocol,"
            "ep.profile_id,w.workspace_id,w.status AS workspace_status,"
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
            "WHERE b.server_id=? AND b.executor_id=? AND b.binding_id=? "
            "AND b.workspace_binding_id=?",
            (server_id, reservation.executor_id, row["binding_id"],
             row["workspace_binding_id"]),
        ).fetchone()
        if (binding is None or binding["binding_revision"] !=
                scope["binding_revision"] or
                binding["agent_id"] != row["subject_agent_id"] or
                binding["registered_by_agent_id"] != row["subject_agent_id"] or
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
        if (current is None or fresh is None or
                current["inventory_revision"] != binding["inventory_revision"] or
                fresh[0] != current["publication_sequence"] or
                current["observation_age_ms"] +
                max(0, int((time.monotonic() - fresh[1]) * 1000)) >= 120_000):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch inventory is no longer fresh.", {})
        if not any(
            item["adapter_id"] == binding["adapter_id"] and
            item["candidate_ref"] == binding["candidate_ref"]
            for item in load_current_executor_inventory(current["canonical_projection"])["evidence"]
        ):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch candidate changed.", {})
        semantic = json.loads(row["semantic_payload"])
        if semantic["action"] != row["action"]:
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The stored dispatch action changed.", {})
        session = conn.execute(
            "SELECT binding_id,workspace_id,workspace_binding_id,"
            "owner_generation,lifecycle_state,lease_state "
            "FROM execution_sessions WHERE server_id=? AND executor_id=? "
            "AND session_id=?",
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
                  session["lease_state"] != "ACTIVE"))):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch session changed.", {})
        if row["action"] == "runtime.open":
            profile = conn.execute(
                "SELECT enabled,revision FROM runtime_profiles WHERE profile_id=?",
                (binding["profile_id"],),
            ).fetchone() if binding["profile_id"] else None
            if (profile is None or not profile["enabled"] or
                    profile["revision"] != semantic["payload"]["profile_revision"]):
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "The dispatch profile changed.", {})
        lease = conn.execute(
            "SELECT lease_id,lease_serial,connection_generation,"
            "authorization_revision,configuration_revision,"
            "credential_epoch,owner_generation,allowed_actions_json,"
            "valid_until_server FROM execution_leases WHERE server_id=? "
            "AND executor_id=? AND session_id=? AND status='ACTIVE' "
            "ORDER BY lease_serial DESC LIMIT 1",
            (server_id, reservation.executor_id, row["session_id"]),
        ).fetchone()
        if (lease is None or row["action"] not in
                json.loads(lease["allowed_actions_json"]) or
                lease["authorization_revision"] != revisions.authorization or
                lease["configuration_revision"] != revisions.configuration or
                lease["credential_epoch"] != revisions.credential_epoch or
                lease["owner_generation"] != scope["session_owner_generation"] or
                datetime.fromisoformat(lease["valid_until_server"].replace(
                    "Z", "+00:00")) <= datetime.now(timezone.utc)):
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "An applied dispatch lease is required.", {})
        changed = conn.execute(
            "UPDATE execution_dispatch_outbox SET dispatch_state='SENDING',"
            "lease_id=?,lease_serial=?,connection_generation=? "
            "WHERE server_id=? AND executor_id=? AND operation_id=? "
            "AND dispatch_state='RESERVED' AND attempt_token=?",
            (lease["lease_id"], lease["lease_serial"],
             lease["connection_generation"], *key,
             reservation.attempt_token),
        ).rowcount
        if changed != 1:
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "The dispatch attempt changed before send.", {})
        return AuthorizedDispatch(
            reservation, semantic, lease["lease_id"],
            lease["lease_serial"], lease["connection_generation"])
