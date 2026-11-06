"""Pure predicates shared by canonical native commands and attention reads.

All rows, policy, catalog descriptions and time are supplied by the caller.
This module neither authenticates an inbound caller nor reads persistent state.
"""
from datetime import datetime
import hashlib
import json

from nexus_connector_core.protocol import canonical_json

from ..domain.permissions import PermissionSet
from ..domain.tag_selector import reachable
from ..errors import ErrorCode, OktoNexusError


def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def fail(message, code=ErrorCode.CONFLICT, details=None):
    raise OktoNexusError(code, message, details or {})


def runtime_operator(context, actor):
    local = context.trusted_local_operator and context.authentication_source in ('http_loopback', 'operator_session')
    keyed = (context.authentication_source == 'agent_key' and actor and actor.is_active
        and actor.agent_id == 'operator' and context.credential_binding
        and context.credential_binding == actor.api_key_hash)
    return bool(local or keyed)


def authenticate_runtime_facts(context, actor, *, feature_enabled, require_feature=True):
    operator = runtime_operator(context, actor)
    if (require_feature and not feature_enabled) or not (operator or (actor and actor.is_active
            and context.authentication_source == 'agent_key' and context.credential_binding
            and context.credential_binding == actor.api_key_hash)):
        fail('Runtime action is not authorized.', ErrorCode.PERMISSION_DENIED)
    return operator


def runtime_guard_facts(defaults, override, epoch):
    override = override or {}
    return dict(runtime_enabled=bool(override['runtime_enabled'] if override.get('runtime_enabled') is not None
        else defaults['runtime_enabled']), session_policy=override['session_policy']
        if override.get('session_policy') is not None else defaults['session_policy'], epoch=epoch or 0)


def recorded_actor_context(*, actor, subject, guard, current):
    """Interpret committed provenance; this is never inbound authentication."""
    from ..domain.runtime_context import RuntimeRequestContext
    if actor == subject:
        return None, None
    if current is None or not guard:
        fail('The initiating operator authority is unavailable.', ErrorCode.PERMISSION_DENIED)
    if guard.startswith('delegated:'):
        proof = json.loads(guard.removeprefix('delegated:'))
        return RuntimeRequestContext(actor, 'agent_key', credential_binding=current.api_key_hash,
            execution_grant_id=proof['grant_id']), proof
    local = guard.startswith('local-operator:')
    return RuntimeRequestContext(actor, 'http_loopback' if local else 'agent_key',
        trusted_local_operator=local, credential_binding=None if local else current.api_key_hash), None


def agent_guard_facts(*, agent, methods, endpoints, profiles, execution_policy, runtime_policy):
    if agent is None or not agent['is_active']:
        fail('The agent is unavailable.', ErrorCode.PERMISSION_DENIED)
    agent_fields = ('role', 'capabilities', 'metadata', 'api_key_hash', 'is_active',
        'permissions', 'preset_id', 'tags', 'comm_scope', 'color')
    endpoint_fields = ('endpoint_id', 'workspace_id', 'adapter_id', 'protocol', 'contract_version',
        'profile_id', 'enabled', 'activation_state', 'health', 'priority', 'selection_group',
        'consumption', 'response_policy', 'public_config', 'revision')
    profile_fields = ('profile_id', 'adapter_id', 'config', 'secret_refs', 'inherit_ambient', 'enabled', 'revision')
    value = dict(runtime_policy=runtime_policy, execution_policy=[dict(row) for row in execution_policy],
        agent={key: agent[key] for key in agent_fields}, methods=[dict(row) for row in methods],
        endpoints=[{key: row[key] for key in endpoint_fields} for row in endpoints],
        profiles=[{key: row[key] for key in profile_fields} for row in profiles])
    return 'sha256:' + hashlib.sha256(canonical_json(value)).hexdigest()


