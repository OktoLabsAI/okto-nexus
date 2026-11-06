"""Current authority denials for committed, unfinished work; no I/O or effects.

This deliberately does not treat queue age, a disconnected host, recovery,
an unapplied/renewing lease, or absent inventory as an authority incident.
Those facts do not prove that an operator must change authorization.
Content guardrails remain canonical command checks; this metadata projection
does not promise that otherwise authorized work will be accepted or executed.
"""
from collections import defaultdict
from dataclasses import asdict
from datetime import timedelta
from types import SimpleNamespace
import hashlib
import json

from ..domain.attention import occurrence
from ..domain.inbox import requires_known_recipient
from ..domain.messages import parse_target
from ..domain.permissions import PermissionSet
from ..domain.policy import PolicyVersion, audience_permits, resolve_effective_sources
from ..domain.routing import RoutingAgent, can_agent_see_event, is_agent_eligible
from ..domain.runtime_context import RuntimeRequestContext
from ..domain.tag_selector import reachable
from ..errors import OktoNexusError
from .attention_native import _agent, _guard, _profile, _recorded_operator, _runtime_grant
from .execution_native_facts import effective_lease_facts, grant_candidate_authorized, grant_candidate_matches, runtime_guard_facts, stamp
from .runtime_delivery_facts import require_delivery_facts


KEYS = {
    'agents': ('agent_id',), 'agent_endpoints': ('endpoint_id',), 'runtime_profiles': ('profile_id',),
    'agent_runtime_overrides': ('agent_id',), 'agent_runtime_policy_epochs': ('agent_id',),
    'runtime_execution_grants': ('grant_id',), 'runtime_handoff_notifications': ('message_id',),
    'runtime_handoff_bindings': ('operation_id',), 'handoffs': ('handoff_id',), 'messages': ('message_id',),
    'handoff_authorization_receipts': ('handoff_id',), 'harness_sessions': ('session_id',),
    'runtime_results': ('result_id',),
    'execution_decisions': ('native_operation_id',),
    'runtime_boot_bindings': ('endpoint_id',), 'delivery_outbox': ('operation_id',),
    'execution_agent_revisions': ('server_id', 'agent_id'),
    'execution_bindings': ('server_id', 'executor_id', 'binding_id'),
    'execution_executors': ('server_id', 'executor_id'),
    'execution_workspace_bindings': ('server_id', 'executor_id', 'workspace_binding_id'),
    'execution_realizations': ('server_id', 'executor_id', 'realization_ref'),
    'execution_sessions': ('server_id', 'executor_id', 'session_id'),
    'execution_operations': ('server_id', 'executor_id', 'operation_id'),
    'execution_domain_deliveries': ('server_id', 'executor_id', 'operation_id'),
    'execution_dispatch_outbox': ('server_id', 'executor_id', 'operation_id'),
    'execution_session_capabilities': ('capability_id',),
}


def prepare_graph(rows, check_budget=None):
    check = check_budget or (lambda: None)
    def checked(values):
        for index, value in enumerate(values):
            if index % 128 == 0:
                check()
            yield value
    def grouped(values, keys):
        groups = defaultdict(list)
        for row in checked(values):
            groups[tuple(row[key] for key in keys)].append(row)
        return groups
    graph = {name: {tuple(row[key] for key in keys): row for row in checked(rows[name])} for name, keys in KEYS.items()}
    for name, keys in {'execution_client_intents': ('server_id', 'actor_agent_id', 'operation_id'),
                       'execution_leases': ('server_id', 'executor_id', 'session_id')}.items():
        graph[name] = grouped(rows[name], keys)
    graph['anchors'] = {(row['source_type'], row['source_id']): row for row in rows['anchors']}
    graph['agent_facts'] = {}
    endpoints_by_agent = grouped(rows['agent_endpoints'], ('agent_id',))
    methods_by_agent = grouped(rows['agent_connection_methods'], ('agent_id',))
    policy_by_agent = grouped(rows['agent_execution_policies'], ('agent_id',))
    for agent in checked(rows['agents']):
        identity = agent['agent_id']
        endpoints = sorted(endpoints_by_agent[(identity,)], key=lambda row: row['endpoint_id'])
        profiles = sorted((graph['runtime_profiles'][(key,)] for key in {row['profile_id'] for row in endpoints}
            if (key,) in graph['runtime_profiles']), key=lambda row: row['profile_id'])
        override = graph['agent_runtime_overrides'].get((identity,))
        graph['agent_facts'][identity] = dict(agent=agent,
            methods=sorted(methods_by_agent[(identity,)], key=lambda row: row['method']), endpoints=endpoints,
            profiles=[{k: v for k, v in row.items() if k != 'launch_revision'} for row in profiles],
            execution_policy=policy_by_agent[(identity,)],
            runtime_override={k: override[k] for k in ('runtime_enabled', 'session_policy')} if override else None,
            runtime_epoch=graph['agent_runtime_policy_epochs'].get((identity,), {}).get('epoch', 0))
    def decoded(value):
        return json.loads(value) if value is not None else None
    versions = defaultdict(list)
    for row in checked(rows['policy_versions']):
        versions[row['policy_id']].append(PolicyVersion(policy_id=row['policy_id'], version=row['version'],
            audience=decoded(row['audience']), governance=tuple(decoded(row['governance']) or ()), published_at=row['published_at']))
    graph['governance'], graph['governance_refs'], graph['governance_sources'] = {}, {}, {}
    bindings_by_agent = grouped(rows['agent_policy_bindings'], ('agent_id',))
    for agent in checked(rows['agents']):
        identity = agent['agent_id']
        bindings = sorted(bindings_by_agent[(identity,)], key=lambda row: row['position'])
        sources = resolve_effective_sources([dict(row, audience=decoded(row['audience']), governance=decoded(row['governance']) or []) for row in bindings], versions)
        encoded = json.dumps([asdict(source) for source in sources], sort_keys=True, separators=(',', ':'))
        graph['governance'][identity] = hashlib.sha256(encoded.encode()).hexdigest()
        graph['governance_sources'][identity] = sources
        graph['governance_refs'][identity] = [ref('agent_policy_bindings', identity, row['position']) for row in bindings] + [
            ref('policy_versions', source.policy_id, source.version) for source in sources if source.version is not None]
    graph['automation_overrides'] = {row['agent_id']: row for row in rows['agent_runtime_overrides']}
    installations = {row['server_id'] for row in rows['execution_installation']}
    bindings_by_endpoint = grouped((row for row in rows['execution_bindings'] if row['server_id'] in installations), ('endpoint_id',))
    grants_by_endpoint = grouped(rows['runtime_execution_grants'], ('endpoint_id',))
    graph['runtimes'] = {}
    for endpoint in checked(rows['agent_endpoints']):
        bindings = bindings_by_endpoint[(endpoint['endpoint_id'],)]
        graph['runtimes'][endpoint['endpoint_id']] = dict(endpoint=endpoint,
            represented=graph['agent_facts'].get(endpoint['agent_id']),
            profile=graph['runtime_profiles'].get((endpoint['profile_id'],)),
            binding_executors=[row['executor_id'] for row in bindings],
            host_kinds=[graph['execution_executors'].get((row['server_id'], row['executor_id']), {}).get('kind') for row in bindings],
            grants=grants_by_endpoint[(endpoint['endpoint_id'],)])
    graph['removed_agent_refs'] = defaultdict(list)
    for kind, key in checked(graph['anchors']):
        if kind in ('authority_agent_connection_methods', 'authority_agent_policy_bindings'):
            graph['removed_agent_refs'][json.loads(key)[0]].append((kind, key))
    graph['pending_domain'] = defaultdict(list)
    graph['domain_executors'] = defaultdict(set)
    pending_keys = {(row['server_id'], row['executor_id'], row['operation_id']) for row in rows['pending_dispatch']}
    for key, link in checked(graph['execution_domain_deliveries'].items()):
        graph['domain_executors'][link['domain_operation_id']].add(link['executor_id'])
        if key in pending_keys:
            graph['pending_domain'][link['domain_operation_id']].append(graph['execution_operations'][key])
    check()
    return graph


