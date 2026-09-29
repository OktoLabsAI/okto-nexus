"""Durable R4 installation identity; boot does not claim runtime ownership."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
import hashlib
import json

from ....domain.execution.keys import ExecutorKey
from ....errors import ErrorCode, OktoNexusError

from .connection import ConnectionFactory


@dataclass(frozen=True, slots=True)
class ExecutionInstallation:
    server_id: str
    embedded_executor_id: str
    schema_revision: int


@dataclass(frozen=True, slots=True)
class RemoteExecutorRegistration:
    server_id: str
    executor_id: str
    connector_id: str
    intent_id: str
    reused: bool


def ensure_execution_installation(factory: ConnectionFactory) -> ExecutionInstallation:
    """Create the two IDs exactly once under a SQLite write transaction.

    Reboot and concurrent bootstraps read the committed pair. Neither this
    function nor a copied database grants ownership of a Core process.
    """
    with factory.unit_of_work() as uow:
        conn = uow.connection
        row = conn.execute("SELECT server_id,embedded_executor_id,schema_revision "
                           "FROM execution_installation WHERE singleton=1").fetchone()
        if row is None:
            server_id = "srv_" + secrets.token_hex(16)
            executor_id = "exe_" + secrets.token_hex(16)
            conn.execute("INSERT INTO execution_installation(singleton,server_id,"
                         "embedded_executor_id,schema_revision,created_at) "
                         "VALUES (1,?,?,1,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
                         (server_id, executor_id))
            conn.execute("INSERT INTO execution_executors(server_id,executor_id,"
                         "kind,control_state,generation) VALUES (?,?,'embedded',"
                         "'DISCONNECTED',1)", (server_id, executor_id))
            return ExecutionInstallation(server_id, executor_id, 1)
        return ExecutionInstallation(row["server_id"], row["embedded_executor_id"],
                                     row["schema_revision"])


def register_remote_executor(factory: ConnectionFactory, *,
                             actor_agent_id: str, connector_id: str,
                             client_intent_id: str) -> RemoteExecutorRegistration:
    """Idempotently register one remote executor for the authenticated actor.

    This creates identity only. The new executor remains DISCONNECTED with no
    socket owner, lease or authority to run work. The caller supplies the
    authenticated actor from middleware, never an actor claim in JSON.
    """
    from nexus_connector_core.protocol import canonical_json

    for name, value in (("actor_agent_id", actor_agent_id),
                        ("connector_id", connector_id),
                        ("client_intent_id", client_intent_id)):
        if not isinstance(value, str) or not 1 <= len(value) <= 160:
            raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
                                  f"Invalid {name}.", {"field": name})
    body_hash = "sha256:" + hashlib.sha256(canonical_json(
        {"kind": "register_remote_executor", "connector_id": connector_id}
    )).hexdigest()
    with factory.unit_of_work() as uow:
        conn = uow.connection
        installation = conn.execute("SELECT server_id FROM execution_installation "
                                    "WHERE singleton=1").fetchone()
        if installation is None:
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "Execution installation is not initialized.", {})
        server_id = installation["server_id"]
        intent = conn.execute(
            "SELECT body_hash,intent_id,resolved_json FROM execution_client_intents "
            "WHERE server_id=? AND actor_agent_id=? AND client_intent_id=?",
            (server_id, actor_agent_id, client_intent_id),
        ).fetchone()
        if intent is not None:
            if intent["body_hash"] != body_hash:
                raise OktoNexusError(ErrorCode.CONFLICT,
                                      "client_intent_id was used with another body.", {})
            resolved = json.loads(intent["resolved_json"])
            return RemoteExecutorRegistration(server_id, resolved["executor_id"],
                                              connector_id, intent["intent_id"], True)
        existing = conn.execute(
            "SELECT executor_id,registered_by_agent_id FROM execution_executors "
            "WHERE server_id=? AND kind='remote' AND connector_id=?",
            (server_id, connector_id),
        ).fetchone()
        if existing is not None and existing["registered_by_agent_id"] != actor_agent_id:
            raise OktoNexusError(ErrorCode.CONFLICT,
                                  "connector_id belongs to another agent.", {})
        executor_id = (existing["executor_id"] if existing is not None
                       else "exe_" + secrets.token_hex(16))
        ExecutorKey(server_id, executor_id)
        if existing is None:
            conn.execute(
                "INSERT INTO execution_executors(server_id,executor_id,connector_id,"
                "registered_by_agent_id,kind,control_state,generation) "
                "VALUES (?,?,?,?,'remote','DISCONNECTED',1)",
                (server_id, executor_id, connector_id, actor_agent_id),
            )
        intent_id = "intent_" + secrets.token_hex(16)
        resolved = {"server_id": server_id, "executor_id": executor_id,
                    "connector_id": connector_id}
        conn.execute(
            "INSERT INTO execution_client_intents(server_id,actor_agent_id,"
            "client_intent_id,body_hash,intent_id,resolution_revision,resolved_json,created_at) "
            "VALUES (?,?,?,?,?,1,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (server_id, actor_agent_id, client_intent_id, body_hash, intent_id,
             canonical_json(resolved).decode("utf-8")),
        )
        return RemoteExecutorRegistration(server_id, executor_id, connector_id,
                                          intent_id, existing is not None)
