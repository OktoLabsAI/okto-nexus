"""Revalidate limited bootstrap authority without promoting it to an agent key."""
from .connection_policy import valid_connection_key
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError


def require_connection_key(uow, *, access, agent_id, endpoint_id, key_id=None, key_hash=None):
    if key_id is not None:
        row = uow.connection.execute(
            "SELECT key_hash FROM agent_connection_keys WHERE key_id=?", (key_id,)).fetchone()
        key_hash = row[0] if row else None
    key = valid_connection_key(uow, key_hash, access.clock.now_iso(), endpoint_id,
                               agents=access.agents) if key_hash else None
    if key is None or key["agent_id"] != agent_id:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED,
            "The opening connection credential is no longer valid.", {})
    context = RuntimeRequestContext(agent_id, "connection_key", credential_binding=key_hash,
                                    endpoint_id=endpoint_id)
    access.authorize(context, action="open", endpoint_id=endpoint_id,
                     represented_agent_id=agent_id, uow=uow, audit=False)
    return key