class AuthorityDenied(Exception):
    def __init__(self, reason, refs=(), deadline=None):
        self.reason, self.refs, self.deadline = reason, list(refs), deadline


def ref(table, *identity):
    return 'authority_' + table, json.dumps(identity, separators=(',', ':'))


def _agent_refs(graph, identity):
    data = graph['agent_facts'].get(identity)
    result = [ref('agents', identity), ref('agent_runtime_overrides', identity),
        ref('agent_runtime_policy_epochs', identity), ref('agent_execution_policies', identity),
        ref('runtime_policy_defaults', 1)]
    if data:
        result += [ref('agent_connection_methods', identity, row['method']) for row in data['methods']]
        result += [ref('agent_endpoints', row['endpoint_id']) for row in data['endpoints']]
        result += [ref('runtime_profiles', row['profile_id']) for row in data['profiles']]
        result += [ref('runtime_profiles', row['profile_id']) for row in data['endpoints'] if row['profile_id']]
    # Removed method/policy rows remain relevant tombstones for their agent.
    result.extend(graph['removed_agent_refs'].get(identity, ()))
    return result


def _policy_refs(graph, identity):
    return _agent_refs(graph, identity) + graph['governance_refs'].get(identity, [])


def _runtime_refs(graph, runtime):
    if not runtime:
        return []
    endpoint = runtime['endpoint']
    return _agent_refs(graph, endpoint['agent_id'])


def _check(reason, refs, call):
    try:
        return call()
    except OktoNexusError:
        raise AuthorityDenied(reason, refs) from None


def _grant(graph, runtime, actor_data, *, action, grant_id, scope, now, policy, budget):
    actor_id = actor_data['agent']['agent_id'] if actor_data else None
    refs = _runtime_refs(graph, runtime) + _agent_refs(graph, actor_id)
    if runtime:
        refs += [ref('runtime_execution_grants', row['grant_id']) for row in runtime['grants']
            if row['actor_agent_id'] == actor_id and (not grant_id or row['grant_id'] == grant_id)]
    if grant_id:
        refs.append(ref('runtime_execution_grants', grant_id))
        grant = graph['runtime_execution_grants'].get((grant_id,))
        if grant and grant['revoked_at']:
            raise AuthorityDenied('grant_revoked', [ref('runtime_execution_grants', grant_id)], grant['revoked_at'])
        if grant and not grant['no_expiry'] and stamp(grant['expires_at']) <= stamp(now):
            raise AuthorityDenied('grant_expired', [ref('runtime_execution_grants', grant_id)], grant['expires_at'])
    try:
        selected = _runtime_grant(runtime, actor_data, action=action, grant_id=grant_id,
            scope=scope, now=now, policy=policy, check_budget=budget)
        if selected is None:
            raise AuthorityDenied('canonical_grant_required', refs)
        return selected
    except OktoNexusError:
        deadlines = []
        # A message that has not selected an execution lease may use any
        # currently eligible grant. If the last such grant merely expires,
        # its durable deadline (not the next GET) starts the blocked episode.
        for grant in runtime['grants'] if runtime and not grant_id else ():
            if grant['no_expiry'] or not grant['expires_at'] or grant['revoked_at'] or stamp(grant['expires_at']) > stamp(now):
                continue
            try:
                _runtime_grant(dict(runtime, grants=[grant]), actor_data, action=action, grant_id=grant['grant_id'],
                    scope=scope, now=(stamp(grant['expires_at']) - timedelta(microseconds=1)).isoformat(), policy=policy, check_budget=budget)
            except OktoNexusError:
                continue
            deadlines.append(grant['expires_at'])
        raise AuthorityDenied('runtime_authority_changed', refs, max(deadlines, key=stamp) if deadlines else None) from None


