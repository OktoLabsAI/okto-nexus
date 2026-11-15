"""Finite migration/lifecycle selections. No credential or provider operation."""
from pathlib import Path
import subprocess
import time

from recovery_context import require, read_json, pin, sha
import recovery_observation as nexus
import recovery_connector as connector


def task_absent(context, component):
    service = nexus.installation(context) if component == 'nexus' else connector.installation(context)
    _, task = service.observe()
    require(task is None, 'OLD_TASK_MUST_BE_ABSENT')
    nexus.canonical_absence(context, component)


def preparation(context):
    require(not context.PUBLIC.exists() and not context.PRIVATE.exists(), 'PREPARATION_ALREADY_SELECTED')
    old_installation = read_json(pin(context.P['old_installation']))
    for source in context.P['source_contexts'].values():
        old_context = read_json(pin(source))
        require(Path(old_context['executable']).absolute() == Path(old_installation['python']).absolute()
                and Path(old_context['environment_prefix']).resolve() == Path(old_installation['python_prefix']).resolve(),
                'PREDECESSOR_PACKAGE_SCOPE_CHANGED')
    for component, item in context.P['predecessors'].items():
        proof = read_json(pin(item['presence']))
        exits = read_json(pin(item['exits']))
        require(proof['task_absent'] is True and proof['data_preserved'] is True
                and proof['force_used'] is False, 'NORMAL_CLOSED_PREDECESSOR_REQUIRED')
        require(set(exits['exits']) == set(nexus.ROLES)
                and all(v['physical_exit'] is True and v['exit_code'] == 0
                        for v in exits['exits'].values()), 'PREDECESSOR_PHYSICAL_EXIT_REQUIRED')
        data = proof['data']
        path = Path(data['path'])
        require(path.resolve().is_relative_to(context.ROOT.resolve()), 'PREDECESSOR_DATA_OUTSIDE_SCOPE')
        require(data.get('exists', True) is True and path.is_file() and sha(path) == data['sha256'],
                'PREDECESSOR_DATA_CHANGED')
        task_absent(context, component)
    from recovery_nexus import port_free
    port_free(context)
    for item in context.installed['files']:
        pin(item)
    context.PUBLIC.mkdir()
    nexus.secure_directory(context.PRIVATE, context.CONTROL)
    value = {'status': 'PREPARED', 'payload_count': len(context.installed['files']),
             'old_tasks_absent': True, 'old_data_hashes_unchanged': True,
             'model_admissions': 0, 'service_effects': False}
    context.save('preparation.json', value)
    return value


def upgrade_argv(context, component, action, revision=None):
    python = context.python
    if component == 'nexus':
        result = [python, '-I', '-B', '-X', 'utf8', '-m', 'okto_nexus.adapters.inbound.cli.main',
                  'service', action, '--home', context.P['paths']['server_home'], '--json']
    else:
        require(component == 'connector', 'COMPONENT_INVALID')
        result = [python, '-I', '-B', '-X', 'utf8', '-m', 'okto_nexus_connector.cli.main',
                  '--non-interactive', '--json', '--state-dir', context.P['paths']['connector_state'],
                  'service', action]
    document = context.PRIVATE / (component + '-upgrade-plan.json')
    if action == 'upgrade-plan':
        return result + ['--python', python, '--output', str(document)]
    require(action == 'upgrade-apply' and isinstance(revision, str) and len(revision) == 64,
            'EXPLICIT_UPGRADE_REVISION_REQUIRED')
    return result + ['--plan-file', str(document), '--expected-revision', revision]


def validate_upgrade(context, component, document):
    body = document['plan']
    require(body['component'] == component
            and body['instance_id'] == context.C['tasks'][component]['instance_id'], 'UPGRADE_SCOPE_CHANGED')
    source = read_json(pin(context.P['source_contexts'][component]))
    require(body['source_context'] == source, 'UPGRADE_SOURCE_CHANGED')
    candidate, target = body['candidate'], body['target_context']
    require(Path(candidate['executable']).absolute() == Path(context.python).absolute()
            and Path(candidate['environment_prefix']).resolve() == Path(context.installed['python_prefix']).resolve(),
            'UPGRADE_TARGET_NOT_PINNED_PACKAGE')
    mutable = {'revision', 'executable', 'environment_prefix', 'package_version', 'core_version', 'environment_fingerprint'}
    require({k: v for k, v in source.items() if k not in mutable}
            == {k: v for k, v in target.items() if k not in mutable}, 'UPGRADE_CHANGED_EXECUTION_SCOPE')
    require(target['executable'] == candidate['executable']
            and target['environment_prefix'] == candidate['environment_prefix'], 'UPGRADE_TARGET_MISMATCH')
    require(body['source_receipt'] is None and 'source_native_xml' not in body,
            'UPGRADE_EXPECTED_ABSENT_TASK')
    return {'component': component, 'plan_revision': document['plan_revision'],
            'source_executable': source['executable'], 'target_executable': target['executable'],
            'instance_id': body['instance_id'], 'source_generation': body['source_generation'],
            'candidate_package': candidate['package'], 'candidate_core': candidate['core'],
            'unchanged_execution_scope': True, 'task_absent': True, 'model_admissions': 0}


