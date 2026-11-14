"""Publish the same finite cleanup proof required by lifecycle uninstall."""
from pathlib import Path
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import gate, invocation_inventory, main_guard, parser, public_save, read_json, require, require_tags, sha
from m1_v11_observation import IDENTITY, canonical_absence


def validate_exit(selected, proof, drain, task, expected):
    require(proof.get('retained_handle') is True and proof.get('exit_confirmed') is True
        and proof.get('wait_result') == 0 and proof.get('force_used') is False, 'PHYSICAL_EXIT_REQUIRED')
    require(all(proof.get(k) == selected.get(k) for k in (*IDENTITY, 'birth_filetime', 'component')),
        'EXIT_OWNER_CHANGED')
    require(drain.get('state') == 'DRAINED' and drain.get('generation') == proof['generation'], 'EXACT_DRAIN_REQUIRED')
    require(selected['instance_id'] == expected['instance_id'] and selected['task']['name'] == expected['name'],
        'TASK_IDENTITY_CHANGED')
    require(task is not None and task.state in (1, 3) and task.digest == selected['task']['digest'], 'TASK_STOP_UNCONFIRMED')


def never_started_inputs(context, component, *, allow_current_uninstall=False, directory=None):
    ledger = invocation_inventory(context, directory,
        allow_pending_uninstall=component if allow_current_uninstall else None)
    for name, value in ledger.items():
        selection = value['selection']
        safe = selection == ['initialize'] or (len(selection) == 2 and selection[0] in ('nexus', 'connector')
            and selection[1] in ('install', 'uninstall'))
        require(value['mode'] == 'lifecycle' and safe, 'START_OR_IMPLICIT_START_SELECTED')
        if value['returned_sha256'] is not None:
            require(value['returncode'] == 0, 'PRIOR_INVOCATION_UNCONFIRMED')
    require('lifecycle-initialize.reserved.json' in ledger
        and f'lifecycle-{component}-install.reserved.json' in ledger, 'INSTALL_ONLY_LEDGER_INCOMPLETE')
    public = context.ROOT / 'public'
    prohibited = ['lifecycle-nexus-start.json', 'lifecycle-connector-start.json',
        'remote-pty-reservation.json', 'remote-host-handoff.json', 'remote-supervisor-checked.json',
        'nexus-owner-selection.json', 'connector-owner-selection.json']
    require(not any((public / name).exists() for name in prohibited)
        and not (context.ROOT / 'private/controller.json').exists(), 'START_OR_REMOTE_STATE_EXISTS')
    action = public / f'lifecycle-{component}-install.json'
    result_path = public / f'lifecycle-{component}-install-result.json'
    record, result = read_json(action), read_json(result_path)
    expected = context.C['tasks'][component]
    require(record.get('proposal_sha256') == context.args.expected_proposal_sha256
        and all(v.get('component') == component and v.get('action') == 'install'
            and v.get('task_name') == expected['name'] for v in (record, result))
        and result.get('returncode') == 0, 'CANONICAL_INSTALL_NOT_CONFIRMED')
    return {'invocations': ledger, 'install_action_sha256': sha(action), 'install_result_sha256': sha(result_path)}


def live_never_started(context, component):
    absence = canonical_absence(context, component)
    if component == 'nexus':
        from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation, CONTROL_NAME
        home = Path(context.P['paths']['server_home'])
        service = ServerInstallation(home, home / 'nexus.db')
        receipt_path, control_path = service.path, home / CONTROL_NAME
    else:
        from okto_nexus_connector.platform.user_service import UserService
        from okto_nexus_connector.platform.service_context import INSTALLATION, CONTROL
        home = Path(context.P['paths']['connector_state'])
        service = UserService(home)
        receipt_path, control_path = home / INSTALLATION, home / CONTROL
    receipt_before, control_before = sha(receipt_path), sha(control_path)
    receipt, task = service.observe()  # independently checks owner/definition/context
    control = service.control(receipt)
    expected = context.C['tasks'][component]
    require(receipt['name'] == expected['name'] and receipt['instance_id'] == expected['instance_id'], 'INSTALLATION_IDENTITY_CHANGED')
    require(task is not None and task.state == 3 and task.last_result == 0x41303,
        'SCHEDULER_NEVER_RAN_NOT_CONFIRMED')
    require(control.get('desired') == 'running' and not control.get('launch_requested')
        and not control.get('generation'), 'START_CONTROL_NOT_PRISTINE')
    require(canonical_absence(context, component) == absence
        and sha(receipt_path) == receipt_before and sha(control_path) == control_before, 'OWNER_OR_CONTROL_CHANGED')
    return {'canonical_absence': absence, 'task_name': expected['name'], 'instance_id': expected['instance_id'],
        'task_state': task.state, 'task_digest': task.digest, 'scheduler_last_result': task.last_result,
        'installation_receipt_sha256': receipt_before, 'control_sha256': control_before,
        'desired': control['desired'], 'launch_requested': False, 'generation': None}


