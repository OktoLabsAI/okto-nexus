"""Reviewed renewal delegates to the existing grant issuer, never to a new authority."""
import json
from nexus_connector_core import CoreError

from ..bootstrap.execution_authority import build_execution_access, ExecutionToolDependencies
from ..domain.base import iso_plus
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError
from .connection_setup import SetupTransaction, baseline, require_operator, setup_actor, conflict
from .execution_binding_proposals import _agent_guard
from .execution_local_realizations import _digest
from . import runtime_policy


def normalize_authorization(configuration):
    """Normalize Connector unlimited limits to the internal setup contract."""
    if not isinstance(configuration, dict):
        return configuration
    limits = configuration.get('authorization')
    if not isinstance(limits, dict):
        return configuration
    if set(limits) - {'minutes', 'actions', 'no_expiry', 'unlimited_actions'}:
        raise CoreError('VALIDATION_ERROR', 'connection_configuration')
    normalized = {}
    for name, flag in [('minutes', 'no_expiry'), ('actions', 'unlimited_actions')]:
        if name not in limits:
            raise CoreError('VALIDATION_ERROR', 'connection_configuration')
        value = limits[name]
        if value is not None and type(value) is not int:
            raise CoreError('VALIDATION_ERROR', 'connection_configuration')
        unlimited = value is None or value == 0
        if flag in limits and (type(limits[flag]) is not bool or limits[flag] != unlimited):
            raise CoreError('VALIDATION_ERROR', 'connection_configuration')
        normalized[name] = None if unlimited else value
    return {**configuration, 'authorization': normalized}


def project_actions(conn, agent_id):
    actions = ['open', 'send', 'steer', 'interrupt', 'close']
    if runtime_policy.effective(conn, agent_id)['broadcast_handoff_auto_claim']:
        actions.append('execute_work')
    return actions


def grant_view(row, *, now, credential, profile_revision):
    state = ('revoked' if row['revoked_at'] else
             'superseded' if row['credential_binding'] != credential or row['profile_revision'] != profile_revision else
             'expired' if not row['no_expiry'] and row['expires_at'] <= now else
             'exhausted' if not row['unlimited_actions'] and row['used_executions'] >= row['max_executions'] else 'available')
    return dict(grant_id=row['grant_id'], revision=row['revision'], state=state,
                actions=json.loads(row['actions']), expires_at=None if row['no_expiry'] else row['expires_at'],
                max_executions=None if row['unlimited_actions'] else row['max_executions'],
                used_executions=row['used_executions'])


def snapshot(deps, uow, binding_id):
    rows = uow.connection.execute('SELECT b.* FROM execution_bindings b JOIN execution_installation i '
        'ON i.server_id=b.server_id AND i.singleton=1 WHERE b.binding_id=?', (binding_id,)).fetchall()
    if len(rows) != 1:
        raise conflict('The project connection is no longer unique or available.')
    binding = dict(rows[0])
    access = build_execution_access(deps)
    endpoint = access.endpoints.get(uow, binding['endpoint_id'])
    agent = access.agents.get(uow, endpoint['agent_id']) if endpoint else None
    if not agent or not agent.is_active or not agent.api_key_hash:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'The project identity is unavailable.', {})
    profile = access.endpoints.profile(uow, endpoint['profile_id']) if endpoint['profile_id'] else None
    rows = [dict(row) for row in uow.connection.execute('SELECT * FROM runtime_execution_grants '
        'WHERE actor_agent_id=? AND endpoint_id=? ORDER BY grant_id', (agent.agent_id, endpoint['endpoint_id']))]
    grants = [grant_view(row, now=deps.clock.now_iso(), credential=agent.api_key_hash,
        profile_revision=profile['revision'] if profile else None) for row in rows]
    actions = project_actions(uow.connection, agent.agent_id)
    state = dict(binding=binding, endpoint=endpoint, profile=profile, grants=rows, grant_states=grants,
        agent_guard=_agent_guard(uow.connection, agent.agent_id),
        baseline=baseline(uow, agent.agent_id, binding_id), actions=actions,
        feature_hitl=deps.config.feature_hitl, feature_harness_integrations=deps.config.feature_harness_integrations)
    scope = {key: binding[key] for key in ('server_id', 'executor_id', 'binding_id', 'workspace_binding_id')}
    scope.update(agent_id=agent.agent_id, workspace_id=endpoint['workspace_id'], endpoint_id=endpoint['endpoint_id'])
    return dict(scope=scope, current_grants=grants, expected_revision=_digest(state), actions=actions)