def _method(data, name, policy):
    if name != 'mcp' and name not in policy['catalog']:
        return False
    row = next((row for row in data['methods'] if row['method'] == name), None) if data else None
    return bool(row['enabled']) if row else name == 'mcp' or bool(data and any(
        row['adapter_id'] == name and row['protocol'] == 'nxl-r4' and row['activation_state'] == 'approved' for row in data['endpoints']))


def _lease(graph, scope):
    rows = sorted(graph['execution_leases'].get((scope['server_id'], scope['executor_id'], scope['session_id']), []),
        key=lambda row: row['lease_serial'], reverse=True)
    return effective_lease_facts(rows[0] if rows else None, rows[1] if len(rows) > 1 else None)


def _scope_authority(graph, scope, *, source_guard, policy, operator_containment=False):
    identity = scope['agent_id']
    data = graph['agent_facts'].get(identity)
    if not data or not data['agent']['is_active']:
        raise AuthorityDenied('subject_unavailable', _agent_refs(graph, identity))
    binding = graph['execution_bindings'].get((scope['server_id'], scope['executor_id'], scope['binding_id']))
    subject_refs = _agent_refs(graph, identity) + ([ref('agent_endpoints', binding['endpoint_id'])] if binding else [])
    actual = _check('subject_authority_changed', subject_refs, lambda: _guard(data, policy))
    if not source_guard or actual != source_guard:
        raise AuthorityDenied('subject_authority_changed', subject_refs)
    revision = graph['execution_agent_revisions'].get((scope['server_id'], identity))
    if not operator_containment and (not revision or any(revision[key] != scope[key]
            for key in ('authorization_revision', 'configuration_revision', 'credential_epoch'))):
        raise AuthorityDenied('scope_authority_changed', [ref('execution_agent_revisions', scope['server_id'], identity)])
    if not binding or binding['binding_revision'] != scope['binding_revision'] or binding['workspace_binding_id'] != scope['workspace_binding_id']:
        raise AuthorityDenied('binding_authority_changed', [ref('execution_bindings', scope['server_id'], scope['executor_id'], scope['binding_id'])])
    executor = graph['execution_executors'].get((scope['server_id'], scope['executor_id']))
    if executor and executor['revoked_at']:
        raise AuthorityDenied('executor_revoked', [ref('execution_executors', scope['server_id'], scope['executor_id'])], executor['revoked_at'])
    # Missing/changed workspace approval and realization are durable config;
    # the host's connection state and recovery remain separate availability.
    workspace = graph['execution_workspace_bindings'].get((scope['server_id'], scope['executor_id'], scope['workspace_binding_id']))
    realization = graph['execution_realizations'].get((scope['server_id'], scope['executor_id'], binding['realization_ref']))
    if (not workspace or workspace['workspace_id'] != scope['workspace_id'] or workspace['status'] != 'READY'
            or not realization or realization['status'] != 'READY' or realization['revision'] != binding['realization_revision']):
        raise AuthorityDenied('workspace_authority_changed', [ref('execution_workspace_bindings', scope['server_id'], scope['executor_id'], scope['workspace_binding_id']),
            ref('execution_realizations', scope['server_id'], scope['executor_id'], binding['realization_ref'])])
    return graph['runtimes'].get(binding['endpoint_id'])


def _recorded(graph, operation, scope, provenance, runtime, now, policy, *, budget):
    actor = operation['actor_agent_id']
    guard = provenance['actor_guard_digest']
    delegated = dict(runtime, recipient_binding_count=1) if runtime else None
    facts = dict(authority=dict(actor_agent_id=actor, actor_guard_digest=guard), request=dict(scope=scope),
        initiator=graph['agent_facts'].get(actor), delegated_runtime=delegated)
    refs = _agent_refs(graph, actor) + _runtime_refs(graph, runtime)
    _check('initiator_authority_changed', refs, lambda: _recorded_operator(facts, policy, now))
    if budget and actor != scope['agent_id'] and guard and guard.startswith('delegated:'):
        proof = json.loads(guard[len('delegated:'):])
        _grant(graph, runtime, facts['initiator'], action='send', grant_id=proof['grant_id'], scope=scope,
            now=now, policy=policy, budget=True)


def _capability_binding(graph, actor, reference, workspace, now, policy, *, responding=False):
    credential = graph['execution_session_capabilities'].get((reference.get('capability_id'),))
    refs = [ref('execution_session_capabilities', reference.get('capability_id'))]
    scope = reference.get('scope', {})
    actions = (('tools/call', 'runtime_input_respond') if responding else ('tools/call', 'message_create')) if reference.get('audience') == 'nexus-mcp-session' else (('runtime.input.respond',) if responding else ('message.create',))
    if (not credential or reference.get('audience') not in ('nexus-mcp-session', 'nexus-native-session')
            or credential['audience'] != reference['audience'] or credential['revoked_at']
            or json.loads(credential['scope_json']) != scope or any(a not in json.loads(credential['actions_json']) for a in actions)
            or scope.get('agent_id') != actor or scope.get('workspace_id') != workspace):
        raise AuthorityDenied('message_principal_changed', refs)
    if stamp(credential['valid_until_server']) <= stamp(now):
        raise AuthorityDenied('message_principal_expired', refs, credential['valid_until_server'])
    grant = _opening_authority(graph, scope, now, policy, selected_id=credential['source_grant_id'])
    if not grant or grant['revision'] != credential['source_grant_revision']:
        raise AuthorityDenied('message_principal_changed', refs + [ref('runtime_execution_grants', credential['source_grant_id'])])
    if reference['audience'] == 'nexus-mcp-session' and not _method(graph['agent_facts'].get(actor), 'mcp', policy):
        raise AuthorityDenied('message_method_disabled', _agent_refs(graph, actor))


