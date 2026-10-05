"""Connection admission policy, independent of an agent's advertised skills."""
from ..errors import ErrorCode, OktoNexusError


def method_enabled(uow, agent_id, method):
    if method != "mcp":
        from nexus_connector_core import get_runtime_catalog
        if method not in {item.adapter_id for item in get_runtime_catalog().runtimes}:
            return False
    row = uow.connection.execute(
        "SELECT enabled FROM agent_connection_methods WHERE agent_id=? AND method=?",
        (agent_id, method)).fetchone()
    # Compatibility: an operator-approved endpoint remains usable until the
    # operator explicitly configures its agent's method. New methods alone
    # never grant authority: an approved endpoint is still required.
    if row:
        return bool(row[0])
    return method == "mcp" or uow.connection.execute(
        "SELECT 1 FROM agent_endpoints WHERE agent_id=? AND adapter_id=? AND protocol='nxl-r4' AND activation_state='approved' LIMIT 1",
        (agent_id, method)).fetchone() is not None


def require_method(uow, agent_id, method):
    if not method_enabled(uow, agent_id, method):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Connection method is disabled for this agent.", {})


def valid_connection_key(uow, key_hash, now, endpoint_id=None, *, agents):
    # Old scoped opening credentials cannot activate a retained connection.
    return None
