"""Observe only the two declared tasks and exclusive availability of their port."""
from pathlib import Path
import json
import importlib.util
import socket
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import gate, invocation_inventory, main_guard, parser, public_save, read_json, require, require_tags, selection_can_start, sha
from m1_v12_observation import canonical_absence, endpoint
from m1_v12_confirm_cleanup import never_started_inputs
import driver_common


def local_setup_only_connector_inputs(context, inventory):
    """Narrow completed local failure path; no claim about setup/provider success."""
    directory = driver_common.HERE / 'runtime-private'
    current = invocation_inventory(context, directory)
    require(current == inventory, 'LOCAL_ONLY_HISTORY_CHANGED')
    mandatory = {'lifecycle-initialize', 'lifecycle-nexus-install', 'lifecycle-nexus-start',
                 'lifecycle-nexus-uninstall', 'plan-local_plan', 'setup-local'}
    names = {name.removesuffix('.reserved.json') for name in current}
    require(mandatory <= names <= mandatory | {'lifecycle-nexus-stop'}, 'LOCAL_ONLY_HISTORY_REQUIRED')
    require({p.name for p in directory.iterdir() if p.name.endswith(('.reserved.json', '.returned.json'))}
            == {name + suffix for name in names for suffix in ('.reserved.json', '.returned.json')},
            'LOCAL_ONLY_HISTORY_REQUIRED')
    for name, value in current.items():
        require(value.get('returned_sha256') and type(value.get('returncode')) is int,
                'LOCAL_ONLY_WRAPPER_EXIT_REQUIRED')
        if name != 'lifecycle-nexus-start.reserved.json':
            require(value['returncode'] == 0, 'LOCAL_ONLY_WRAPPER_RESULT_UNCONFIRMED')
    public = context.ROOT / 'public'
    allowed_public = {'authorization-reference.json', 'root-driver-preparation.json', 'live-accounting.json',
        'local-setup-dispatch.json', 'local-setup-result.json', 'local-setup-runner-error.json',
        'nexus-owner-selection.json', 'nexus-exit-watch-started.json', 'nexus-exit-proof.json',
        'cleanup-nexus.json', 'final-presence.json', 'closure.json',
        *('lifecycle-nexus-' + action + suffix for action in ('install', 'start', 'stop', 'uninstall')
          for suffix in ('.json', '-result.json')),
        *('process-nexus-' + action + '.json' for action in ('install', 'start', 'stop', 'uninstall'))}
    allowed_private = {'controller.json', 'controller.json.lock',
        *(name + suffix for name in ('local-setup', 'nexus-install', 'nexus-start', 'nexus-stop-wrapper',
          'nexus-stop', 'nexus-uninstall') for suffix in ('.stdout', '.stderr'))}
    public_names = {p.name for p in public.iterdir()}
    private_names = {p.name for p in (context.ROOT / 'private').iterdir()}
    require(public_names <= allowed_public and private_names <= allowed_private, 'NONLOCAL_ARTIFACT_PRESENT')
    for key in ('connector_state', 'operator_home'):
        root = driver_common.owned_path(context.P['paths'][key], context.ROOT)
        require(root.is_dir() and not any(root.iterdir()), 'REMOTE_STATE_NOT_PRISTINE')
    checkpoint_path = context.ROOT / 'private/controller.json'
    before = sha(checkpoint_path)
    checkpoint = read_json(checkpoint_path)
    entry = context.P['execution_bundle']['files']['controller_token_collector']
    require(sha(entry['path']) == entry['sha256'], 'COLLECTOR_CHANGED')
    spec = importlib.util.spec_from_file_location('presence_token_collector', entry['path'])
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)  # restore only; never imports/creates Controller
    state = collector.restore(checkpoint['collector'])
    from close_campaign import checkpoint_summary
    summary = checkpoint_summary(context, checkpoint, collector.summary(state))
    home = context.P['paths']['server_home']
    require(checkpoint.get('owners') == {'local': home}, 'NONLOCAL_CONTROLLER_OWNER')
    request_id = 'm1v12-local-setup'
    require(request_id in context.P['request_ids']['productive_setup']
            and set(checkpoint['requests']) == {request_id}, 'NONLOCAL_REQUEST_RESERVATION')
    request = checkpoint['requests'][request_id]
    require(request.get('kind') == 'setup' and request.get('lane') == 'local'
            and request['monitor'].get('home') == home, 'NONLOCAL_REQUEST_SCOPE')
    require(all(not state[k] for k in ('requests', 'streams', 'threads', 'turns'))
            and state['current_request'] is None, 'WORK_ACCOUNTING_PRESENT')
    require(set(checkpoint.get('independent_owner_stops', {})) <= {'local'}
            and checkpoint.get('independent_observation', {}).get('worker_in_flight') is False,
            'LOCAL_WORKER_EXIT_UNCONFIRMED')
    dispatch_path, result_path = public / 'local-setup-dispatch.json', public / 'local-setup-result.json'
    dispatch, result = read_json(dispatch_path), read_json(result_path)
    require(dispatch.get('request_id') == request_id and dispatch.get('reservation_persisted') is True,
            'LOCAL_SETUP_DISPATCH_REQUIRED')
    require(type(result.get('cli_exit')) is int and result['cli_exit'] != 0
            and type(result.get('started')) in (int, float) and type(result.get('finished')) in (int, float)
            and result['finished'] >= result['started'], 'LOCAL_SETUP_FINISHED_FAILURE_REQUIRED')
    require(sha(checkpoint_path) == before, 'CHECKPOINT_CHANGED_DURING_PRESENCE')
    return {'basis': 'COMPLETED_LOCAL_SETUP_FAILURE_CONNECTOR_NEVER_SELECTED',
            'invocations': current, 'controller_checkpoint_sha256': before,
            'setup_dispatch_sha256': sha(dispatch_path), 'setup_result_sha256': sha(result_path),
            'public_names': sorted(public_names), 'private_names': sorted(private_names),
            'checkpoint_summary': summary, 'setup_cli_exit': result['cli_exit'],
            'setup_success_inferred': False, 'provider_usage_final': False}