def _opening_authority(graph, scope, now, policy, *, selected_id=None):
    session = graph['execution_sessions'].get((scope['server_id'], scope['executor_id'], scope['session_id']))
    key = (scope['server_id'], scope['executor_id'], session['open_operation_id']) if session else None
    opening = graph['execution_operations'].get(key)
    provenance = _provenance(graph, opening) if opening else None
    refs = _agent_refs(graph, scope['agent_id'])
    if (not opening or not provenance or opening['action'] != 'runtime.open'
            or json.loads(opening['expected_revisions_json']) != scope):
        raise AuthorityDenied('opening_authority_changed', refs)
    runtime = _scope_authority(graph, scope, source_guard=provenance['source_guard_digest'], policy=policy)
    _recorded(graph, opening, scope, provenance, runtime, now, policy, budget=False)
    dispatch = graph['execution_dispatch_outbox'].get(key)
    captured = dispatch['dispatch_grant_id'] if dispatch else None
    if selected_id and captured not in (None, selected_id):
        raise AuthorityDenied('opening_grant_changed', refs)
    return _grant(graph, runtime, graph['agent_facts'].get(scope['agent_id']), action='open',
        grant_id=selected_id or captured, scope=scope, now=now, policy=policy, budget=False)


def _binding(graph, operation, now, policy):
    actor = operation['actor_agent_id']
    data = graph['agent_facts'].get(actor)
    binding = operation['credential_binding']
    if not data or not data['agent']['is_active'] or not binding:
        return False
    if binding.startswith('local-operator:'):
        return actor == 'operator' and binding == 'local-operator:' + _guard(data, policy)
    if binding.startswith('managed-message-v1:'):
        proof = json.loads(binding[len('managed-message-v1:'):])
        if set(proof) != {'principal', 'agent_guard'} or proof['agent_guard'] != _guard(data, policy):
            return False
        _capability_binding(graph, actor, proof['principal'], operation['workspace_id'], now, policy)
        return True
    if binding.startswith('handoff-notification-v1:'):
        identity = binding[len('handoff-notification-v1:'):]
        notice, message = graph['runtime_handoff_notifications'].get((identity,)), graph['messages'].get((identity,))
        return bool(notice and message and notice['runtime_route'] != 'competitive' and message['from_agent_id'] == actor
            and message['workspace_id'] == operation['workspace_id'] and notice['actor_guard'] == _guard(data, policy))
    return bool(data['agent']['api_key_hash'] and binding == data['agent']['api_key_hash'])


def _message_policy(graph, work, now, policy):
    message = graph['messages'].get((work['message_id'],))
    refs = _policy_refs(graph, work['actor_agent_id']) + _policy_refs(graph, work['recipient_agent_id'])
    if not message:
        raise AuthorityDenied('message_source_removed', refs)
    if (work['message_id'],) in graph['runtime_handoff_notifications']:
        _notice(graph, work, message, now)
        return
    sender = _agent(graph['agent_facts'].get(message['from_agent_id']))
    recipient = _agent(graph['agent_facts'].get(work['recipient_agent_id']))
    if not sender or not sender.is_active or not recipient or not reachable(sender, recipient):
        raise AuthorityDenied('message_audience_changed', refs)
    permissions = PermissionSet(sender.permissions)
    direct = requires_known_recipient(parse_target(message['target']))
    actions = ['send_channel'] + (['send_direct'] if direct else []) if message['channel_id'] else ['send_direct' if direct else 'send_broadcast']
    if any(not permissions.allows('messages', action) for action in actions):
        raise AuthorityDenied('message_permission_changed', refs)
    notification_actor = _relay(graph, work['source_result_id'], work['recipient_agent_id'], now, policy) if work['source_result_id'] else None
    expected = graph['governance'][sender.agent_id] + ':' + graph['governance'][recipient.agent_id]
    if notification_actor:
        expected += ':' + graph['governance'][notification_actor]
        refs += _policy_refs(graph, notification_actor)
    if work['authorization_revision'] != expected:
        raise AuthorityDenied('message_policy_changed', refs)


def _notice(graph, work, message, now):
    from .runtime_handoff_notifications import OUTCOME_KINDS, PREFIX
    notice = graph['runtime_handoff_notifications'][(work['message_id'],)]
    handoff = graph['handoffs'].get((notice['handoff_id'],))
    refs = _policy_refs(graph, message['from_agent_id']) + _policy_refs(graph, work['recipient_agent_id'])
    if (work['credential_binding'] != PREFIX + work['message_id'] or notice['recipient_agent_id'] != work['recipient_agent_id']
            or notice['runtime_route'] in ('competitive', 'legacy_admitted') or not handoff
            or handoff['workspace_id'] != message['workspace_id']):
        raise AuthorityDenied('handoff_notice_authority_changed', refs)
    recipient = _agent(graph['agent_facts'].get(work['recipient_agent_id']))
    if notice['event_type'].split(':')[0] in OUTCOME_KINDS:
        sender = _agent(graph['agent_facts'].get(message['from_agent_id']))
        if (not sender or not sender.is_active or not recipient or not recipient.is_active
                or work['recipient_agent_id'] not in {handoff['from_agent_id'], handoff['claimed_by'], message['previous_claimed_by']}):
            raise AuthorityDenied('handoff_notice_authority_changed', refs)
        return
    sender = _agent(graph['agent_facts'].get(handoff['from_agent_id']))
    if not sender or not sender.is_active or not recipient or not recipient.is_active or sender.agent_id == recipient.agent_id:
        raise AuthorityDenied('handoff_notice_authority_changed', refs)
    view = RoutingAgent(agent_id=recipient.agent_id, workspace_id=handoff['workspace_id'], role=recipient.role,
        capabilities=json.loads(recipient.capabilities) if isinstance(recipient.capabilities, str) else recipient.capabilities, tags=recipient.tags)
    if (not reachable(sender, recipient) or not PermissionSet(sender.permissions).allows('handoffs', 'create')
            or not PermissionSet(recipient.permissions).allows('handoffs', 'work')
            or not audience_permits(graph['governance_sources'][sender.agent_id], 'outbound', recipient.tags)
            or not audience_permits(graph['governance_sources'][recipient.agent_id], 'inbound', sender.tags)
            or not can_agent_see_event(view, handoff, now) or not is_agent_eligible(view, handoff['target'], handoff['created_at'], now)):
        raise AuthorityDenied('handoff_notice_authority_changed', refs)