def require_policy(deps, context, uow, current):
    scope = current['scope']
    access = build_execution_access(deps)
    if not runtime_policy.effective(uow.connection, scope['agent_id'])['runtime_enabled']:
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'Runtime execution is disabled by the project policy.', {})
    # Operator authority cannot override a disabled binding, provider or native policy.
    access.authorize(context, action='open', endpoint_id=scope['endpoint_id'],
        represented_agent_id=scope['agent_id'], workspace_id=scope['workspace_id'], uow=uow, audit=False)


def available(current):
    return any(row['state'] == 'available' and set(current['actions']) <= set(row['actions'])
               for row in current['current_grants'])


def review_authorization(deps, context, *, binding_id, client_request_id, minutes=60, max_executions=20):
    if type(minutes) is not int or not 1 <= minutes <= 1440 or type(max_executions) is not int or not 1 <= max_executions <= 1000:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Choose 1..1440 minutes and 1..1000 actions.', {})
    with deps.connection_factory.unit_of_work(write=False) as uow:
        require_operator(build_execution_access(deps), context, uow)
        current = snapshot(deps, uow, binding_id)
        require_policy(deps, context, uow, current)
        grants = sorted(current['current_grants'], key=lambda row: (row['state'] != 'available', row['grant_id']))
        return dict(state='authorization_review', scope=current['scope'], current_grants=grants[:50],
            total_grants=len(grants), has_more_grants=len(grants) > 50,
            can_issue=not available(current), actions=current['actions'],
            request=dict(binding_id=binding_id, client_request_id=client_request_id,
                expected_revision=current['expected_revision'], expires_at=iso_plus(deps.clock.now_iso(), minutes * 60),
                max_executions=max_executions), effects=[
                'Issue one new execution grant for this project identity and connection, with the displayed expiry and action budget.',
                'Eligible authorized Nexus messages may execute within this grant; existing policy and native approvals still apply.',
                'Keep existing grants, bindings and sessions unchanged. This does not resume work or move an old session to the new grant.',
                'For an expired or exhausted session, explicitly close it when appropriate and use work send --new-session to start new work.'])


def receipt(uow, context, request):
    row = uow.connection.execute('SELECT * FROM connection_authorization_receipts '
        'WHERE actor_agent_id=? AND client_request_id=?', (setup_actor(context), request['client_request_id'])).fetchone()
    if row is None:
        return None
    if row['request_hash'] != _digest(request):
        raise conflict('This authorization request ID has different content.')
    result = json.loads(row['result_json'])
    return dict(state='authorization_committed', client_request_id=request['client_request_id'],
                request_hash=row['request_hash'], result=result)


def issue_authorization(deps, context, request, *, recover=False):
    with deps.connection_factory.unit_of_work(write=not recover) as uow:
        require_operator(build_execution_access(deps), context, uow)
        prior = receipt(uow, context, request)
        if prior is not None:
            return prior  # Historical receipt, never re-enable a subsequently revoked grant.
        if recover:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'No committed authorization receipt exists for this request.', {})
        current = snapshot(deps, uow, request['binding_id'])
        if current['expected_revision'] != request['expected_revision']:
            raise conflict('The project authorization changed. Review its current state again.')
        if available(current):
            raise conflict('This project already has an available authorization. No additional grant was issued.')
        require_policy(deps, context, uow, current)
        scope = current['scope']
        access = build_execution_access(ExecutionToolDependencies(deps, SetupTransaction(deps.connection_factory, uow)))
        grant = access.issue(context, actor_agent_id=scope['agent_id'], endpoint_id=scope['endpoint_id'],
            actions=current['actions'], expires_at=request['expires_at'], max_executions=request['max_executions'])
        actor = access.agents.get(uow, scope['agent_id'])
        subject = RuntimeRequestContext(actor.agent_id, 'agent_key', credential_binding=actor.api_key_hash,
                                        execution_grant_id=grant['grant_id'])
        for action in current['actions']:
            access.authorize(subject, action=action, endpoint_id=scope['endpoint_id'],
                represented_agent_id=scope['agent_id'], workspace_id=scope['workspace_id'], uow=uow, audit=False)
        result = dict(scope=scope, grant=grant)
        uow.connection.execute('INSERT INTO connection_authorization_receipts VALUES(?,?,?,?,?)',
            (setup_actor(context), request['client_request_id'], _digest(request), json.dumps(result), deps.clock.now_iso()))
        return receipt(uow, context, request)
