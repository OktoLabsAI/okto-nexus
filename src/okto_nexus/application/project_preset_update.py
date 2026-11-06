"""Optional evolution of the one project preset through ordinary setup Finish."""
from copy import deepcopy
import json

from ..bootstrap.execution_authority import ExecutionToolDependencies, build_execution_access
from ..errors import ErrorCode, OktoNexusError
from .execution_local_realizations import _digest
from . import project_preset


def stored_preset(conn, binding_id):
    row = conn.execute('SELECT result_json FROM connection_setup_commits '
        "WHERE json_extract(result_json,'$.binding.binding_id')=? "
        "AND json_type(result_json,'$.project_preset')='object' ORDER BY created_at DESC,rowid DESC LIMIT 1",
        (binding_id,)).fetchone()
    return json.loads(row['result_json']) if row else {}


def merge_defaults(current, previous, recommended, path=''):
    """Only unchanged old defaults advance. Unknown/manual values stay explicit."""
    proposed, changes, preserved = deepcopy(current), [], []
    for key, value in recommended.items():
        name = path + key
        before = current.get(key)
        known = previous is not None and key in previous
        if isinstance(value, dict) and isinstance(before, dict):
            base = previous.get(key) if known and isinstance(previous[key], dict) else None
            proposed[key], nested, kept = merge_defaults(before, base, value, name + '.')
            changes.extend(nested)
            preserved.extend(kept)
        elif before != value or key not in current:
            if previous is not None and ((known and key in current and before == previous[key]) or
                                          (not known and key not in current)):
                proposed[key] = deepcopy(value)
                changes.append(dict(field=name, before=before, after=value))
            else:
                preserved.append(dict(field=name, current=before, recommendation=value))
    for key, before in (previous or {}).items():
        if key not in recommended and key in current:
            if current[key] == before:
                proposed.pop(key)
                changes.append(dict(field=path + key, before=before, after=None, removed=True))
            else:
                preserved.append(dict(field=path + key, current=current[key], recommendation=None))
    return proposed, changes, preserved


def authorization_effects(conn, agent_id, endpoint_id, current, configuration):
    """Explain existing runtime/endpoint invalidation, including other bindings."""
    policy = current['runtime_policy']
    effective = {key: configuration[key] if configuration[key] is not None else policy['defaults'][key]
        for key in ('runtime_enabled', 'session_policy')}
    all_connections = any(effective[key] != policy['effective'][key] for key in effective)
    endpoint = conn.execute('SELECT response_policy,consumption FROM agent_endpoints WHERE endpoint_id=?',
        (endpoint_id,)).fetchone()
    public = current['public_config']
    selected = (configuration['harness_settings'] != public.get('harness_settings', {}) or
        configuration['tool_access'] != public.get('nexus_tool_permission', 'ask') or
        endpoint['response_policy'] != 'conversation' or endpoint['consumption'] != 'exclusive')
    if not all_connections and not selected:
        return dict(connections=[], revoked_grant_ids=[], disabled_boot_endpoint_ids=[]), _digest({})
    args = (agent_id, all_connections, endpoint_id)
    predicate = 'e.agent_id=? AND (? OR e.endpoint_id=?)'
    connections = [dict(row) for row in conn.execute(
        "SELECT e.endpoint_id,b.binding_id,e.workspace_id,json_extract(e.public_config,'$.alias') AS alias,"
        'w.display_name AS workspace_label FROM agent_endpoints e '
        'LEFT JOIN execution_bindings b ON b.endpoint_id=e.endpoint_id '
        'LEFT JOIN workspaces w ON w.workspace_id=e.workspace_id WHERE ' + predicate + ' ORDER BY e.endpoint_id', args)]
    grants = [dict(row) for row in conn.execute('SELECT g.* FROM runtime_execution_grants g '
        'JOIN agent_endpoints e ON e.endpoint_id=g.endpoint_id WHERE ' + predicate +
        ' AND g.revoked_at IS NULL ORDER BY g.grant_id', args)]
    boot = [dict(row) for row in conn.execute('SELECT b.* FROM runtime_boot_bindings b '
        'JOIN agent_endpoints e ON e.endpoint_id=b.endpoint_id WHERE ' + predicate +
        ' AND b.enabled=1 ORDER BY b.endpoint_id', args)]
    return dict(connections=connections, revoked_grant_ids=[row['grant_id'] for row in grants],
        disabled_boot_endpoint_ids=[row['endpoint_id'] for row in boot]), _digest(dict(grants=grants, boot=boot))


