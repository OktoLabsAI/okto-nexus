"""A runtime identity has routing authority on only one execution host."""
from ..errors import ErrorCode, OktoNexusError


def require_identity_host(conn, *, server_id, agent_id, executor_id):
    """Call inside admission's write transaction so concurrent opens serialize.

    Pending and uncertain sessions retain ownership until closed, failed or
    explicitly revoked. Revocation releases routing authority, not process proof.
    """
    owner = conn.execute(
        "SELECT s.executor_id FROM execution_sessions s "
        "JOIN execution_bindings b USING(server_id,executor_id,binding_id) "
        "JOIN agent_endpoints ep ON ep.endpoint_id=b.endpoint_id "
        "WHERE s.server_id=? AND ep.agent_id=? AND s.executor_id<>? "
        "AND s.lifecycle_state NOT IN ('CLOSED','FAILED') AND s.lease_state<>'REVOKED' LIMIT 1",
        (server_id, agent_id, executor_id),
    ).fetchone()
    if owner is not None:
        raise OktoNexusError(
            ErrorCode.CONFLICT,
            "This agent already has a runtime session on another host. Close its sessions before switching hosts.",
            {"reason": "AGENT_RUNTIME_HOST_CONFLICT", "executor_id": owner["executor_id"]},
        )
