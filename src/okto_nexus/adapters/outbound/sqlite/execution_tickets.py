"""Hashed, audience-bound R4 link tickets for one executor and agent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets

from nexus_connector_core.protocol import canonical_json

from ....errors import ErrorCode, OktoNexusError
from .connection import ConnectionFactory
from .execution_agent_revisions import current_agent_revisions


AUDIENCE = "nexus-executor-control"
BOOTSTRAP_SCOPES = frozenset({
    "link:connect", "inventory:publish", "realization:publish",
})
_ALL_SCOPES = frozenset({
    "link:connect", "lane:attach", "inventory:publish",
    "realization:publish", "receipt:publish", "history:read",
    "lease:request",
})


@dataclass(frozen=True, slots=True)
class IssuedExecutionTicket:
    ticket_id: str
    ticket: str
    executor_id: str
    binding_id: str | None
    agent_id: str
    expires_in: int
    credential_epoch: int
    authorization_revision: int
    audience: str
    scopes: tuple[str, ...]

    def public_dict(self) -> dict:
        return {"ticket_id": self.ticket_id, "ticket": self.ticket,
                "executor_id": self.executor_id, "binding_id": self.binding_id,
                "agent_id": self.agent_id, "expires_in": self.expires_in,
                "credential_epoch": self.credential_epoch,
                "authorization_revision": self.authorization_revision,
                "audience": self.audience, "scopes": list(self.scopes)}


@dataclass(frozen=True, slots=True)
class VerifiedExecutionTicket:
    ticket_id: str
    server_id: str
    executor_id: str
    binding_id: str | None
    agent_id: str
    scopes: frozenset[str]
    credential_epoch: int
    authorization_revision: int


class TicketRequestConflict(Exception):
    """Scoped request metadata that can be returned without ticket material."""

    def __init__(self, code: str, ticket_id: str, message: str):
        super().__init__(message)
        self.code = code
        self.ticket_id = ticket_id


def _hash(ticket: str) -> str:
    return "sha256:" + hashlib.sha256(ticket.encode("utf-8")).hexdigest()


def issue_execution_ticket(factory: ConnectionFactory, *, server_id: str,
                           executor_id: str, agent_id: str,
                           scopes: frozenset[str] = BOOTSTRAP_SCOPES,
                           binding_id: str | None = None,
                           expires_in: int = 600,
                           now: datetime | None = None,
                           client_intent_id: str | None = None,
                           credential_request_id: str | None = None,
                           replaces_ticket_id: str | None = None,
                           ) -> IssuedExecutionTicket:
    """Issue a random ticket after checking its canonical actor and target."""
    if (not isinstance(expires_in, int) or isinstance(expires_in, bool) or
            not 1 <= expires_in <= 600 or not scopes or
            not scopes <= _ALL_SCOPES):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid ticket scope or duration.", {})
    if binding_id is None and scopes != BOOTSTRAP_SCOPES:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                              "A binding is required for this ticket scope.", {})
    request_fields = (client_intent_id, credential_request_id)
    if any(value is not None for value in (*request_fields, replaces_ticket_id)):
        if (binding_id is None or any(
                not isinstance(value, str) or not 1 <= len(value) <= 160
                for value in request_fields) or
                (replaces_ticket_id is not None and
                 (not isinstance(replaces_ticket_id, str) or
                  not 1 <= len(replaces_ticket_id) <= 160))):
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                                  "Invalid binding ticket request identity.", {})
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    actual_server_id, revisions, _ = current_agent_revisions(
        factory, agent_id=agent_id)
    if actual_server_id != server_id:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                              "The ticket target belongs to another server.", {})
    ticket_id = "ept_" + secrets.token_hex(16)
    ticket = "nxt4_" + secrets.token_urlsafe(36)
    ordered_scopes = tuple(sorted(scopes))
    with factory.unit_of_work() as uow:
        conn = uow.connection
        target = conn.execute(
            "SELECT kind,registered_by_agent_id,revoked_at FROM execution_executors "
            "WHERE server_id=? AND executor_id=?",
            (server_id, executor_id),
        ).fetchone()
        if (target is None or target["kind"] != "remote" or
                target["revoked_at"] is not None or
                (binding_id is None and
                 target["registered_by_agent_id"] != agent_id)):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                  "The executor is unavailable to this agent.", {})
        if binding_id is not None:
            binding = conn.execute(
                "SELECT 1 FROM execution_bindings b JOIN agent_endpoints ep "
                "ON ep.endpoint_id=b.endpoint_id WHERE b.server_id=? AND "
                "b.executor_id=? AND b.binding_id=? AND ep.agent_id=?",
                (server_id, executor_id, binding_id, agent_id),
            ).fetchone()
            if binding is None:
                raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                      "The binding is unavailable to this executor.", {})
        agent = conn.execute(
            "SELECT api_key_hash,is_active FROM agents WHERE agent_id=?",
            (agent_id,),
        ).fetchone()
        if agent is None or not agent["is_active"] or not agent["api_key_hash"]:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                  "The agent has no active canonical key.", {})
        if credential_request_id is not None:
            prior = conn.execute(
                "SELECT ticket_id,client_intent_id,scopes_json,"
                "requested_duration_seconds,replaces_ticket_id FROM "
                "execution_link_tickets WHERE server_id=? AND executor_id=? "
                "AND binding_id=? AND agent_id=? AND credential_request_id=?",
                (server_id, executor_id, binding_id, agent_id,
                 credential_request_id),
            ).fetchone()
            if prior is not None:
                if (prior["client_intent_id"] != client_intent_id or
                        prior["scopes_json"] != canonical_json(
                            list(ordered_scopes)).decode("utf-8") or
                        prior["requested_duration_seconds"] != expires_in or
                        prior["replaces_ticket_id"] != replaces_ticket_id):
                    raise OktoNexusError(ErrorCode.CONFLICT,
                                          "The credential request ID has different content.", {})
                raise TicketRequestConflict(
                    "CREDENTIAL_MATERIAL_UNAVAILABLE", prior["ticket_id"],
                    "Ticket material is unavailable after its first response.")
            active = conn.execute(
                "SELECT ticket_id FROM execution_link_tickets WHERE server_id=? "
                "AND executor_id=? AND binding_id=? AND agent_id=? AND "
                "audience=? AND revoked_at IS NULL AND expires_at>? "
                "ORDER BY expires_at DESC LIMIT 1",
                (server_id, executor_id, binding_id, agent_id,
                 AUDIENCE, instant.isoformat()),
            ).fetchone()
            if active is not None and replaces_ticket_id is None:
                raise TicketRequestConflict(
                    "CREDENTIAL_REPLACEMENT_REQUIRED", active["ticket_id"],
                    "An active ticket must be replaced explicitly.")
            if active is not None and replaces_ticket_id != active["ticket_id"]:
                raise TicketRequestConflict(
                    "CREDENTIAL_REPLACEMENT_REQUIRED", active["ticket_id"],
                    "The current active ticket must be replaced explicitly.")
            if replaces_ticket_id is not None:
                replaced = conn.execute(
                    "SELECT ticket_id,client_intent_id,bound_connection_id,"
                    "revoked_at,expires_at,scopes_json,credential_epoch,"
                    "authorization_revision,requested_duration_seconds "
                    "FROM execution_link_tickets WHERE "
                    "ticket_id=? AND server_id=? AND executor_id=? AND "
                    "binding_id=? AND agent_id=? AND audience=?",
                    (replaces_ticket_id, server_id, executor_id,
                     binding_id, agent_id, AUDIENCE),
                ).fetchone()
                if (replaced is None or replaced["revoked_at"] is not None or
                        replaced["bound_connection_id"] is not None or
                        replaced["client_intent_id"] != client_intent_id or
                        replaced["expires_at"] <= instant.isoformat() or
                        replaced["scopes_json"] != canonical_json(
                            list(ordered_scopes)).decode("utf-8") or
                        replaced["credential_epoch"] != revisions.credential_epoch or
                        replaced["authorization_revision"] != revisions.authorization or
                        replaced["requested_duration_seconds"] != expires_in):
                    raise OktoNexusError(ErrorCode.CONFLICT,
                                          "The prior ticket cannot be replaced.", {})
                conn.execute(
                    "UPDATE execution_link_tickets SET revoked_at=? WHERE ticket_id=?",
                    (instant.isoformat(), replaces_ticket_id),
                )
        if binding_id is None:
            # A lost registration response may be retried with the same
            # intent. The successor replaces the old bootstrap credential;
            # no second long-lived route to this executor is accumulated.
            conn.execute(
                "UPDATE execution_link_tickets SET revoked_at=? WHERE "
                "server_id=? AND executor_id=? AND agent_id=? AND "
                "binding_id IS NULL AND audience=? AND revoked_at IS NULL",
                (instant.isoformat(), server_id, executor_id, agent_id, AUDIENCE),
            )
        conn.execute(
            "INSERT INTO execution_link_tickets(ticket_id,secret_hash,server_id,"
            "executor_id,binding_id,agent_id,audience,scopes_json,credential_epoch,"
            "authorization_revision,expires_at,client_intent_id,"
            "credential_request_id,replaces_ticket_id,requested_duration_seconds) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ticket_id, _hash(ticket), server_id, executor_id, binding_id,
             agent_id, AUDIENCE, canonical_json(list(ordered_scopes)).decode("utf-8"),
             revisions.credential_epoch, revisions.authorization,
             (instant + timedelta(seconds=expires_in)).isoformat(),
             client_intent_id, credential_request_id, replaces_ticket_id,
             expires_in if credential_request_id is not None else None),
        )
    return IssuedExecutionTicket(
        ticket_id, ticket, executor_id, binding_id, agent_id, expires_in,
        revisions.credential_epoch, revisions.authorization, AUDIENCE,
        ordered_scopes,
    )


def verify_execution_ticket(factory: ConnectionFactory, *, ticket: str,
                            server_id: str, executor_id: str, scope: str,
                            binding_id: str | None = None,
                            now: datetime | None = None) -> VerifiedExecutionTicket:
    """Reject wrong audience, scope, namespace, revocation and stale epochs."""
    if (not isinstance(ticket, str) or not ticket.startswith("nxt4_") or
            not 32 <= len(ticket) <= 4096 or scope not in _ALL_SCOPES):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                              "The execution ticket is invalid.", {})
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    with factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute(
            "SELECT t.*,e.revoked_at AS executor_revoked_at,"
            "e.registered_by_agent_id,ep.agent_id AS binding_agent_id "
            "FROM execution_link_tickets t "
            "JOIN execution_executors e ON e.server_id=t.server_id AND "
            "e.executor_id=t.executor_id LEFT JOIN execution_bindings b ON "
            "b.server_id=t.server_id AND b.executor_id=t.executor_id AND "
            "b.binding_id=t.binding_id LEFT JOIN agent_endpoints ep ON "
            "ep.endpoint_id=b.endpoint_id WHERE t.secret_hash=?",
            (_hash(ticket),),
        ).fetchone()
        if (row is None or row["server_id"] != server_id or
                row["executor_id"] != executor_id or
                row["binding_id"] != binding_id or
                row["audience"] != AUDIENCE or row["revoked_at"] is not None or
                row["executor_revoked_at"] is not None or
                (binding_id is None and
                 row["registered_by_agent_id"] != row["agent_id"]) or
                (binding_id is not None and
                 row["binding_agent_id"] != row["agent_id"])):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                  "The execution ticket is invalid for this target.", {})
        expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        scopes = frozenset(json.loads(row["scopes_json"]))
        if expires.tzinfo is None or expires <= instant or scope not in scopes:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                  "The execution ticket is expired or out of scope.", {})
        agent_id = row["agent_id"]
        epoch = row["credential_epoch"]
        authorization = row["authorization_revision"]
        ticket_id = row["ticket_id"]
    current_server_id, revisions, _ = current_agent_revisions(
        factory, agent_id=agent_id)
    if (current_server_id != server_id or revisions.credential_epoch != epoch or
            revisions.authorization != authorization):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                              "The execution ticket has stale authority.", {})
    return VerifiedExecutionTicket(ticket_id, server_id, executor_id,
                                   binding_id, agent_id, scopes, epoch,
                                   authorization)


def verify_execution_history_ticket(factory: ConnectionFactory, *, ticket: str,
                                    server_id: str, operation_id: str
                                    ) -> VerifiedExecutionTicket:
    """Resolve a history ticket only through its own admitted operation."""
    if (not isinstance(ticket, str) or not ticket.startswith("nxt4_") or
            not 32 <= len(ticket) <= 4096):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                              "The execution ticket is invalid.", {})
    with factory.unit_of_work(write=False) as uow:
        target = uow.connection.execute(
            "SELECT t.executor_id,t.binding_id FROM execution_link_tickets t "
            "JOIN execution_operations o ON o.server_id=t.server_id AND "
            "o.executor_id=t.executor_id AND o.binding_id=t.binding_id AND "
            "o.subject_agent_id=t.agent_id WHERE t.secret_hash=? AND "
            "t.server_id=? AND o.operation_id=?",
            (_hash(ticket), server_id, operation_id),
        ).fetchone()
    if target is None:
        raise OktoNexusError(ErrorCode.NOT_FOUND,
                              "The operation was not found in this ticket scope.", {})
    return verify_execution_ticket(
        factory, ticket=ticket, server_id=server_id,
        executor_id=target["executor_id"], binding_id=target["binding_id"],
        scope="history:read",
    )