def effective_lease_facts(latest, previous):
    if latest is None or latest['status'] != 'ISSUED' or json.loads(latest['request_json']).get('purpose') != 'renew':
        return latest
    fields = ('scope_json', 'connection_id', 'connection_generation', 'grant_id',
        'source_grant_revision', 'allowed_actions_json')
    if (previous is not None and previous['lease_serial'] == latest['lease_serial'] - 1
            and previous['status'] == 'ACTIVE' and previous['applied_at'] is not None
            and all(previous[key] == latest[key] for key in fields)):
        return previous
    return latest


def require_lane_facts(*, scope, lane, connection_id, connection_generation, now, operator_containment=False):
    allowed = ('ADMITTED', 'DISCONNECTED') if operator_containment else ('ADMITTED',)
    if (lane is None or lane['state'] not in allowed or lane['agent_id'] != scope['agent_id']
            or lane['connection_id'] != connection_id or lane['connection_generation'] != connection_generation
            or lane['bound_connection_id'] != connection_id or lane['revoked_at'] is not None
            or 'lease:request' not in json.loads(lane['scopes_json'])
            or any(lane[key] != scope[key] for key in ('authorization_revision', 'configuration_revision', 'credential_epoch'))):
        fail('An admitted binding lane with lease authority is required.')
    expires = min(stamp(lane['expires_at']), stamp(lane['ticket_expires_at']))
    if expires <= now:
        fail('The binding lane authority has expired.')
    return expires


def require_location_facts(*, runtime_enabled, host_kinds, policy, adapter_id):
    if not runtime_enabled:
        fail('Runtime is disabled; this agent uses MCP only.', ErrorCode.PERMISSION_DENIED, {'reason': 'RUNTIME_DISABLED'})
    if len(host_kinds) != 1:
        fail('Execution host is not uniquely identified.', ErrorCode.PERMISSION_DENIED)
    local = host_kinds[0] == 'embedded'
    if policy['execution_location'] != ('local' if local else 'remote'):
        fail('Execution host is restricted by the agent policy.', ErrorCode.PERMISSION_DENIED,
            {'reason': 'EXECUTION_LOCATION_RESTRICTED'})
    if local and policy['local_adapter_id'] is not None and policy['local_adapter_id'] != adapter_id:
        fail('Local runtime integration is restricted by the agent policy.', ErrorCode.PERMISSION_DENIED,
            {'reason': 'LOCAL_INTEGRATION_RESTRICTED'})


def native_runtime_enabled(*, enabled, endpoint, represented, method_enabled, profile,
                           descriptor, hitl_enabled, action, session_profile_revision=None, session_id=None):
    from .runtime_requirements import profile_action_allowed, validate_native_requirements_descriptor
    enabled = enabled and represented is not None and represented.is_active and method_enabled
    enabled = enabled and endpoint['enabled'] and endpoint['activation_state'] == 'approved'
    enabled = enabled and endpoint['health'] != 'quarantined'
    if endpoint['profile_id']:
        enabled = enabled and profile is not None and profile['enabled']
        if enabled:
            try:
                validate_native_requirements_descriptor(profile['config'], descriptor, hitl_enabled=hitl_enabled)
            except OktoNexusError:
                enabled = False
            enabled = enabled and profile_action_allowed(profile['config'], action)
        if enabled and session_id:
            enabled = session_profile_revision == profile['revision']
    return bool(enabled)


def grant_candidate_matches(grant, *, context, actor, action, endpoint_id, now, automated=False):
    return not (
        context.execution_grant_id and context.execution_grant_id != grant['grant_id']
        or automated and grant['revision'] != context.handoff_automation.grant_revision
        or endpoint_id and endpoint_id != grant['endpoint_id']
        or grant['credential_binding'] != actor.api_key_hash
        or not grant['no_expiry'] and stamp(grant['expires_at']) <= stamp(now)
        or action != 'access' and action not in grant['actions'])


