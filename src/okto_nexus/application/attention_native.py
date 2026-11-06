"""Native attention classification over explicitly supplied canonical facts."""
from types import SimpleNamespace
import json

from ..domain.attention import occurrence
from ..domain.runtime_context import RuntimeRequestContext
from ..errors import ErrorCode, OktoNexusError
from .execution_native_facts import (
    agent_guard_facts, authenticate_runtime_facts, effective_lease_facts, fail,
    grant_candidate_authorized, grant_candidate_matches, native_runtime_enabled,
    recorded_actor_context, require_capability_scope_facts, require_lane_facts,
    require_location_facts, require_native_live_facts, require_source_guard,
    runtime_guard_facts, runtime_operator, stamp,
)
from .execution_native_recipient import native_permission, recipient_from_facts


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def _agent(data):
    if not data or not data.get('agent'):
        return None
    value = dict(data['agent'])
    for key in ('permissions', 'tags', 'comm_scope'):
        value[key] = _json(value[key])
    return SimpleNamespace(**value)


def _guard(data, policy):
    return agent_guard_facts(agent=data['agent'], methods=data['methods'], endpoints=data['endpoints'],
        profiles=data['profiles'], execution_policy=data['execution_policy'],
        runtime_policy=runtime_guard_facts(policy['runtime_defaults'], data['runtime_override'], data['runtime_epoch']))


def _profile(raw):
    return dict(raw, config=_json(raw['config'])) if raw else None


def _policy_value(policy, key, *, required=True):
    """Defer a policy-only refusal while authority examines independent gates.

    Ordinary native projection remains strict. Authority supplies a private
    collector and emits these refusals only if the other predicates authorize.
    This never grants permission to a command or mutates the supplied snapshot.
    """
    value = bool(policy[key])
    denials = policy.get('_policy_denials')
    if denials is not None and value != required:
        denials.add(key)
        return required
    return value


def _profile_hitl(policy, profile, descriptor):
    from .runtime_requirements import native_requirement_schema
    if profile and descriptor and profile['config'].get('required_native_requests'):
        schema = native_requirement_schema(descriptor.native_kind,
            'stream' if descriptor.native_kind == 'claude_code' else None)
        if schema.get('requires_feature_hitl'):
            return _policy_value(policy, 'feature_hitl')
    return policy['feature_hitl']


def _runtime_grant(runtime, actor_data, *, action, grant_id, scope, now, policy, check_budget=False):
    if policy['admission_closed']:
        fail('Runtime shutdown is in progress; new work is not accepted.', details={'reason': 'RUNTIME_DRAINING'})
    if not runtime or not runtime['endpoint'] or runtime['endpoint']['protocol'] != 'nxl-r4':
        fail('Runtime action is not authorized.', ErrorCode.PERMISSION_DENIED)
    endpoint, actor = runtime['endpoint'], _agent(actor_data)
    subject_data = runtime['represented']
    represented = _agent(subject_data)
    descriptor_data = policy['catalog'].get(endpoint['adapter_id'])
    descriptor = SimpleNamespace(**descriptor_data) if descriptor_data else None
    enabled = descriptor is not None and _policy_value(policy, 'feature_harness_integrations') and descriptor.connection_mode != 'attach'
    if len(runtime['binding_executors']) != 1:
        fail('Runtime action is not authorized.', ErrorCode.PERMISSION_DENIED)
    selected_policy = (subject_data['execution_policy'] or [dict(execution_location='local', local_adapter_id=None)])[0]
    require_location_facts(runtime_enabled=runtime_guard_facts(policy['runtime_defaults'],
        subject_data['runtime_override'], subject_data['runtime_epoch'])['runtime_enabled'],
        host_kinds=runtime['host_kinds'], policy=selected_policy, adapter_id=endpoint['adapter_id'])
    profile = _profile(runtime['profile'])
    method = next((row for row in subject_data['methods'] if row['method'] == endpoint['adapter_id']), None)
    enabled = native_runtime_enabled(enabled=enabled, endpoint=endpoint, represented=represented,
        method_enabled=method is None or bool(method['enabled']), profile=profile,
        descriptor=descriptor, hitl_enabled=_profile_hitl(policy, profile, descriptor), action=action)
    context = RuntimeRequestContext(actor.agent_id if actor else None, 'agent_key',
        credential_binding=actor.api_key_hash if actor else None, execution_grant_id=grant_id)
    if enabled and runtime_operator(context, actor) and not grant_id:
        return None
    if not enabled or not actor or not actor.is_active or not actor.api_key_hash:
        fail('Runtime action is not authorized.', ErrorCode.PERMISSION_DENIED)
    candidates = [dict(row, actions=_json(row['actions'])) for row in runtime['grants']
        if row['actor_agent_id'] == actor.agent_id and row['revoked_at'] is None]
    candidates.sort(key=lambda row: row['grant_id'])
    if action == 'open' and not grant_id:
        candidates.sort(key=lambda row: not set(row['actions']) & {'send', 'steer', 'execute_work'}
            or not row['unlimited_actions'] and row['used_executions'] >= row['max_executions'])
    for grant in candidates:
        if not grant_candidate_matches(grant, context=context, actor=actor, action=action,
                endpoint_id=endpoint['endpoint_id'], now=now):
            continue
        if grant_candidate_authorized(grant, actor=actor,
                represented=represented if grant['represented_agent_id'] == represented.agent_id else None,
                endpoint=endpoint, profile=profile, action=action, represented_agent_id=scope['agent_id'],
                workspace_id=scope.get('workspace_id'), check_budget=check_budget, consume=False):
            return grant
    fail('Runtime action is not authorized.', ErrorCode.PERMISSION_DENIED)


