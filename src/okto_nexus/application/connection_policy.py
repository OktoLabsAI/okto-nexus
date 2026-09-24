"""Connection admission policy, independent of an agent's advertised skills."""
from ..domain.permissions import PermissionSet
from ..domain.tag_selector import reachable
from ..errors import ErrorCode, OktoNexusError


def method_enabled(uow, agent_id, method):
    row = uow.connection.execute(
        "SELECT enabled FROM agent_connection_methods WHERE agent_id=? AND method=?",
        (agent_id, method)).fetchone()
    # Compatibility: an operator-approved endpoint remains usable until the
    # operator explicitly configures its agent's method. New methods alone
    # never grant authority: an approved endpoint is still required.
    if row:
        return bool(row[0])
    return method == "mcp" or uow.connection.execute(
        "SELECT 1 FROM agent_endpoints WHERE agent_id=? AND adapter_id=? AND activation_state='approved' LIMIT 1",
        (agent_id, method)).fetchone() is not None


def require_method(uow, agent_id, method):
    if not method_enabled(uow, agent_id, method):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, "Connection method is disabled for this agent.", {})


def valid_connection_key(uow, key_hash, now, endpoint_id=None, *, agents):
    row = uow.connection.execute(
        "SELECT k.* FROM agent_connection_keys k JOIN agents a ON a.agent_id=k.agent_id "
        "JOIN agent_endpoints e ON e.endpoint_id=k.endpoint_id "
        "WHERE k.key_hash=? AND k.revoked_at IS NULL AND (k.expires_at IS NULL OR k.expires_at>?) "
        "AND (k.source_grant_id IS NULL OR EXISTS (SELECT 1 FROM runtime_execution_grants g WHERE g.grant_id=k.source_grant_id "
        "AND g.revoked_at IS NULL AND g.expires_at>? AND g.actor_agent_id=k.agent_id AND g.endpoint_id=k.endpoint_id "
        "AND g.credential_binding=a.api_key_hash)) "
        "AND a.is_active=1 AND e.agent_id=k.agent_id AND e.enabled=1 AND e.activation_state='approved' "
        "AND e.revision=k.endpoint_revision AND e.health<>'quarantined' "
        "AND NOT EXISTS (SELECT 1 FROM agent_connection_methods m WHERE m.agent_id=k.agent_id "
        "AND m.method=e.adapter_id AND m.enabled=0) "
        "AND (e.profile_id IS NULL OR EXISTS (SELECT 1 FROM runtime_profiles p WHERE p.profile_id=e.profile_id "
        "AND p.enabled=1 AND p.revision=k.profile_revision))", (key_hash, now, now)).fetchone()
    if row and (endpoint_id is None or endpoint_id == row['endpoint_id']):
        if row['source_grant_id']:
            actor = agents.get(uow, row['agent_id'])
            if not actor or not PermissionSet(actor.permissions).allows('messages', 'send_direct') or not reachable(actor, actor):
                return None
        return dict(row)
    return None