def check_component(context, component, *, task_reader, inventory=None, absence=canonical_absence):
    inventory = invocation_inventory(context) if inventory is None else inventory
    expected = context.C['tasks'][component]
    require(task_reader(expected['name']) is None, 'TEMPORARY_TASK_STILL_PRESENT')
    public = context.ROOT / 'public'
    installed = public / ('lifecycle-' + component + '-install.json')
    selected = public / (component + '-owner-selection.json')
    evidence = {}
    local_only = None
    if installed.exists() or selected.exists():
        # Deleting a task does not prove a detached owner died. Require the
        # selected physical owner proof and normal uninstall's actual result.
        cleanup_path = public / ('cleanup-' + component + '.json')
        cleanup = read_json(cleanup_path)
        require_tags(cleanup, context)
        require(cleanup.get('task_name') == expected['name']
            and cleanup.get('task_stopped_confirmed') is True and cleanup.get('force_used') is False,
            'PHYSICAL_CLEANUP_REQUIRED')
        if cleanup.get('kind') == 'NEVER_STARTED_OWNER_ABSENT':
            require(cleanup.get('owned_pid_birth_exit_confirmed') is False
                and cleanup.get('never_started_owner_absence_confirmed') is True, 'ABSENCE_PROOF_KIND_INVALID')
            current = never_started_inputs(context, component, allow_current_uninstall=True)
            previous = cleanup['base_evidence']
            require(current['install_action_sha256'] == previous['install_action_sha256']
                and current['install_result_sha256'] == previous['install_result_sha256'], 'INSTALL_EVIDENCE_CHANGED')
            require(all(current['invocations'].get(k) == v for k, v in previous['invocations'].items()), 'BASE_INVOCATION_CHANGED')
            require(set(current['invocations']) - set(previous['invocations']) <= {f'lifecycle-{component}-uninstall.reserved.json'},
                'INVOCATIONS_CHANGED_AFTER_ABSENCE_PROOF')
        else:
            require(cleanup.get('kind') == 'PHYSICAL_OWNER_EXIT'
                and cleanup.get('owned_pid_birth_exit_confirmed') is True, 'PHYSICAL_CLEANUP_REQUIRED')
        uninstall_path = public / ('lifecycle-' + component + '-uninstall-result.json')
        uninstall = read_json(uninstall_path)
        require(uninstall.get('component') == component and uninstall.get('action') == 'uninstall'
            and uninstall.get('task_name') == expected['name'] and uninstall.get('returncode') == 0
            and uninstall.get('cleanup_proof_sha256') == sha(cleanup_path),
            'UNINSTALL_RESULT_REQUIRED')
        uninstall_action = read_json(public / ('lifecycle-' + component + '-uninstall.json'))
        require(uninstall_action.get('cleanup_proof_sha256') == sha(cleanup_path), 'UNINSTALL_PROOF_PIN_REQUIRED')
        evidence = {'cleanup_sha256': sha(cleanup_path), 'uninstall_result_sha256': sha(uninstall_path)}
    else:
        require(not (public / ('lifecycle-' + component + '-start.json')).exists(), 'UNSELECTED_START_REQUIRES_RECONCILIATION')
        if component == 'connector' and any(v['mode'] == 'setup' and v['selection'] == ['local'] for v in inventory.values()):
            local_only = local_setup_only_connector_inputs(context, inventory)
        else:
            require(not any(selection_can_start(v, component) for v in inventory.values()), 'POSSIBLE_UNSELECTED_START')
            require(not any((public / name).exists() for name in ('remote-pty-reservation.json',
                'remote-host-handoff.json', 'remote-supervisor-checked.json'))
                and not (context.ROOT / 'private/controller.json').exists(), 'POSSIBLE_IMPLICIT_START')
    observed_absence = absence(context, component)
    if local_only is not None:
        require(local_setup_only_connector_inputs(context, inventory) == local_only, 'LOCAL_ONLY_EVIDENCE_CHANGED')
    return {'name': expected['name'], 'absent': True, 'owner_cleanup_evidence': evidence,
        'canonical_absence': observed_absence, **({'unselected_scope_evidence': local_only} if local_only else {})}


