"""Atomic connection setup. No canonical configuration is changed by a draft test."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json

from ..bootstrap.execution_authority import ExecutionToolDependencies, build_execution_access
from ..errors import ErrorCode, OktoNexusError
from .execution_local_realizations import _digest, directory_identity, stage_embedded_realization
from . import agent_execution_policy, runtime_policy


class SetupTransaction:
    """Nested application services share the outer Finish transaction."""
    def __init__(self, factory, uow):
        self.factory, self.uow = factory, uow

    def __getattr__(self, name):
        return getattr(self.factory, name)

    @contextmanager
    def unit_of_work(self, **kwargs):
        yield self.uow


def conflict(message):
    return OktoNexusError(ErrorCode.CONFLICT, message, {})


def require_operator(access, context, uow, *, require_feature=False):
    if not access.authenticate(context, uow=uow, require_feature=require_feature):
        raise OktoNexusError(ErrorCode.PERMISSION_DENIED, 'An authenticated operator is required.', {})


def baseline(uow, agent_id, binding_id=None):
    execution = agent_execution_policy.policy_view(uow, agent_id)
    runtime = runtime_policy.view(uow.connection, agent_id)
    result = dict(execution_revision=execution['revision'], runtime_revision=runtime['revision'],
                  defaults_revision=runtime['defaults']['revision'], binding_revision=None, endpoint_revision=None)
    if binding_id:
        row = uow.connection.execute('SELECT b.binding_revision,e.revision FROM execution_bindings b '
            'JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id WHERE b.binding_id=? AND e.agent_id=?',
            (binding_id, agent_id)).fetchone()
        if row is None:
            raise conflict('The selected connection is no longer available.')
        result.update(binding_revision=row[0], endpoint_revision=row[1])
    return result


def runtime_enabled(conn, configuration):
    value = configuration['runtime_enabled']
    return runtime_policy.defaults(conn)['runtime_enabled'] if value is None else value


def load_setup(deps, context, agent_id, binding_id=None):
    access = build_execution_access(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        require_operator(access, context, uow)
        if access.agents.get(uow, agent_id) is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Agent does not exist.', {})
        result = {'baseline': baseline(uow, agent_id, binding_id),
                  'runtime_default': runtime_policy.defaults(uow.connection)['runtime_enabled']}
        result['connections'] = [dict(row) for row in uow.connection.execute(
            'SELECT b.binding_id,b.candidate_ref,b.executor_id,e.workspace_id,e.adapter_id '
            'FROM execution_bindings b JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id '
            'JOIN execution_local_realizations l ON l.server_id=b.server_id AND l.executor_id=b.executor_id '
            'AND l.realization_ref=b.realization_ref WHERE e.agent_id=? ORDER BY e.workspace_id,e.adapter_id', (agent_id,))]
        if binding_id:
            row = uow.connection.execute('SELECT e.public_config,e.response_policy,l.local_record_json FROM execution_bindings b '
                'JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id '
                'JOIN execution_local_realizations l ON l.server_id=b.server_id AND l.executor_id=b.executor_id '
                'AND l.realization_ref=b.realization_ref WHERE b.binding_id=? AND e.agent_id=?',
                (binding_id, agent_id)).fetchone()
            if row:
                record = json.loads(row['local_record_json'])
                result['folders'] = dict(workspace_root=record['root']['path'],
                    provider_home=record['provider_home']['path'] if record['provider_home'] else None,
                    secret_bindings=record['configuration']['secret_bindings'])
                result['public_config'] = json.loads(row['public_config'])
                result['automatic_reply'] = True
                grant = uow.connection.execute('SELECT g.* FROM runtime_execution_grants g '
                    'JOIN execution_bindings b ON b.endpoint_id=g.endpoint_id WHERE b.binding_id=? '
                    'AND g.actor_agent_id=? AND g.revoked_at IS NULL ORDER BY g.created_at DESC LIMIT 1',
                    (binding_id, agent_id)).fetchone()
                if grant:
                    minutes = max(1, min(1440, round((datetime.fromisoformat(grant['expires_at']) -
                        datetime.fromisoformat(grant['created_at'])).total_seconds() / 60)))
                    result['authorization'] = {'minutes': None if grant['no_expiry'] else minutes,
                        'actions': None if grant['unlimited_actions'] else grant['max_executions']}
        return result


def finish_setup(deps, context, owner, fresh, request, *, verified):
    from .execution_binding_proposals import prepare_execution_binding, apply_execution_binding
    from ..adapters.inbound.mcp.tools.harness import build_endpoint_service
    agent_id, configuration = request['agent_id'], request['configuration']
    digest = _digest(request)
    with deps.connection_factory.unit_of_work() as uow:
        scoped = ExecutionToolDependencies(deps, SetupTransaction(deps.connection_factory, uow))
        access = build_execution_access(scoped)
        access.authorize_maintenance(context, uow=uow)
        prior = uow.connection.execute('SELECT * FROM connection_setup_commits WHERE actor_agent_id=? '
            'AND client_intent_id=?', (context.actor_agent_id, request['client_intent_id'])).fetchone()
        if prior:
            if prior['request_hash'] != digest:
                raise conflict('This Finish request has different content.')
            return json.loads(prior['result_json'])
        if baseline(uow, agent_id, request.get('binding_id')) != request['baseline']:
            raise conflict('The active configuration changed while you were editing. Reopen Connections to review it.')
        active = runtime_enabled(uow.connection, configuration)
        runtime_policy.save_policy(scoped, context, agent_id=agent_id, changes=dict(
            expected_revision=request['baseline']['runtime_revision'], runtime_enabled=configuration['runtime_enabled'],
            session_policy=configuration['session_policy']))
        if active or configuration['adapter_id']:
            agent_execution_policy.save_policy(scoped, context, agent_id,
                expected_revision=request['baseline']['execution_revision'],
                execution_location=configuration['execution_location'], local_adapter_id=configuration['adapter_id'] or None)
        result = {'saved': True, 'agent_id': agent_id}
        binding = None
        if active and configuration['execution_location'] != 'remote':
            if not verified:
                raise conflict('Test this configuration successfully before finishing.')
            if directory_identity(configuration['workspace_root']) != verified['root'] or (
                    directory_identity(configuration['provider_home']) if configuration['provider_home'] else None) != verified['home']:
                raise conflict('A configured directory changed after the test. Run the test again.')
            intent = request['client_intent_id']
            publication = stage_embedded_realization(scoped.connection_factory, owner=owner,
                executor_id=request['executor_id'], access=access, context=context, request=dict(
                    client_intent_id=intent, local_consent_id=intent, approved=True, agent_id=agent_id,
                    workspace_id=request.get('workspace_id'), workspace_label=configuration['workspace_label'],
                    workspace_root=configuration['workspace_root'], provider_home=configuration['provider_home'],
                    secret_bindings=configuration['secret_bindings'], adapter_id=configuration['adapter_id'],
                    candidate_ref=request['candidate_ref'], inventory_revision=request['inventory_revision']))
            binding_request = dict(client_intent_id=intent + '_prepare', agent_id_hint=agent_id,
                executor_id=request['executor_id'], adapter_id=configuration['adapter_id'],
                candidate_ref=request['candidate_ref'], inventory_revision=request['inventory_revision'],
                realization_ref=publication.realization_ref, workspace_id=publication.workspace_id,
                alias=configuration['alias'])
            if request.get('binding_id'):
                binding_request['replace_binding_id'] = request['binding_id']
            proposal = prepare_execution_binding(scoped.connection_factory, actor_agent_id=context.actor_agent_id,
                request=binding_request, fresh_publications=fresh, context=context, access=access, approvals=deps.approvals)
            binding = apply_execution_binding(scoped.connection_factory, actor_agent_id=context.actor_agent_id,
                request=dict(client_intent_id=intent + '_apply', proposal_id=proposal['proposal_id'],
                    proposal_revision=proposal['proposal_revision'], approved_diff_hash=proposal['diff']['approved_diff_hash']),
                fresh_publications=fresh, context=context, access=access)
        elif active and request.get('binding_id'):
            row = uow.connection.execute('SELECT b.binding_id,b.endpoint_id,e.adapter_id,e.agent_id,e.enabled,e.activation_state '
                'FROM execution_bindings b JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id '
                'JOIN execution_executors x ON x.server_id=b.server_id AND x.executor_id=b.executor_id '
                "WHERE b.binding_id=? AND b.executor_id=? AND x.kind='remote'",
                (request['binding_id'], request['executor_id'])).fetchone()
            if not row or row['agent_id'] != agent_id or row['adapter_id'] != configuration['adapter_id'] or not row['enabled'] or row['activation_state'] != 'approved':
                raise conflict('Select an approved remote connection for this agent and harness.')
            binding = dict(row)
        if binding:
            endpoints = build_endpoint_service(scoped)
            endpoint_id = binding['endpoint_id']
            # These policies share one endpoint revision. Always read it inside this
            # transaction, after the previous update, rather than asking the UI to reload.
            for method, values in [(endpoints.harness_settings, {'settings': configuration['harness_settings']}),
                                   (endpoints.tool_permission, {'mode': configuration['tool_access']}),
                                   (endpoints.conversation_policy, {'enabled': True})]:
                current = method(context, endpoint_id=endpoint_id)
                method(context, endpoint_id=endpoint_id, changes={'expected_revision': current['revision'], **values})
            limits = configuration['authorization']
            expiry = None if limits['minutes'] is None else (
                datetime.now(timezone.utc) + timedelta(minutes=limits['minutes'])).isoformat()
            access.issue(context, actor_agent_id=agent_id, endpoint_id=endpoint_id,
                actions=['open','send','steer','interrupt','close'], expires_at=expiry, max_executions=limits['actions'])
            result['binding'] = binding
        uow.connection.execute('INSERT INTO connection_setup_commits VALUES(?,?,?,?,?)',
            (context.actor_agent_id, request['client_intent_id'], digest, json.dumps(result), deps.clock.now_iso()))
        return result
