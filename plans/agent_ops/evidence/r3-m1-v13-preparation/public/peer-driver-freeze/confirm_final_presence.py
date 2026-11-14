"""Observe only the two declared tasks and exclusive availability of their port."""
from pathlib import Path
import json
import importlib.util
import socket
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import gate, invocation_inventory, main_guard, parser, public_save, read_json, require, require_tags, selection_can_start, sha
from m1_v13_observation import canonical_absence, endpoint
from m1_v13_confirm_cleanup import never_started_inputs
import driver_common


def local_only_connector_inputs(context, inventory):
    """Positive closed predecessor + finite local-only successor; not pristine operator auth."""
    current = invocation_inventory(context)
    require(current == inventory, 'LOCAL_ONLY_HISTORY_CHANGED')
    allowed = {('lifecycle', ('initialize',)), ('adopt_local', ('once',)),
        ('authorize_local', ('review',)), ('authorize_local', ('apply',)), ('operator_bootstrap', ('once',)),
        *(('lifecycle', ('nexus', action)) for action in ('install', 'start', 'stop', 'uninstall')),
        *(('work', ('local', phase)) for phase in ('useful', 'continuation'))}
    require(all((v['mode'], tuple(v['selection'])) in allowed and v.get('returned_sha256')
        and type(v.get('returncode')) is int for v in current.values()), 'CONNECTOR_SELECTION_OR_UNKNOWN_EFFECT')
    pin = context.P['adoption']['predecessor_closure_pin']
    require(sha(pin['path']) == pin['sha256'], 'PREDECESSOR_CLOSURE_CHANGED')
    previous = read_json(pin['path'])
    require(previous.get('all_temporary_tasks_absent') is True and previous.get('closed_without_force') is True,
        'CLOSED_PREDECESSOR_REQUIRED')
    connector = driver_common.owned_path(context.P['paths']['connector_state'], context.ROOT)
    require(connector.is_dir() and not any(connector.iterdir()), 'UNSELECTED_CONNECTOR_STATE_PRESENT')
    require(not any(path.name.startswith(('remote-', 'connector-', 'lifecycle-connector-', 'process-connector-'))
        for folder in (context.PUBLIC, context.PRIVATE) for path in folder.iterdir()), 'REMOTE_EFFECT_EVIDENCE_PRESENT')
    result = {'basis': 'CLOSED_PREDECESSOR_AND_COMPLETE_LOCAL_ONLY_SUCCESSOR',
        'invocations': current, 'predecessor_closure_sha256': pin['sha256'],
        'connector_state_empty': True, 'operator_pristine_required': False}
    checkpoint_path = context.PRIVATE / 'controller.json'
    if checkpoint_path.exists():
        before = sha(checkpoint_path); checkpoint = read_json(checkpoint_path)
        entry = context.P['execution_bundle']['files']['controller_token_collector']
        require(sha(entry['path']) == entry['sha256'], 'COLLECTOR_CHANGED')
        spec = importlib.util.spec_from_file_location('presence_token_collector', entry['path'])
        collector = importlib.util.module_from_spec(spec); spec.loader.exec_module(collector)
        state = collector.restore(checkpoint['collector'])
        from close_campaign import checkpoint_summary
        summary = checkpoint_summary(context, checkpoint, collector.summary(state))
        expected = context.P['adoption']['expected_scope']
        local_ids = {context.P['execution_bundle']['profiles']['local'] + '-work-0' + str(i) for i in (1, 2)}
        require(set(checkpoint['requests']) <= local_ids and set(checkpoint.get('owners', {})) <= {'local'}
            and all(v == context.P['paths']['server_home'] for v in checkpoint.get('owners', {}).values()),
            'NONLOCAL_CONTROLLER_OWNER')
        require(all(r.get('kind') == 'work' and r.get('lane') == 'local'
            and all(r.get('scope', {}).get(k) == expected[k] for k in collector.PRE_SCOPE)
            for r in checkpoint['requests'].values()), 'NONLOCAL_REQUEST_RESERVATION')
        require(set(state['requests']) <= local_ids and all(
            all(stream['scope'].get(k) == expected[k] for k in collector.PRE_SCOPE)
            for stream in state['streams'].values()), 'NONLOCAL_COLLECTOR_SCOPE')
        require(set(checkpoint.get('independent_owner_stops', {})) <= {'local'}
            and checkpoint.get('independent_observation', {}).get('worker_in_flight') is False,
            'LOCAL_WORKER_EXIT_UNCONFIRMED')
        require(sha(checkpoint_path) == before, 'CHECKPOINT_CHANGED_DURING_PRESENCE')
        result.update(controller_checkpoint_sha256=before, checkpoint_summary=summary)
    return result


def check_component(context, component, *, task_reader, inventory=None, absence=canonical_absence):
    inventory = invocation_inventory(context) if inventory is None else inventory
    expected = context.C['tasks'][component]
    require(task_reader(expected['name']) is None, 'TEMPORARY_TASK_STILL_PRESENT')
    public = context.PUBLIC
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
        if component == 'connector':
            local_only = local_only_connector_inputs(context, inventory)
        else:
            require(not any(selection_can_start(v, component) for v in inventory.values()), 'POSSIBLE_UNSELECTED_START')
            require(not any((public / name).exists() for name in ('remote-pty-reservation.json',
                'remote-host-handoff.json', 'remote-supervisor-checked.json'))
                and not (context.PRIVATE / 'controller.json').exists(), 'POSSIBLE_IMPLICIT_START')
    observed_absence = absence(context, component)
    if local_only is not None:
        require(local_only_connector_inputs(context, inventory) == local_only, 'LOCAL_ONLY_EVIDENCE_CHANGED')
    return {'name': expected['name'], 'absent': True, 'owner_cleanup_evidence': evidence,
        'canonical_absence': observed_absence, **({'unselected_scope_evidence': local_only} if local_only else {})}


def remote_helpers(context, inventory):
    public = context.PUBLIC
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