def _relay(graph, result_id, recipient_id, now, policy):
    current, visited, notification_actor = result_id, set(), None
    for _ in range(65):
        if current in visited:
            raise AuthorityDenied('relay_ancestry_changed')
        visited.add(current)
        result = graph['runtime_results'].get((current,))
        source = graph['delivery_outbox'].get((result['operation_id'],)) if result else None
        if not source:
            raise AuthorityDenied('relay_source_authority_removed')
        runtime = graph['runtimes'].get(source['endpoint_id'])
        refs = _runtime_refs(graph, runtime) + _policy_refs(graph, source['actor_agent_id'])
        actor = _agent(graph['agent_facts'].get(source['actor_agent_id']))
        sender = _agent(graph['agent_facts'].get(source['recipient_agent_id']))
        message = graph['messages'].get((source['message_id'],))
        origin = _agent(graph['agent_facts'].get(message['from_agent_id'])) if message else None
        endpoint = runtime['endpoint'] if runtime else None
        profile = runtime['profile'] if runtime else None
        if (not policy['feature_harness_integrations'] or source['reconciliation_id'] or not endpoint or not endpoint['enabled']
                or endpoint['response_policy'] != 'conversation' or endpoint['revision'] != source['endpoint_revision']
                or not sender or not sender.is_active or not origin or not origin.is_active
                or not _binding(graph, source, now, policy)
                or endpoint['profile_id'] and (not profile or not profile['enabled'] or profile['revision'] != source['profile_revision'])):
            raise AuthorityDenied('relay_source_authority_changed', refs)
        config = json.loads(endpoint['public_config'])
        if not config.get('relay_results'):
            raise AuthorityDenied('relay_approval_revoked', refs)
        handoff = graph['runtime_handoff_bindings'].get((source['operation_id'],))
        if handoff:
            _handoff(graph, source, handoff, now, policy)
        if current == result_id:
            target = config.get('notify_target', dict(strategy='direct', agent_id=origin.agent_id))
            if not (target.get('strategy') == 'direct' and target.get('agent_id') == origin.agent_id) and actor.agent_id != sender.agent_id:
                notification_actor = actor.agent_id
                permissions = PermissionSet(actor.permissions)
                direct = requires_known_recipient(target)
                actions = ['send_channel'] + (['send_direct'] if direct else []) if message['channel_id'] else ['send_direct' if direct else 'send_broadcast']
                captured = json.loads(result['publication_recipients']) if result['publication_state'] == 'PUBLISHED' else [recipient_id]
                if (any(not permissions.allows('messages', action) for action in actions)
                        or recipient_id not in captured or 0 < permissions.limit('max_recipients') < len(captured)
                        or any(identity != actor.agent_id and not reachable(actor, _agent(graph['agent_facts'].get(identity))) for identity in captured)):
                    raise AuthorityDenied('relay_audience_changed', refs)
        current = source['source_result_id']
        if not current:
            return notification_actor
    raise AuthorityDenied('relay_ancestry_changed')


def _handoff(graph, work, binding, now, policy):
    handoff = graph['handoffs'].get((binding['handoff_id'],))
    if not handoff or handoff['status'] != 'CLAIMED' or handoff['claim_epoch'] != binding['claim_epoch'] or handoff['claimed_by'] != work['recipient_agent_id']:
        return
    actor = graph['agent_facts'].get(work['actor_agent_id'])
    runtime = graph['runtimes'].get(work['endpoint_id'])
    refs = _runtime_refs(graph, runtime) + _policy_refs(graph, work['actor_agent_id'])
    from .handoff_automation import PREFIX, restore_context
    if (work['credential_binding'] or '').startswith(PREFIX):
        context = _check('handoff_automation_changed', refs, lambda: restore_context(work, binding))
        proof = context.handoff_automation
        override = graph['automation_overrides'].get(proof.agent_id)
        inherited = override is None or override['broadcast_handoff_auto_claim'] is None
        defaults = policy['automation_defaults']
        automation = dict(runtime=runtime_guard_facts(policy['runtime_defaults'], actor['runtime_override'], actor['runtime_epoch']),
            enabled=bool(defaults['broadcast_handoff_auto_claim'] if inherited else override['broadcast_handoff_auto_claim']),
            inherited=inherited, agent_epoch=override['handoff_auto_claim_epoch'] if override else 0,
            defaults_epoch=defaults['handoff_auto_claim_epoch'] if inherited else None)
        from nexus_connector_core.protocol import canonical_json
        digest = 'sha256:' + hashlib.sha256(canonical_json(automation)).hexdigest()
        if (not automation['enabled'] or not automation['runtime']['runtime_enabled'] or proof.policy_digest != digest
                or proof.agent_digest != _guard(actor, policy) or json.loads(handoff['target']).get('strategy') != 'broadcast'):
            raise AuthorityDenied('handoff_automation_changed', refs)
    elif not actor or work['credential_binding'] != actor['agent']['api_key_hash']:
        raise AuthorityDenied('handoff_actor_changed', refs)
    grant = _grant(graph, runtime, actor, action='execute_work', grant_id=binding['grant_id'],
        scope=dict(agent_id=work['recipient_agent_id'], workspace_id=work['workspace_id']), now=now, policy=policy, budget=False)
    endpoint, profile = runtime['endpoint'], runtime['profile']
    if (not grant or grant['revision'] != binding['grant_revision'] or endpoint['revision'] != work['endpoint_revision']
            or endpoint['consumption'] != 'exclusive' or not profile or profile['revision'] != work['profile_revision']):
        raise AuthorityDenied('handoff_runtime_changed', refs)
    creator = _agent(graph['agent_facts'].get(handoff['from_agent_id']))
    worker = _agent(graph['agent_facts'].get(handoff['claimed_by']))
    refs += _policy_refs(graph, handoff['from_agent_id']) + _policy_refs(graph, handoff['claimed_by'])
    receipt = graph['handoff_authorization_receipts'].get((handoff['handoff_id'],))
    if not creator or not creator.is_active or not worker or not worker.is_active or not reachable(creator, worker):
        raise AuthorityDenied('handoff_audience_changed', refs)
    creator_revision = graph['governance'][creator.agent_id]
    if (not receipt or receipt['creator_policy_revision'] != creator_revision or receipt['hitl_enabled'] != int(policy['feature_hitl'])
            or work['authorization_revision'] != creator_revision + ':' + graph['governance'][worker.agent_id]):
        raise AuthorityDenied('handoff_policy_changed', refs)
    view = RoutingAgent(agent_id=worker.agent_id, workspace_id=handoff['workspace_id'], role=worker.role,
        capabilities=json.loads(worker.capabilities) if isinstance(worker.capabilities, str) else worker.capabilities, tags=worker.tags)
    if (not PermissionSet(creator.permissions).allows('handoffs', 'create')
            or not PermissionSet(worker.permissions).allows('handoffs', 'work')
            or not is_agent_eligible(view, handoff['target'], handoff['created_at'], now)):
        raise AuthorityDenied('handoff_permission_changed', refs)