def review_in_uow(deps, context, uow, agent_id, binding_id):
    from .connection_setup import SetupTransaction, load_setup, require_operator, conflict
    from .connection_authorization import snapshot
    require_operator(build_execution_access(deps), context, uow)
    authority = snapshot(deps, uow, binding_id)
    if authority['scope']['agent_id'] != agent_id:
        raise conflict('The selected binding belongs to another identity.')
    scoped = ExecutionToolDependencies(deps, SetupTransaction(deps.connection_factory, uow))
    current = load_setup(scoped, context, agent_id, binding_id)
    binding = next((row for row in current['connections'] if row['binding_id'] == binding_id), None)
    if binding is None:
        raise conflict('Select an approved existing project connection.')
    saved = stored_preset(uow.connection, binding_id)
    origin = saved.get('project_preset')
    previous = saved.get('project_preset_defaults')
    if previous is None and origin == dict(id='project-generalist', revision=1):
        previous = deepcopy(project_preset.REVISION_1_DEFAULTS)
    if origin is not None and (origin.get('id') != project_preset.ORIGIN['id'] or not isinstance(previous, dict)):
        raise conflict('The stored preset base is unavailable. Preserve this configuration and review its settings explicitly.')
    if origin is not None and (type(origin.get('revision')) is not int or
                               origin['revision'] > project_preset.ORIGIN['revision']):
        raise conflict('This connection records a newer preset. Use compatible Server software; no downgrade was proposed.')
    public = current['public_config']
    workspace = uow.connection.execute('SELECT display_name FROM workspaces WHERE workspace_id=?',
        (binding['workspace_id'],)).fetchone()
    folders = current.get('folders', {})
    configuration = project_preset.configuration(adapter_id=binding['adapter_id'],
        project=folders.get('workspace_root', ''), label=workspace['display_name'],
        provider_home=folders.get('provider_home'))
    configuration.update(execution_location=binding['execution_location'],
        runtime_enabled=current['runtime_policy']['runtime_enabled'],
        session_policy=current['runtime_policy']['session_policy'],
        secret_bindings=deepcopy(folders.get('secret_bindings', {})),
        alias=public['alias'], harness_settings=deepcopy(public.get('harness_settings', {})),
        tool_access=public.get('nexus_tool_permission', 'ask'),
        authorization=deepcopy(current.get('authorization', (previous or configuration)['authorization'])))
    recommended = project_preset.configuration_defaults()
    selected = {key: configuration[key] for key in recommended}
    proposed, changes, preserved = merge_defaults(selected, previous, recommended)
    configuration.update(proposed)
    invalidations, affected_authority = authorization_effects(uow.connection, agent_id,
        authority['scope']['endpoint_id'], current, configuration)
    inventory = uow.connection.execute('SELECT inventory_revision FROM execution_inventory_current '
        'WHERE server_id=? AND executor_id=?',
        (authority['scope']['server_id'], binding['executor_id'])).fetchone()
    active = configuration['runtime_enabled']
    if active is None:
        active = current['runtime_default']
    request = dict(agent_id=agent_id, executor_id=binding['executor_id'], binding_id=binding_id,
        candidate_ref=binding['candidate_ref'], inventory_revision=inventory['inventory_revision'] if inventory else '',
        workspace_id=binding['workspace_id'], baseline=current['baseline'],
        configuration=configuration, project_preset=deepcopy(project_preset.ORIGIN))
    effects = ['Keep the same identity, name, role, coordination permissions, workspace, binding and host paths.',
        'Keep native sandbox decisions, customized harness settings, MCP servers and Server-wide policy.',
        'Apply the listed configuration changes only after this review is approved; concurrent changes require a new review.']
    if invalidations['connections']:
        effects.append('Canonical configuration changes revoke the listed execution grants and disable the listed boot approvals. Agent-wide runtime/session policy changes affect every connection of this identity; only the selected connection can receive new authorization below.')
    if active:
        limits = configuration['authorization']
        duration = str(limits['minutes']) + ' minutes' if limits['minutes'] is not None else 'unlimited time'
        budget = str(limits['actions']) + ' actions' if limits['actions'] is not None else 'unlimited actions'
        effects.append('Finish issues new execution authorization for ' + duration + ' and ' + budget +
            '; no revoked grant or disabled boot approval is restored.')
        if binding['execution_location'] == 'local':
            effects.append('Recheck and test the selected local harness before Finish. The model test may incur provider charges; close existing sessions explicitly if replacement is refused.')
        else:
            effects.append('Update the approved remote connection on the Server; no host paths or credentials are changed and no remote test or task is submitted.')
    else:
        effects.append('Runtime stays disabled. No harness test, execution grant or project task is requested.')
    review = dict(format_version=1, state='up_to_date' if origin == project_preset.ORIGIN else 'review',
        source_origin=origin, target_origin=deepcopy(project_preset.ORIGIN), changes=changes,
        preserved=preserved, effects=effects, actions=authority['actions'], authority_changes=invalidations,
        new_authorization=dict(scope=authority['scope'], actions=authority['actions'],
            limits=configuration['authorization']) if active else None,
        local_test_required=bool(active and binding['execution_location'] == 'local'))
    # Inventory publication can advance during the separately reviewed version
    # check; actual installation/test selection remains fenced by existing setup.
    revision = _digest(dict(review=review, configuration=request | {'inventory_revision': ''},
        authorization=authority['expected_revision'], affected_authority=affected_authority, defaults=recommended))
    request['preset_update'] = dict(review_revision=revision)
    return review | dict(review_revision=revision, request=request)


def prepare_preset_update(deps, context, agent_id, binding_id):
    with deps.connection_factory.unit_of_work(write=False) as uow:
        return review_in_uow(deps, context, uow, agent_id, binding_id)


def validate_preset_update(deps, context, uow, request):
    if request.get('preset_update') is None:
        return None
    from .connection_setup import conflict
    if not request.get('binding_id'):
        raise conflict('Preset evolution requires an existing project binding.')
    review = review_in_uow(deps, context, uow, request['agent_id'], request['binding_id'])
    actual = {key: value for key, value in request.items() if key not in ('client_intent_id', 'inventory_revision')}
    expected = {key: value for key, value in review['request'].items() if key != 'inventory_revision'}
    if review['state'] == 'up_to_date' or actual != expected:
        raise conflict('The preset review or project changed. Review the current diff before applying it.')
    return review


def validate_origin(request):
    origin = request.get('project_preset')
    if origin is None:
        return
    if (not isinstance(origin, dict) or set(origin) != {'id', 'revision'} or
            origin['id'] != project_preset.ORIGIN['id'] or type(origin['revision']) is not int or
            not 1 <= origin['revision'] <= project_preset.ORIGIN['revision']):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'Unknown project preset revision.', {})
    if origin != project_preset.ORIGIN:
        raise OktoNexusError(ErrorCode.CONFLICT, 'The project preset changed. Review the current recommendation.', {})