def run_cli(context, component, action, argv):
    name = component + '-' + action
    context.save(name + '-reserved.json', {'state': 'RESERVED_BEFORE_DISPATCH', 'argv': argv,
                                         'model_admissions': 0, 'force_used': False})
    output, error = context.PRIVATE / (name + '.stdout'), context.PRIVATE / (name + '.stderr')
    environment = context.env() if component == 'nexus' else context.connector_env()
    with output.open('xb') as out, error.open('xb') as err:
        child = subprocess.Popen(argv, cwd=context.ROOT, env=environment, stdout=out, stderr=err,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            code = child.wait(timeout=180)
        except subprocess.TimeoutExpired:
            context.save(name + '-pending.json', {'state': 'WRAPPER_PENDING_NO_REPLAY', 'pid': child.pid,
                                                 'force_used': False, 'new_control_selected': False})
            # Keep the actual launched process handle until normal exit or finite observation bound.
            try:
                child.wait(timeout=7200)
            except subprocess.TimeoutExpired:
                pass
            raise RuntimeError('UPGRADE_WRAPPER_UNCONFIRMED_NO_REPLAY') from None
    try:
        raw = read_json(output)
        value = raw.get('data', raw)
        require(isinstance(value, dict), 'CLI_RESULT_NOT_OBJECT')
        projection = {k: value[k] for k in ('applied', 'state', 'code', 'reason', 'plan_revision') if k in value}
    except Exception:
        projection = {'state': 'OUTPUT_UNCONFIRMED'}
    return {'returncode': code, 'projection': projection, 'stdout_sha256': sha(output),
            'stderr_sha256': sha(error), 'wrapper_exit_confirmed': True}


def migration(context, component, action, revision=None):
    context.require_tags(read_json(context.PUBLIC / 'preparation.json'))
    task_absent(context, component)
    document_path = context.PRIVATE / (component + '-upgrade-plan.json')
    if action == 'upgrade-plan':
        pin(context.P['source_contexts'][component])
    else:
        require(action == 'upgrade-apply', 'MIGRATION_ACTION_INVALID')
        previous = read_json(context.PUBLIC / (component + '-upgrade-plan-returned.json'))
        context.require_tags(previous)
        require(previous['returncode'] == 0 and sha(document_path) == previous['document_sha256'], 'REVIEWED_PLAN_CHANGED')
        document = read_json(document_path)
        validate_upgrade(context, component, document)
        require(revision == document['plan_revision'], 'EXPLICIT_REVIEW_REVISION_CHANGED')
        for item in context.installed['files']:
            pin(item)
    value = run_cli(context, component, action, upgrade_argv(context, component, action, revision))
    if value['returncode'] == 0:
        if action == 'upgrade-plan':
            value['review'] = validate_upgrade(context, component, read_json(document_path))
            value['document_sha256'] = sha(document_path)
        else:
            require(value['projection'].get('applied') is True, 'UPGRADE_NOT_CONFIRMED')
            target = read_json(document_path)['plan']['target_context']
            actual = read_json(context.P['source_contexts'][component]['path'])
            require(actual == target, 'APPLIED_CONTEXT_NOT_EXACT_TARGET')
            task_absent(context, component)
            value['target_context_sha256'] = sha(context.P['source_contexts'][component]['path'])
    context.save(component + '-' + action + '-returned.json', value)
    return value


def dispatch(context, component, action, revision=None):
    if action == 'prepare':
        require(component == 'both', 'PREPARE_BOTH_REQUIRED')
        return preparation(context)
    require(component in ('nexus', 'connector'), 'COMPONENT_INVALID')
    if action.startswith('upgrade-'):
        return migration(context, component, action, revision)
    if component == 'nexus':
        import recovery_nexus as host
    else:
        host = connector
    if action in ('install', 'start', 'stop', 'uninstall'):
        return host.lifecycle(context, action)
    if action == 'select':
        return host.select(context)
    if action == 'watch':
        return host.watch(context)
    require(action == 'cleanup', 'ACTION_INVALID')
    value = host.cleanup_valid(context)
    context.save('cleanup.json' if component == 'nexus' else 'connector-cleanup.json', value)
    return value