def _delivery(graph, work, now, policy):
    runtime = graph['runtimes'].get(work['endpoint_id'])
    endpoint = runtime['endpoint'] if runtime else None
    if endpoint and endpoint['protocol'] != 'nxl-r4':
        return
    notice = graph['runtime_handoff_notifications'].get((work['message_id'],))
    if notice:
        from .runtime_handoff_notifications import OUTCOME_KINDS
        handoff_source = graph['handoffs'].get((notice['handoff_id'],))
        if handoff_source and handoff_source['status'] != 'OPEN' and notice['event_type'].split(':')[0] not in OUTCOME_KINDS:
            return
    handoff = graph['runtime_handoff_bindings'].get((work['operation_id'],))
    if handoff:
        _handoff(graph, work, handoff, now, policy)
        for pending in graph['pending_domain'].get(work['operation_id'], ()):
            _dispatch(graph, dict(work=pending, profile_revision=pending['profile_revision']), now, policy, validate_domain=False)
        return
    actor, subject = graph['agent_facts'].get(work['actor_agent_id']), graph['agent_facts'].get(work['recipient_agent_id'])
    admission = json.loads(work['admission_binding']) if work['admission_binding'] else None
    original = graph['runtimes'].get(admission['endpoint_id']) if admission else None
    descriptor = policy['catalog'].get(endpoint['adapter_id']) if endpoint else None
    refs = _agent_refs(graph, work['actor_agent_id']) + _runtime_refs(graph, runtime) + _runtime_refs(graph, original) + [ref('agent_endpoints', work['endpoint_id'])]
    _check('delivery_authority_changed', refs, lambda: require_delivery_facts(operation=work,
        config=SimpleNamespace(**policy), actor=_agent(actor), recipient=_agent(subject), endpoint=endpoint,
        profile=_profile(runtime['profile']) if runtime else None,
        original=original['endpoint'] if original else None,
        original_profile=_profile(graph['runtime_profiles'].get((admission['profile_id'],))) if admission else None,
        actor_binding_valid=_binding(graph, work, now, policy), method_enabled=_method(subject, endpoint['adapter_id'], policy) if endpoint else False,
        session_profile_revision=graph['harness_sessions'].get((work['runtime_session_id'],), {}).get('runtime_profile_revision'),
        descriptor=SimpleNamespace(**descriptor) if descriptor else None))
    _message_policy(graph, work, now, policy)
    _grant(graph, runtime, subject, action='send', grant_id=None,
        scope=dict(agent_id=work['recipient_agent_id'], workspace_id=work['workspace_id']), now=now, policy=policy, budget=True)


def _provenance(graph, operation):
    rows = [row for row in graph['execution_client_intents'].get((operation['server_id'], operation['actor_agent_id'], operation['operation_id']), [])
        if row['session_selection'] != 'reuse' and row['intent_id'].startswith(
            'r4decisionintent_' if operation['action'] in ('approval.decide', 'input.provide') else 'r4intent_')]
    return rows[0] if len(rows) == 1 else None