def grant_candidate_authorized(grant, *, actor, represented, endpoint, profile, action,
                               represented_agent_id, workspace_id, check_budget, consume):
    if action != 'access' and (not endpoint or not endpoint['enabled']
            or endpoint['activation_state'] != 'approved' or grant['endpoint_id'] != endpoint['endpoint_id']):
        return False
    if not represented or not represented.is_active or not reachable(actor, represented):
        return False
    if represented_agent_id and represented_agent_id != grant['represented_agent_id']:
        return False
    if workspace_id and workspace_id != grant['workspace_id']:
        return False
    if endpoint and (endpoint['agent_id'] != grant['represented_agent_id'] or endpoint['workspace_id'] != grant['workspace_id']):
        return False
    if endpoint and endpoint['profile_id'] and (
            not profile or not profile['enabled'] or profile['revision'] != grant['profile_revision']):
        return False
    permission = (('handoffs', 'work') if action == 'execute_work' else
        ('events', 'read') if action in {'read', 'events', 'discover'} else ('messages', 'send_direct'))
    if not PermissionSet(actor.permissions).allows(*permission):
        return False
    return not ((check_budget or consume) and action in {'send', 'steer', 'execute_work'}
        and not grant['unlimited_actions'] and grant['used_executions'] >= grant['max_executions'])


def require_capability_scope_facts(*, scope, revisions, authority):
    if revisions is None or any(revisions[key] != scope[key] for key in (
            'credential_epoch', 'authorization_revision', 'configuration_revision')):
        fail('The session capability revisions changed.')
    row = authority
    if (row is None or not row['is_active'] or not row['api_key_hash']
            or row['lifecycle_state'] not in ('OPEN_PENDING', 'READY') or row['revoked_at'] is not None
            or row['protocol'] != 'nxl-r4' or row['activation_state'] != 'approved' or not row['enabled']
            or row['health'] == 'quarantined' or row['workspace_status'] != 'READY' or row['realization_status'] != 'READY'
            or row['realization_revision'] != row['current_realization_revision']
            or row['agent_id'] != scope['agent_id'] or row['subject_agent_id'] != scope['agent_id']
            or row['binding_id'] != scope['binding_id'] or row['binding_revision'] != scope['binding_revision']
            or row['workspace_id'] != scope['workspace_id']
            or any(row[key] != scope['workspace_binding_id'] for key in (
                'workspace_binding_id', 'binding_workspace_binding_id', 'realization_workspace_binding_id'))
            or row['owner_generation'] != scope['session_owner_generation']
            or json.loads(row['expected_revisions_json']) != scope
            or row['admission_state'] not in ('ACCEPTED', 'DISPATCH_PENDING', 'DISPATCHED', 'RESOLVED_TERMINAL')):
        fail('The session capability authority changed.')


def require_source_guard(expected, actual):
    if expected != actual:
        fail('The session capability authority changed.')


def require_native_live_facts(*, scope, request, session, lease, authority, grant, profile, source, receipt, now):
    if (session is None or session['stream_epoch'] != request['stream_epoch']
            or session['lifecycle_state'] != 'READY' or session['lease_state'] != 'ACTIVE'
            or stamp(request['expires_at']) <= now or request['state'] not in {'PENDING', 'DECIDED'}
            or lease is None or lease['status'] != 'ACTIVE' or lease['applied_at'] is None
            or not lease['scope_json'] or json.loads(lease['scope_json']) != scope
            or stamp(lease['valid_until_server']) <= now or lease['grant_id'] != grant['grant_id']
            or lease['connection_id'] != authority['owner_instance_id']
            or lease['connection_generation'] != authority['generation'] or authority['control_state'] != 'CONTROL_READY'):
        fail('The native request no longer has a live session lease.')
    if profile is not None and 'approvals' in profile['config'].get('disabled_capabilities', ()):
        fail('The session profile does not authorize native decisions.', ErrorCode.PERMISSION_DENIED)
    if (source is None or source['action'] != 'turn.submit' or source['subject_agent_id'] != scope['agent_id']
            or json.loads(source['expected_revisions_json']) != scope or source['admission_state'] == 'RESOLVED_TERMINAL'
            or receipt is not None and receipt['stage'] in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'UNCERTAIN'}):
        fail('The native request turn is no longer active.')