def validate_never_started(context, proof, *, allow_current_uninstall=False):
    require_tags(proof, context)
    component = proof.get('component')
    require(proof.get('kind') == 'NEVER_STARTED_OWNER_ABSENT' and component in ('nexus', 'connector')
        and proof.get('owned_pid_birth_exit_confirmed') is False, 'ABSENCE_PROOF_KIND_INVALID')
    current = never_started_inputs(context, component, allow_current_uninstall=allow_current_uninstall)
    previous = proof['base_evidence']
    require(current['install_action_sha256'] == previous['install_action_sha256']
        and current['install_result_sha256'] == previous['install_result_sha256'], 'INSTALL_EVIDENCE_CHANGED')
    for name, entry in previous['invocations'].items():
        require(current['invocations'].get(name) == entry, 'BASE_INVOCATION_CHANGED')
    extra = set(current['invocations']) - set(previous['invocations'])
    require(not extra or (allow_current_uninstall and extra == {f'lifecycle-{component}-uninstall.reserved.json'}),
        'INVOCATIONS_CHANGED_AFTER_ABSENCE_PROOF')
    require(live_never_started(context, component) == proof['live_evidence'], 'LIVE_ABSENCE_PROOF_CHANGED')
    return True


def main():
    p = parser()
    p.add_argument('component', choices=('nexus', 'connector'))
    p.add_argument('--never-started', action='store_true')
    args = p.parse_args()
    context = gate(args)
    component = args.component
    if args.never_started:
        base = never_started_inputs(context, component)
        live = live_never_started(context, component)
        result = {'kind': 'NEVER_STARTED_OWNER_ABSENT', 'component': component,
            'task_name': live['task_name'], 'instance_id': live['instance_id'],
            'owned_pid_birth_exit_confirmed': False, 'never_started_owner_absence_confirmed': True,
            'task_stopped_confirmed': True, 'force_used': False,
            'base_evidence': base, 'live_evidence': live, 'observed_at': time.time()}
        public_save(context, 'cleanup-' + component + '.json', result)
        print(json.dumps({'kind': result['kind'], 'component': component, 'task_name': result['task_name']}))
        return 0
    selected = read_json(context.ROOT / 'public' / (component + '-owner-selection.json'))
    proof = read_json(context.ROOT / 'public' / (component + '-exit-proof.json'))
    require_tags(selected, context)
    require_tags(proof, context)
    drain_path = Path(context.P['paths']['server_home']) / 'service-shutdown.json' if component == 'nexus' else Path(context.P['paths']['connector_state']) / 'run/shutdown.json'
    before = sha(drain_path)
    drain = read_json(drain_path)
    from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks
    task = WindowsTasks().read(context.C['tasks'][component]['name'])
    validate_exit(selected, proof, drain, task, context.C['tasks'][component])
    require(sha(drain_path) == before, 'DRAIN_CHANGED_DURING_OBSERVATION')
    result = {'kind': 'PHYSICAL_OWNER_EXIT', 'component': component, 'task_name': selected['task']['name'], 'owned_pid_birth_exit_confirmed': True,
        'task_stopped_confirmed': True, 'force_used': False, 'task_state': task.state,
        'task_digest': task.digest, 'drain_sha256': before, 'drain_state': 'DRAINED',
        'generation': proof['generation'], 'instance_id': proof['instance_id'],
        'pid': proof['pid'], 'birth_filetime': proof['birth_filetime'], 'observed_at': time.time()}
    public_save(context, 'cleanup-' + component + '.json', result)
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main_guard(main))