def _dispatch(graph, facts, now, policy, *, validate_domain=True):
    work = facts['work']
    scope = json.loads(work['expected_revisions_json'])
    provenance = _provenance(graph, work)
    if not provenance:
        raise AuthorityDenied('dispatch_provenance_changed', [ref('execution_operations', work['server_id'], work['executor_id'], work['operation_id'])])
    containment = work['action'] in ('turn.interrupt', 'runtime.close')
    operator_containment = containment and work['actor_agent_id'] != work['subject_agent_id']
    runtime = _scope_authority(graph, scope, source_guard=provenance['source_guard_digest'], policy=policy,
        operator_containment=operator_containment)
    native_decision = work['action'] in ('approval.decide', 'input.provide')
    if not native_decision:
        _recorded(graph, work, scope, provenance, runtime, now, policy, budget=not containment)
    else:
        _decision(graph, work, scope, runtime, now, policy)
        _opening_authority(graph, scope, now, policy)
    link = graph['execution_domain_deliveries'].get((work['server_id'], work['executor_id'], work['operation_id']))
    if link and validate_domain:
        delivery = graph['delivery_outbox'].get((link['domain_operation_id'],))
        if delivery:
            _delivery(graph, delivery, now, policy)
    if containment:
        if not operator_containment:
            _control_grant(graph, runtime, scope, work['action'], now, policy)
        return  # Operator containment survives productive grant revocation.
    session = graph['execution_sessions'].get((work['server_id'], work['executor_id'], work['session_id']))
    opening = graph['execution_operations'].get((work['server_id'], work['executor_id'], session['open_operation_id'])) if session else None
    if opening and opening['connection_key_id'] is not None:
        raise AuthorityDenied('opening_credential_retired', _agent_refs(graph, scope['agent_id']))
    if work['action'] == 'runtime.open':
        profile = runtime['profile'] if runtime else None
        if not profile or not profile['enabled'] or profile['launch_revision'] != facts['profile_revision']:
            raise AuthorityDenied('launch_profile_changed', _runtime_refs(graph, runtime))
        if work['boot_authority_json']:
            proof = json.loads(work['boot_authority_json'])
            boot = graph['runtime_boot_bindings'].get((proof['endpoint_id'],))
            issuer = graph['agents'].get((boot['issuer_agent_id'],)) if boot else None
            if (not boot or not boot['enabled'] or boot['revision'] != proof['revision']
                    or boot['endpoint_revision'] != runtime['endpoint']['revision']
                    or boot['profile_revision'] != profile['revision'] or not issuer or not issuer['is_active']
                    or issuer['agent_id'] != 'operator' or boot['issuer_credential_binding'] is not None
                    and boot['issuer_credential_binding'] != issuer['api_key_hash']):
                raise AuthorityDenied('boot_approval_changed', [ref('runtime_boot_bindings', proof['endpoint_id'])] + _agent_refs(graph, 'operator'))
    lease = _lease(graph, scope)
    action = {'runtime.open': 'open', 'turn.submit': 'send', 'turn.steer': 'steer',
        'approval.decide': 'send', 'input.provide': 'send'}[work['action']]
    _grant(graph, runtime, graph['agent_facts'].get(scope['agent_id']), action=action,
        grant_id=lease['grant_id'] if lease else None, scope=scope, now=now, policy=policy,
        budget=not native_decision and work['action'] != 'runtime.open')


def _control_grant(graph, runtime, scope, command, now, policy):
    lease = _lease(graph, scope)
    if not lease:
        return  # Awaiting a lease is not itself proof of revoked authority.
    actor = _agent(graph['agent_facts'].get(scope['agent_id']))
    endpoint = runtime['endpoint'] if runtime else None
    action = 'interrupt' if command == 'turn.interrupt' else 'close'
    context = RuntimeRequestContext(scope['agent_id'], 'agent_key',
        credential_binding=actor.api_key_hash if actor else None, execution_grant_id=lease['grant_id'])
    selected = graph['runtime_execution_grants'].get((lease['grant_id'],))
    refs = _runtime_refs(graph, runtime) + [ref('runtime_execution_grants', lease['grant_id'])]
    if (policy['feature_harness_integrations'] and actor and actor.is_active and actor.api_key_hash and endpoint
            and endpoint['adapter_id'] in policy['catalog'] and selected and not selected['revoked_at']):
        selected = dict(selected, actions=json.loads(selected['actions']))
        if (grant_candidate_matches(selected, context=context, actor=actor, action=action,
                endpoint_id=endpoint['endpoint_id'], now=now)
                and grant_candidate_authorized(selected, actor=actor, represented=_agent(runtime['represented']),
                    endpoint=endpoint, profile=_profile(runtime['profile']), action=action,
                    represented_agent_id=scope['agent_id'], workspace_id=scope['workspace_id'], check_budget=False, consume=False)):
            return
    deadline = None
    if selected and selected['revoked_at']:
        deadline = selected['revoked_at']
    elif selected and not selected['no_expiry'] and stamp(selected['expires_at']) <= stamp(now):
        deadline = selected['expires_at']
    raise AuthorityDenied('control_authority_changed', refs, deadline)


def _decision(graph, work, scope, runtime, now, policy):
    decision = graph['execution_decisions'].get((work['operation_id'],))
    refs = _agent_refs(graph, work['actor_agent_id']) + _runtime_refs(graph, runtime)
    if not policy['feature_hitl'] or not decision or not decision['source_valid'] or decision['actor_agent_id'] != work['actor_agent_id']:
        raise AuthorityDenied('native_decision_authority_changed', refs)
    if stamp(decision['expires_at']) <= stamp(now):
        raise AuthorityDenied('native_decision_expired', refs, decision['expires_at'])
    actor_data = graph['agent_facts'].get(work['actor_agent_id'])
    actor = _agent(actor_data)
    guard = decision['actor_guard_digest']
    if not actor or not actor.is_active or not actor.api_key_hash or not guard:
        raise AuthorityDenied('native_responder_changed', refs)
    current = _guard(actor_data, policy)
    if guard.startswith('managed-input-v1:'):
        proof = json.loads(guard[len('managed-input-v1:'):])
        if proof['agent_guard'] != current or decision['kind'] != 'native_input':
            raise AuthorityDenied('native_responder_changed', refs)
        _capability_binding(graph, actor.agent_id, proof['principal'], scope['workspace_id'], now, policy, responding=True)
    elif guard != current:
        raise AuthorityDenied('native_responder_changed', refs)
    profile = _profile(runtime['profile']) if runtime else None
    if profile and 'approvals' in profile['config'].get('disabled_capabilities', ()):
        raise AuthorityDenied('native_decisions_disabled', refs)


def _native(graph, facts, now, policy):
    scope, authority = facts['request']['scope'], facts['authority']
    source = facts['source']
    if (source and source['admission_state'] == 'RESOLVED_TERMINAL'
            or facts['receipt'] and facts['receipt']['stage'] in ('SUCCEEDED', 'FAILED', 'CANCELLED', 'UNCERTAIN')):
        return
    if not authority:
        # Source absence alone cannot identify which authority gate blocked it.
        return
    runtime = _scope_authority(graph, scope, source_guard=authority['source_guard_digest'], policy=policy)
    _check('initiator_authority_changed', _agent_refs(graph, authority['actor_agent_id']),
        lambda: _recorded_operator(facts, policy, now))
    grant = _grant(graph, runtime, facts['subject'], action='open', grant_id=authority['dispatch_grant_id'],
        scope=scope, now=now, policy=policy, budget=False)
    if grant:
        _grant(graph, runtime, facts['subject'], action='send', grant_id=grant['grant_id'],
            scope=scope, now=now, policy=policy, budget=False)
    profile = _profile(runtime['profile']) if runtime else None
    if profile and 'approvals' in profile['config'].get('disabled_capabilities', ()):
        raise AuthorityDenied('native_decisions_disabled', _runtime_refs(graph, runtime))


