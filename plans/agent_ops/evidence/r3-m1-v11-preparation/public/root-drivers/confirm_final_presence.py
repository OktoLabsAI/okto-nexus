"""Observe only the two declared tasks and exclusive availability of their port."""
from pathlib import Path
import json
import socket
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import gate, invocation_inventory, main_guard, parser, public_save, read_json, require, require_tags, selection_can_start, sha
from m1_v11_observation import canonical_absence, endpoint
from m1_v11_confirm_cleanup import never_started_inputs


def check_component(context, component, *, task_reader, inventory=None, absence=canonical_absence):
    inventory = invocation_inventory(context) if inventory is None else inventory
    expected = context.C['tasks'][component]
    require(task_reader(expected['name']) is None, 'TEMPORARY_TASK_STILL_PRESENT')
    public = context.ROOT / 'public'
    installed = public / ('lifecycle-' + component + '-install.json')
    selected = public / (component + '-owner-selection.json')
    evidence = {}
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
        require(not any(selection_can_start(v, component) for v in inventory.values()), 'POSSIBLE_UNSELECTED_START')
        require(not any((public / name).exists() for name in ('remote-pty-reservation.json',
            'remote-host-handoff.json', 'remote-supervisor-checked.json'))
            and not (context.ROOT / 'private/controller.json').exists(), 'POSSIBLE_IMPLICIT_START')
    observed_absence = absence(context, component)
    return {'name': expected['name'], 'absent': True, 'owner_cleanup_evidence': evidence,
        'canonical_absence': observed_absence}


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