def _recorded_operator(facts, policy, now):
    authority, scope = facts['authority'], facts['request']['scope']
    actor, guard = authority['actor_agent_id'], authority['actor_guard_digest']
    data = facts['initiator']
    current = _agent(data)
    context, proof = recorded_actor_context(actor=actor, subject=scope['agent_id'], guard=guard, current=current)
    if context is None:
        return
    is_operator = authenticate_runtime_facts(context, current,
        feature_enabled=_policy_value(policy, 'feature_harness_integrations'))
    if proof is not None and not is_operator and proof['action'] == 'turn.submit' and proof['binding_id']:
        runtime = facts['delegated_runtime']
        if not runtime or runtime['recipient_binding_count'] != 1:
            fail('Delegated binding is unavailable.', ErrorCode.PERMISSION_DENIED)
        # require_operator_request does not constrain workspace for its recorded
        # delegation check; endpoint/grant still have to agree on workspace.
        grant = _runtime_grant(runtime, data, action='send', grant_id=proof['grant_id'],
            scope=dict(agent_id=scope['agent_id']), now=now, policy=policy)
        if grant is None:
            fail('An explicit execution grant is required.', ErrorCode.PERMISSION_DENIED)
        actual = 'delegated:' + json.dumps(dict(actor_guard=_guard(data, policy), grant_id=grant['grant_id'],
            grant_revision=grant['revision'], binding_id=proof['binding_id'],
            endpoint_id=runtime['endpoint']['endpoint_id'], action=proof['action']), sort_keys=True, separators=(',', ':'))
    else:
        if not is_operator:
            fail('Representing another agent requires an authenticated operator.', ErrorCode.PERMISSION_DENIED)
        local = context.authentication_source in ('http_loopback', 'operator_session')
        if local and (actor != 'operator' or not context.trusted_local_operator):
            fail('The local operator is unavailable.', ErrorCode.PERMISSION_DENIED)
        actual = ('local-operator:' if local else '') + _guard(data, policy)
    if actual != guard:
        fail('The initiating operator authority changed.')


def require_live(facts, now, policy):
    """Pure equivalent of the full canonical native liveness dependency chain."""
    if not _policy_value(policy, 'feature_hitl'):
        fail('Native decision dispatch is disabled.', ErrorCode.PERMISSION_DENIED)
    request, authority = facts['request'], facts['authority']
    scope = request['scope']
    if facts['contained']:
        fail('This session requires confirmed resource release before accepting more work.')
    if facts['recovering']:
        fail('Delivery session requires reconciliation.', details={'agent_id': scope['agent_id'], 'reason': 'AGENT_RECOVERING'})
    require_capability_scope_facts(scope=scope, revisions=facts['revisions'], authority=authority)
    require_source_guard(authority['source_guard_digest'], _guard(facts['subject'], policy))
    _recorded_operator(facts, policy, now)
    semantic = _json(authority['semantic_payload'])
    if semantic['action'] != 'runtime.open':
        fail('A canonical opening operation is required.')
    # The payload mode is part of the original canonical call contract, although
    # native adapter descriptors ultimately select the supported substrate.
    semantic['payload']['mode']
    grant = _runtime_grant(facts['runtime'], facts['subject'], action='open',
        grant_id=authority['dispatch_grant_id'], scope=scope, now=now, policy=policy)
    if grant is None or not grant['no_expiry'] and stamp(grant['expires_at']) <= stamp(now):
        fail('A current session execution grant is required.', ErrorCode.PERMISSION_DENIED)
    lease = effective_lease_facts(facts['latest_lease'], facts['previous_lease'])
    require_native_live_facts(scope=scope, request=request, session=facts['session'], lease=lease,
        authority=authority, grant=grant, profile=_profile(facts['runtime']['profile']),
        source=facts['source'], receipt=facts['receipt'], now=stamp(now))
    if authority['kind'] == 'remote':
        require_lane_facts(scope=scope, lane=facts['lane'], connection_id=lease['connection_id'],
            connection_generation=lease['connection_generation'], now=stamp(now))
    _runtime_grant(facts['runtime'], facts['subject'], action='send', grant_id=grant['grant_id'],
        scope=scope, now=now, policy=policy)
    return scope


