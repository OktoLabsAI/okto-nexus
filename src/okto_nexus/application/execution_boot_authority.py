"""Durable operator-approved boot authority, valid only for the current owner."""
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError


def require_boot_authority(uow, *, access, agent_id, endpoint_id, context=None, proof=None):
    if proof is not None:
        if (not isinstance(proof, dict) or set(proof) != {"endpoint_id", "revision", "owner_id", "owner_epoch"}
                or proof["endpoint_id"] != endpoint_id):
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Invalid stored boot authority.", {})
        endpoint = access.endpoints.get(uow, endpoint_id)
        if endpoint is None:
            raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "The boot endpoint is unavailable.", {})
        context = RuntimeRequestContext(None, "runtime_boot", represented_agent_id=agent_id,
            workspace_id=endpoint["workspace_id"], endpoint_id=endpoint_id,
            runtime_owner_id=proof["owner_id"], runtime_owner_epoch=proof["owner_epoch"])
    if context is None or context.authentication_source != "runtime_boot" or context.represented_agent_id != agent_id:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Boot owner authority is required.", {})
    access.authorize(context, action="open", endpoint_id=endpoint_id,
                     represented_agent_id=agent_id, uow=uow, audit=False)
    row = uow.connection.execute("SELECT revision FROM runtime_boot_bindings WHERE endpoint_id=?",
                                  (endpoint_id,)).fetchone()
    if row is None or (proof is not None and proof["revision"] != row[0]):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "The boot approval changed.", {})
    return dict(endpoint_id=endpoint_id, revision=row[0], owner_id=context.runtime_owner_id,
                owner_epoch=context.runtime_owner_epoch)