def _legacy_handoff_episode(graph, work, now):
    """Keep v1 preferences for the exact pre-162 handoff authority episode."""
    binding = graph['runtime_handoff_bindings'].get((work['operation_id'],))
    if not binding:
        return None
    grant = graph['runtime_execution_grants'].get((binding['grant_id'],))
    endpoint = graph['agent_endpoints'].get((work['endpoint_id'],))
    profile = graph['runtime_profiles'].get((endpoint['profile_id'],)) if endpoint else None
    if not grant or not endpoint:
        return None
    reason, anchor, changed = None, None, None
    if grant['revoked_at']:
        reason, changed = 'grant_revoked', grant['revoked_at']
    elif not grant['no_expiry'] and stamp(grant['expires_at']) <= stamp(now):
        reason, changed = 'grant_expired', grant['expires_at']
    elif grant['revision'] != binding['grant_revision']:
        reason, anchor = 'grant_changed', graph['anchors'].get(('runtime_grant_revision', binding['grant_id']))
    elif endpoint['revision'] != work['endpoint_revision'] or not endpoint['enabled'] or endpoint['activation_state'] != 'approved':
        reason, anchor = 'endpoint_changed', graph['anchors'].get(('runtime_endpoint_revision', endpoint['endpoint_id']))
    elif work['profile_revision'] is not None and (not profile or profile['revision'] != work['profile_revision'] or not profile['enabled']):
        reason, anchor = 'profile_changed', graph['anchors'].get(('runtime_profile_revision', endpoint['profile_id']))
    if reason is None:
        return None
    episode = [binding['grant_id'], binding['grant_revision'], work['endpoint_revision'], work['profile_revision']]
    if anchor:
        episode += [reason, anchor['episode']]
        changed = max((work['created_at'], anchor['first_detected_at']), key=stamp)
    return episode, changed or work['created_at'], [reason, grant['revision'], endpoint['revision'], profile['revision'] if profile else None, anchor['episode'] if anchor else None]


def _domain_pending(graph, work):
    """A retired claim/availability notice is no longer executable work."""
    binding = graph['runtime_handoff_bindings'].get((work['operation_id'],))
    if binding:
        handoff = graph['handoffs'].get((binding['handoff_id'],))
        if (not handoff or handoff['status'] != 'CLAIMED' or handoff['claim_epoch'] != binding['claim_epoch']
                or handoff['claimed_by'] != work['recipient_agent_id']):
            return False
    notice = graph['runtime_handoff_notifications'].get((work['message_id'],))
    if notice:
        from .runtime_handoff_notifications import OUTCOME_KINDS
        handoff = graph['handoffs'].get((notice['handoff_id'],))
        if not handoff or handoff['status'] != 'OPEN' and notice['event_type'].split(':')[0] not in OUTCOME_KINDS:
            return False
    return True


def project(facts, now, policy):
    graph = policy['graph']
    family = facts['family']
    if family == 'native':
        native = facts['native']
        request, scope = native['request'], native['request']['scope']
        work = dict(operation_id=request['source_operation_id'], created_at=request['received_at'],
            workspace_id=scope['workspace_id'], subject_agent_id=scope['agent_id'], session_id=scope['session_id'], executor_id=scope['executor_id'])
        source_id, source_type = request['canonical_request_id'], 'execution_native_request'
    else:
        work = facts['work']
        source_id = work['operation_id']
        source_type = 'delivery_operation' if family == 'delivery' else 'execution_operation'
        domain_work = work if family == 'delivery' else None
        if family == 'dispatch':
            link = graph['execution_domain_deliveries'].get((work['server_id'], work['executor_id'], work['operation_id']))
            domain_work = graph['delivery_outbox'].get((link['domain_operation_id'],)) if link else None
        if domain_work and not _domain_pending(graph, domain_work):
            return []
    try:
        if family == 'delivery':
            _delivery(graph, work, now, policy)
        elif family == 'dispatch':
            _dispatch(graph, facts, now, policy)
        else:
            _native(graph, facts['native'], now, policy)
    except AuthorityDenied as denial:
        anchors = [graph['anchors'][key] for key in sorted(set(denial.refs)) if key in graph['anchors']]
        transitions = [work['created_at']] + [row['last_changed_at'] for row in anchors]
        if denial.deadline:
            transitions.append(denial.deadline)
        changed = max(transitions, key=stamp)
        revision = dict(reason=denial.reason, anchors=[(row['source_type'], row['source_id'], row['episode']) for row in anchors],
            deadline=denial.deadline)
        episode = revision
        detected = changed
        legacy = _legacy_handoff_episode(graph, work, now) if family == 'delivery' else None
        if legacy:
            episode, detected, legacy_revision = legacy
            changed = max((changed, detected), key=stamp)
            revision = dict(legacy=legacy_revision, authority=revision)
        executors = graph['domain_executors'].get(work['operation_id'], set())
        executor_id = work.get('executor_id') or (next(iter(executors)) if len(executors) == 1 else None)
        return [occurrence(kind='execution_authority_blocking', source_type=source_type, source_id=source_id,
            episode=episode, source_revision=revision, first_detected_at=detected, last_changed_at=changed,
            agent_id=work.get('recipient_agent_id', work.get('subject_agent_id')), workspace_id=work['workspace_id'],
            session_id=work.get('runtime_session_id', work.get('session_id')), operation_id=work['operation_id'], executor_id=executor_id,
            category='action_required', severity='warning', priority=30, resolution='open',
            allowed_actions=['inspect_approval', 'review_authority'] if family == 'native' else ['inspect_operation', 'review_authority'])]
    return []