def remote_helpers(context, inventory):
    public = context.ROOT / 'public'
    possible = any(v['mode'] == 'remote_setup' for v in inventory.values()) or (public / 'remote-pty-reservation.json').exists()
    if not possible:
        return {'selected': False, 'basis': 'NO_REMOTE_SELECTION_OR_CANONICAL_RESERVATION'}
    path = public / 'remote-pty-result.json'
    value = read_json(path)
    require(value.get('proposal_sha256') == context.args.expected_proposal_sha256
        and value.get('worker_assigned_before_gate') is True and type(value.get('worker_exit')) is int
        and type(value.get('active_job_processes_after')) is int and value['active_job_processes_after'] == 0
        and value.get('public_ipc_readers_joined') is True and value.get('monitor', {}).get('worker_joined') is True
        and value.get('stop_order', {}).get('helper_drained') is True, 'REMOTE_HELPER_EXIT_UNCONFIRMED')
    return {'selected': True, 'owned_job_empty_confirmed': True, 'evidence_sha256': sha(path),
        'forced_auxiliary_cleanup': value.get('forced_owned_cleanup'), 'service_exit_inferred': False}


def main():
    context = gate(parser().parse_args())
    from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks
    inventory = invocation_inventory(context)
    helper_proof = remote_helpers(context, inventory)
    tasks = {c: check_component(context, c, task_reader=WindowsTasks().read, inventory=inventory) for c in ('nexus', 'connector')}
    host, port = endpoint(context)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind((host, port))
    result = {'status': 'NORMAL_CLEANUP_CONFIRMED', 'tasks': tasks, 'invocation_evidence': inventory,
        'remote_helper_evidence': helper_proof,
        'exclusive_port_probe_passed_not_reserved': port, 'observed_at': time.time(),
        'data_directories_retained': all(Path(context.P['paths'][k]).is_dir()
            for k in ('server_home', 'connector_state', 'private_evidence', 'public_evidence')),
        'force_used': False, 'database_read': False,
        'scope': 'Exact temporary tasks, retained selected owners, normal removal and instantaneous port availability only; no work/accounting conclusion.'}
    require(result['data_directories_retained'], 'CAMPAIGN_DIRECTORIES_NOT_RETAINED')
    public_save(context, 'final-presence.json', result)
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main_guard(main))
