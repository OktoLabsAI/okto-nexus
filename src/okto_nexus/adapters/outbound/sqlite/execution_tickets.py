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
BOOTSTRAP_SCOPES = frozenset({"link:connect", "inventory:publish"})
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


def _hash(ticket: str) -> str:
    return "sha256:" + hashlib.sha256(ticket.encode("utf-8")).hexdigest()


def issue_execution_ticket(factory: ConnectionFactory, *, server_id: str,
                           executor_id: str, agent_id: str,
                           scopes: frozenset[str] = BOOTSTRAP_SCOPES,
                           binding_id: str | None = None,
                           expires_in: int = 600,
                           now: datetime | None = None) -> IssuedExecutionTicket:
    """Issue a random ticket after checking its canonical actor and target."""
    if (not isinstance(expires_in, int) or isinstance(expires_in, bool) or
            not 1 <= expires_in <= 600 or not scopes or
            not scopes <= _ALL_SCOPES):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                              "Invalid ticket scope or duration.", {})
    if binding_id is None and scopes != BOOTSTRAP_SCOPES:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                              "A binding is required for this ticket scope.", {})
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
                target["registered_by_agent_id"] != agent_id or
                target["revoked_at"] is not None):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
                                  "The executor is unavailable to this agent.", {})
        if binding_id is not None:
            binding = conn.execute(
                "SELECT 1 FROM execution_bindings WHERE server_id=? AND "
                "executor_id=? AND binding_id=?",
                (server_id, executor_id, binding_id),
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
            "authorization_revision,expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ticket_id, _hash(ticket), server_id, executor_id, binding_id,
             agent_id, AUDIENCE, canonical_json(list(ordered_scopes)).decode("utf-8"),
             revisions.credential_epoch, revisions.authorization,
             (instant + timedelta(seconds=expires_in)).isoformat()),
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
            "e.registered_by_agent_id FROM execution_link_tickets t "
            "JOIN execution_executors e ON e.server_id=t.server_id AND "
            "e.executor_id=t.executor_id WHERE t.secret_hash=?",
            (_hash(ticket),),
        ).fetchone()
        if (row is None or row["server_id"] != server_id or
                row["executor_id"] != executor_id or
                row["binding_id"] != binding_id or
                row["audience"] != AUDIENCE or row["revoked_at"] is not None or
                row["executor_revoked_at"] is not None or
                (binding_id is None and
                 row["registered_by_agent_id"] != row["agent_id"])):
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