def _next_change(facts, now):
    """A live action must be reconsidered at its earliest authority deadline."""
    deadlines = [facts['request']['expires_at']]
    lease = effective_lease_facts(facts['latest_lease'], facts['previous_lease'])
    if lease is not None:
        deadlines.append(lease['valid_until_server'])
    lane = facts['lane']
    if lane is not None:
        deadlines.extend((lane['expires_at'], lane['ticket_expires_at']))
    for runtime in (facts['runtime'], facts['delegated_runtime']):
        if runtime is not None:
            deadlines.extend(row['expires_at'] for row in runtime['grants'] if not row['no_expiry'])
    future = [value for value in deadlines if value is not None and stamp(value) > stamp(now)]
    return min(future, key=stamp) if future else None


def project(facts, now, policy):
    request, approval = facts['request'], facts['approval']
    scope = request['scope']
    permission = native_permission(request['kind'], request['method'],
        {'codex_approval_kind': request['approval_kind']})
    source = facts['source']
    recipient = recipient_from_facts(permission=permission,
        source_exists=source is not None and source['action'] == 'turn.submit',
        source_actor=source['actor_agent_id'] if source else None,
        domain_link_exists=facts['domain_link_exists'], domain_sender=facts['domain_sender'])
    archived_at = approval.get('archived_at') if approval else None
    resolved = bool(archived_at) or request['state'] in ('DECIDED', 'STALE')
    expired = not resolved and (request['state'] == 'EXPIRED' or stamp(request['expires_at']) <= stamp(now))
    resolution = 'resolved' if resolved else 'expired' if expired else 'open'
    historical_recipient = approval.get('recipient_agent_id') if approval else None
    classification_recipient = recipient if recipient is not None or resolution == 'open' else historical_recipient
    kind = ('native_permission_pending' if permission else
        'native_question_pending' if classification_recipient == 'operator' else 'question_waiting_for_agent')
    live, reason = False, None
    if resolution == 'open' and request['state'] == 'PENDING' and approval and approval['status'] == 'pending':
        try:
            require_live(facts, now, policy)
            live = True
        except OktoNexusError as error:
            reason = str(error.code)
    actionable = False
    if live and recipient == 'operator' and policy['viewer_is_operator'] and policy['viewer_actor'] == 'operator':
        try:
            _guard(facts['operator'], policy)
            actionable = True
        except OktoNexusError:
            reason = 'APPROVAL_AUTHORITY_REQUIRED'
    actions = ['inspect_approval'] if approval else []
    if actionable:
        actions.append('decide_native' if permission else 'respond_native')
    changed = request['received_at']
    if approval and approval['decided_at'] and stamp(approval['decided_at']) > stamp(changed):
        changed = approval['decided_at']
    if archived_at and stamp(archived_at) > stamp(changed):
        changed = archived_at
    if expired and stamp(request['expires_at']) > stamp(changed):
        changed = request['expires_at']
    revision = dict(request=request['request_revision'], request_state=request['state'], resolution=resolution,
        approval_revision=approval['decision_revision'] if approval else None,
        approval_status=approval['status'] if approval else None, archived_at=archived_at,
        recipient=recipient, live=live, reason=reason)
    return [occurrence(kind=kind, source_type='execution_native_request', source_id=request['canonical_request_id'],
        episode=request['request_revision'], source_revision=revision, first_detected_at=request['received_at'],
        last_changed_at=changed, agent_id=scope['agent_id'], workspace_id=scope['workspace_id'],
        session_id=scope['session_id'], operation_id=request['source_operation_id'], executor_id=scope['executor_id'],
        category='action_required' if actionable else 'watch', severity='warning' if actionable else 'info',
        priority=20 if actionable else 10, resolution=resolution, allowed_actions=actions,
        freshness='unavailable' if recipient is None and not permission else 'stale' if reason else 'current',
        next_change_at=_next_change(facts, now) if resolution == 'open' else None)]
