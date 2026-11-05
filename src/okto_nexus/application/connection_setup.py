"""Atomic connection setup. No canonical configuration is changed by a draft test."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json

from ..bootstrap.execution_authority import ExecutionToolDependencies, build_execution_access
from ..errors import ErrorCode, OktoNexusError
from .execution_local_realizations import _digest, directory_identity, stage_embedded_realization
from . import agent_execution_policy, runtime_policy, runtime_mcp_presets


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


def setup_actor(context):
    """Use the same canonical audit identity for every Finish/receipt path."""
    return context.actor_agent_id or 'operator'


def refresh_committed_native_policy(deps, result, settings):
    if settings is not None and result.get('native_decision_policy', {}).get('initialized'):
        try:
            settings.refresh_native_decisions(deps.connection_factory)
        except (OktoNexusError, OSError) as error:
            raise OktoNexusError(ErrorCode.CONFLICT,
                'Setup is committed; Server policy refresh is pending. Recover this same setup ID.',
                {'reason': 'SETUP_ACTIVATION_PENDING'}) from error


def read_setup_commit(deps, context, setup_run_id, *, expected_request=None, settings=None):
    """Recover the committed result without testing, regranting or reapplying."""
    if not isinstance(setup_run_id, str) or not 1 <= len(setup_run_id) <= 100:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid setup run ID.', {})
    with deps.connection_factory.unit_of_work(write=False) as uow:
        require_operator(build_execution_access(deps), context, uow)
        row = uow.connection.execute('SELECT * FROM connection_setup_commits '
            'WHERE actor_agent_id=? AND client_intent_id=?', (setup_actor(context), setup_run_id)).fetchone()
        if row is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND,
                'No committed Finish receipt exists for this setup run. Test or host effects may still be pending.', {})
        if expected_request is not None and row['request_hash'] != _digest(expected_request):
            raise conflict('This Finish request has different content.')
        receipt = {'setup_run_id': setup_run_id, 'request_hash': row['request_hash'],
                   'state': 'committed', 'result': json.loads(row['result_json'])}
    refresh_committed_native_policy(deps, receipt['result'], settings)
    return receipt


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


def setup_mcp_preset(uow, request):
    """Check the original preset revision before testing or replacing a binding."""
    draft = request.get('mcp_preset')
    if draft is None:
        return None  # Older clients leave the existing preset untouched.
    from nexus_connector_core.mcp_presets import validate_mcp_preset
    from nexus_connector_core import CoreError
    try:
        servers = validate_mcp_preset(draft['servers'])
    except (CoreError, KeyError, TypeError) as error:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid runtime MCP preset.', {}) from error
    if (not runtime_enabled(uow.connection, request['configuration']) or
            (request['configuration']['execution_location'] == 'remote' and not request.get('binding_id'))):
        raise conflict('Select a runtime connection before configuring its MCP servers.')
    revision = 0
    if request.get('binding_id'):
        row = uow.connection.execute('SELECT b.endpoint_id FROM execution_bindings b '
            'JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id WHERE b.binding_id=? AND e.agent_id=?',
            (request['binding_id'], request['agent_id'])).fetchone()
        if row is None:
            raise conflict('The selected connection is no longer available.')
        revision = runtime_mcp_presets.snapshot(uow.connection, row['endpoint_id'])['revision']
    if type(draft.get('expected_revision')) is not int or draft['expected_revision'] != revision:
        raise conflict('The MCP preset changed while you were editing. Reopen Connections to review it.')
    return servers


def validate_agent_creation(deps, uow, request):
    draft = request.get('agent_creation')
    if draft is None:
        return None
    from .agent_creation import validate_agent_id
    from .project_preset import ORIGIN, identity_defaults
    validate_agent_id(request['agent_id'])
    defaults = identity_defaults()
    if (not isinstance(draft, dict) or set(draft) != {'display_name', 'defaults_hash'} or
            not isinstance(draft['display_name'], str) or not 1 <= len(draft['display_name']) <= 120 or
            not draft['display_name'].strip() or request.get('project_preset') != ORIGIN or
            request['configuration']['execution_location'] != 'local' or
            request['configuration']['runtime_enabled'] is not True or request.get('binding_id')):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Invalid project identity creation review.', {})
    if draft['defaults_hash'] != defaults['defaults_hash']:
        raise conflict('Project identity defaults changed. Review the current role and permissions before creating the agent.')
    if deps.repos.agents.get(uow, request['agent_id']) is not None:
        raise conflict('The proposed agent ID now exists. Review another ID; the existing identity was not adopted.')
    return defaults


def validate_native_policy(uow, request, settings):
    review = request.get('native_decision_policy')
    if review is None:
        return  # Older clients do not initialize or overwrite Server policy.
    from .project_preset import ORIGIN
    if (settings is None or request.get('project_preset') != ORIGIN or
            request['configuration']['runtime_enabled'] is not True):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Native decision policy requires a reviewed project setup.', {})
    settings.validate_native_decisions(uow, review)


def load_setup(deps, context, agent_id, binding_id=None, *, new_agent_draft=False, settings=None):
    access = build_execution_access(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        require_operator(access, context, uow)
        if new_agent_draft:
            from .agent_creation import validate_agent_id
            validate_agent_id(agent_id)
            if binding_id or access.agents.get(uow, agent_id) is not None:
                raise conflict('Select an unused agent ID for the new identity review.')
        elif access.agents.get(uow, agent_id) is None:
            raise OktoNexusError(ErrorCode.NOT_FOUND, 'Agent does not exist.', {})
        result = {'baseline': baseline(uow, agent_id, binding_id),
                  'runtime_policy': runtime_policy.public_view(deps, runtime_policy.view(uow.connection, agent_id)),
                  'runtime_default': runtime_policy.defaults(uow.connection)['runtime_enabled']}
        if settings is not None:
            result['native_decision_policy'] = settings.native_decision_review(uow)
        if new_agent_draft:
            from .project_preset import identity_defaults
            result['agent_creation_defaults'] = identity_defaults()
        result['connections'] = [dict(row) for row in uow.connection.execute(
            "SELECT b.binding_id,b.candidate_ref,b.executor_id,e.workspace_id,e.adapter_id,"
            "CASE WHEN x.kind='remote' THEN 'remote' ELSE 'local' END execution_location "
            'FROM execution_bindings b JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id '
            'JOIN execution_executors x ON x.server_id=b.server_id AND x.executor_id=b.executor_id '
            "WHERE e.agent_id=? AND e.enabled=1 AND e.activation_state='approved' "
            'ORDER BY e.workspace_id,e.adapter_id', (agent_id,))]
        if binding_id:
            row = uow.connection.execute('SELECT e.endpoint_id,e.public_config,e.response_policy,l.local_record_json FROM execution_bindings b '
                'JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id '
                'LEFT JOIN execution_local_realizations l ON l.server_id=b.server_id AND l.executor_id=b.executor_id '
                'AND l.realization_ref=b.realization_ref WHERE b.binding_id=? AND e.agent_id=?',
                (binding_id, agent_id)).fetchone()
            if row:
                origin = uow.connection.execute('SELECT result_json FROM connection_setup_commits '
                    "WHERE json_extract(result_json,'$.binding.binding_id')=? "
                    "AND json_type(result_json,'$.project_preset')='object' ORDER BY created_at DESC LIMIT 1",
                    (binding_id,)).fetchone()
                if origin:
                    result['project_preset'] = json.loads(origin['result_json'])['project_preset']
                result['mcp_preset'] = runtime_mcp_presets.snapshot(uow.connection, row['endpoint_id'])
                if row['local_record_json']:
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


def finish_setup(deps, context, owner, fresh, request, *, verified, settings=None):
    if request.get('native_decision_policy') is not None and settings is None:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'The Server policy service is required for this review.', {})
    result = _finish_setup(deps, context, owner, fresh, request, verified=verified, settings=settings)
    # The receipt and stored policy are committed before runtime consumers
    # see the setting. Repeated Finish refreshes current policy, not defaults.
    refresh_committed_native_policy(deps, result, settings)
    return result


def _finish_setup(deps, context, owner, fresh, request, *, verified, settings):
    from .execution_binding_proposals import prepare_execution_binding, apply_execution_binding
    from ..adapters.inbound.mcp.tools.harness import build_endpoint_service
    agent_id, configuration = request['agent_id'], request['configuration']
    digest = _digest(request)
    with deps.connection_factory.unit_of_work() as uow:
        scoped = ExecutionToolDependencies(deps, SetupTransaction(deps.connection_factory, uow))
        access = build_execution_access(scoped)
        access.authorize_maintenance(context, uow=uow)
        # Human dashboard operators have no agent identity. Use the same
        # operator audit identity as execution grants, only after authorization.
        commit_actor = setup_actor(context)
        prior = uow.connection.execute('SELECT * FROM connection_setup_commits WHERE actor_agent_id=? '
            'AND client_intent_id=?', (commit_actor, request['client_intent_id'])).fetchone()
        if prior:
            if prior['request_hash'] != digest:
                raise conflict('This Finish request has different content.')
            return json.loads(prior['result_json'])
        if baseline(uow, agent_id, request.get('binding_id')) != request['baseline']:
            raise conflict('The active configuration changed while you were editing. Reopen Connections to review it.')
        validate_native_policy(uow, request, settings)
        identity = validate_agent_creation(deps, uow, request)
        if identity is not None:
            from .agent_creation import create_agent_in_uow
            from .auth import AgentKeyAuthService
            # The same creation/key authority as the operator Agents API. Only
            # a new identity can enter here, so no existing key cache is rotated.
            # Managed harnesses use scoped capabilities; no permanent key is
            # exported or persisted in the terminal profile/Finish receipt.
            create_agent_in_uow(deps, uow, AgentKeyAuthService(deps.repos.agents, deps.clock),
                agent_id=agent_id, role=identity['role'], permissions=identity['permissions'],
                metadata={'display_name': request['agent_creation']['display_name']})
        preset = setup_mcp_preset(uow, request)
        active = runtime_enabled(uow.connection, configuration)
        policy_changes = dict(
            expected_revision=request['baseline']['runtime_revision'], runtime_enabled=configuration['runtime_enabled'],
            session_policy=configuration['session_policy'])
        if 'broadcast_handoff_auto_claim' in request:
            policy_changes['broadcast_handoff_auto_claim'] = request['broadcast_handoff_auto_claim']
        runtime_policy.save_policy(scoped, context, agent_id=agent_id, changes=policy_changes)
        if active or configuration['adapter_id']:
            agent_execution_policy.save_policy(scoped, context, agent_id,
                expected_revision=request['baseline']['execution_revision'],
                execution_location=configuration['execution_location'], local_adapter_id=configuration['adapter_id'] or None)
        result = {'saved': True, 'agent_id': agent_id}
        if identity is not None:
            result['agent_created'] = True
        if request.get('project_preset') is not None:
            from .project_preset import ORIGIN
            if (request['project_preset'] != ORIGIN or
                    type(request['project_preset'].get('revision')) is not int):
                raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Unknown project preset revision.', {})
            result['project_preset'] = dict(ORIGIN)
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
            if preset is not None:
                current_preset = runtime_mcp_presets.snapshot(uow.connection, endpoint_id)
                runtime_mcp_presets.save(uow.connection, endpoint_id=endpoint_id,
                    expected_revision=current_preset['revision'], servers=preset)
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
            actions = ['open','send','steer','interrupt','close']
            if runtime_policy.effective(uow.connection, agent_id)['broadcast_handoff_auto_claim']:
                actions.append('execute_work')
            access.issue(context, actor_agent_id=agent_id, endpoint_id=endpoint_id,
                actions=actions, expires_at=expiry, max_executions=limits['actions'])
            result['binding'] = binding
        if request.get('native_decision_policy') is not None:
            settings.stage_native_decisions(uow, request['native_decision_policy'])
            result['native_decision_policy'] = dict(enabled_at_commit=True,
                initialized=request['native_decision_policy']['initialize'])
        uow.connection.execute('INSERT INTO connection_setup_commits VALUES(?,?,?,?,?)',
            (commit_actor, request['client_intent_id'], digest, json.dumps(result), deps.clock.now_iso()))
        return result
