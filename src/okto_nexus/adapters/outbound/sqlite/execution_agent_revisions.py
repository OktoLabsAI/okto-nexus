"""Agent-scoped R4 revisions derived from the current authoritative rows."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import nullcontext
import hashlib
import json

from nexus_connector_core.protocol import canonical_json

from ....errors import ErrorCode, OktoNexusError
from .connection import ConnectionFactory


@dataclass(frozen=True, slots=True)
class AgentExecutionRevisions:
    authorization: int
    configuration: int
    credential_epoch: int


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def current_agent_revisions(factory: ConnectionFactory, *,
                            agent_id: str, uow=None,
                            require_active: bool = True) -> tuple[str, AgentExecutionRevisions, dict]:
    """Advance only changed revision dimensions, scoped to one agent.

    The writer reads the same persisted identity/policy rows used by existing
    auth and connection admission. No global agent scan, provider call or
    filesystem resolution occurs in this short transaction.
    Authorized historical readers may include inactive subjects; authentication
    callers retain the active-only default.
    """
    with nullcontext(uow) if uow is not None else factory.unit_of_work() as uow:
        conn = uow.connection
        installation = conn.execute(
            "SELECT server_id FROM execution_installation WHERE singleton=1"
        ).fetchone()
        agent = conn.execute(
            "SELECT * FROM agents WHERE agent_id=? AND (is_active=1 OR ?)",
            (agent_id, not require_active),
        ).fetchone()
        if installation is None or agent is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND,
                                  "The authenticated agent is unavailable.", {})
        server_id = installation["server_id"]
        methods = [dict(row) for row in conn.execute(
            "SELECT * FROM agent_connection_methods WHERE agent_id=? ORDER BY method",
            (agent_id,),
        )]
        endpoints = [dict(row) for row in conn.execute(
            "SELECT * FROM agent_endpoints WHERE agent_id=? ORDER BY endpoint_id",
            (agent_id,),
        )]
        profiles = [dict(row) for row in conn.execute(
            "SELECT DISTINCT p.* FROM runtime_profiles p JOIN agent_endpoints e "
            "ON e.profile_id=p.profile_id WHERE e.agent_id=? ORDER BY p.profile_id",
            (agent_id,),
        )]
        auth_digest = _digest({
            "permissions": agent["permissions"],
            "comm_scope": agent["comm_scope"],
            "is_active": agent["is_active"],
            "methods": methods,
            "endpoint_gates": [
                {key: row[key] for key in (
                    "endpoint_id", "enabled", "activation_state", "health",
                    "revision", "adapter_id")}
                for row in endpoints
            ],
        })
        config_digest = _digest({
            "metadata": agent["metadata"],
            "capabilities": agent["capabilities"],
            "endpoints": [
                {key: row[key] for key in (
                    "endpoint_id", "workspace_id", "adapter_id", "protocol",
                    "contract_version", "profile_id", "priority",
                    "selection_group", "consumption", "response_policy",
                    "public_config", "revision")}
                for row in endpoints
            ],
            "profiles": [
                {key: row[key] for key in (
                    "profile_id", "adapter_id", "config", "secret_refs",
                    "inherit_ambient", "enabled", "revision")}
                for row in profiles
            ],
        })
        credential_digest = _digest({"api_key_hash": agent["api_key_hash"]})
        old = conn.execute(
            "SELECT * FROM execution_agent_revisions WHERE server_id=? AND agent_id=?",
            (server_id, agent_id),
        ).fetchone()
        if old is None:
            revisions = AgentExecutionRevisions(1, 1, 1)
            conn.execute(
                "INSERT INTO execution_agent_revisions(server_id,agent_id,"
                "authorization_revision,configuration_revision,credential_epoch,"
                "authorization_digest,configuration_digest,credential_digest) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (server_id, agent_id, 1, 1, 1, auth_digest,
                 config_digest, credential_digest),
            )
        else:
            revisions = AgentExecutionRevisions(
                old["authorization_revision"] +
                int(old["authorization_digest"] != auth_digest),
                old["configuration_revision"] +
                int(old["configuration_digest"] != config_digest),
                old["credential_epoch"] +
                int(old["credential_digest"] != credential_digest),
            )
            if (revisions.authorization != old["authorization_revision"] or
                    revisions.configuration != old["configuration_revision"] or
                    revisions.credential_epoch != old["credential_epoch"]):
                conn.execute(
                    "UPDATE execution_agent_revisions SET authorization_revision=?,"
                    "configuration_revision=?,credential_epoch=?,"
                    "authorization_digest=?,configuration_digest=?,credential_digest=? "
                    "WHERE server_id=? AND agent_id=?",
                    (revisions.authorization, revisions.configuration,
                     revisions.credential_epoch, auth_digest, config_digest,
                     credential_digest, server_id, agent_id),
                )
        return server_id, revisions, {
            "permissions": (json.loads(agent["permissions"])
                            if agent["permissions"] else None),
            "metadata": json.loads(agent["metadata"] or "{}"),
        }
