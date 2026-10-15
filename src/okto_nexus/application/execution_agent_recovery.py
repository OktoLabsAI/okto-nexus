"""Durable subject readiness, checked in the transaction that admits effects."""
from ..errors import ErrorCode, OktoNexusError


def agent_recovering(conn, server_id, executor_id, agent_id):
    return conn.execute(
        "SELECT 1 FROM execution_agent_recovery r JOIN execution_executors e "
        "USING(server_id,executor_id) WHERE r.server_id=? AND r.executor_id=? "
        "AND r.agent_id=? AND (r.state<>'READY' OR r.generation<>e.generation)",
        (server_id, executor_id, agent_id)).fetchone() is not None


def require_agent_ready(conn, server_id, executor_id, agent_id):
    if agent_recovering(conn, server_id, executor_id, agent_id):
        raise OktoNexusError(ErrorCode.CONFLICT, 'Delivery session requires reconciliation.',
                            {'agent_id': agent_id, 'reason': 'AGENT_RECOVERING'})
