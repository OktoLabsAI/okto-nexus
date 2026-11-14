"""Root-run snapshot/observe/close for configured v12 setup and no Connector selection."""
from pathlib import Path
from datetime import datetime, timezone
import json
import socket
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
import supplement_common as s

PRESENCE = 'final-presence-reconciled.json'
STATUS = 'RECONCILED_CONFIGURED_LOCAL_SETUP_ONLY_CLEANUP_CONFIRMED'
HISTORY = {'lifecycle-initialize', 'lifecycle-nexus-install', 'lifecycle-nexus-start',
           'lifecycle-nexus-uninstall', 'plan-local_plan', 'setup-local'}
PUBLIC_ALLOWED = {'authorization-reference.json', 'root-driver-preparation.json', 'live-accounting.json',
    'local-setup-dispatch.json', 'local-setup-result.json', 'nexus-owner-selection.json',
    'nexus-exit-watch-started.json', 'nexus-exit-proof.json', 'cleanup-nexus.json',
    *('lifecycle-nexus-' + action + suffix for action in ('install', 'start', 'stop', 'uninstall')
      for suffix in ('.json', '-result.json')),
    *('process-nexus-' + action + '.json' for action in ('install', 'start', 'stop', 'uninstall'))}


def local_inputs(context, deps, output):
    summary = s.checkpoint_summary(context, deps)
    for key in ('server_home', 'connector_state', 'private_evidence', 'public_evidence'):
        root = deps.common.owned_path(context.P['paths'][key], context.ROOT)
        s.require(root.is_dir(), 'CAMPAIGN_DIRECTORIES_NOT_RETAINED')
    profile = deps.common.owned_path(Path(context.P['paths']['server_home']) /
        'terminal/profiles/m1v12-local.json', context.ROOT)
    s.require(profile.is_file(), 'CONFIGURED_PROFILE_NOT_RETAINED')
    ledger = s.DRIVERS / 'runtime-private'
    inventory = deps.common.invocation_inventory(context, ledger)
    s.require(set(inventory) == {n + '.reserved.json' for n in HISTORY}, 'EXACT_LOCAL_HISTORY_REQUIRED')
    s.require({p.name for p in ledger.iterdir() if p.name.endswith(('.reserved.json', '.returned.json'))}
        == {n + suffix for n in HISTORY for suffix in ('.reserved.json', '.returned.json')}, 'EXACT_LOCAL_HISTORY_REQUIRED')
    s.require(all(v.get('returned_sha256') and type(v.get('returncode')) is int for v in inventory.values()), 'WRAPPER_EXIT_REQUIRED')
    for name, value in inventory.items():
        if name != 'lifecycle-nexus-start.reserved.json':
            s.require(value['returncode'] == 0, 'LOCAL_WRAPPER_RESULT_CHANGED')
    public = context.ROOT / 'public'
    names = {p.name for p in public.iterdir()} - {PRESENCE, 'closure.json'}
    s.require(names == PUBLIC_ALLOWED, 'LOCAL_PUBLIC_SET_CHANGED')
    private_allowed = {'controller.json', 'controller.json.lock',
        *(name + suffix for name in ('local-setup', 'nexus-install', 'nexus-start', 'nexus-stop-wrapper',
          'nexus-stop', 'nexus-uninstall') for suffix in ('.stdout', '.stderr'))}
    s.require({p.name for p in (context.ROOT / 'private').iterdir()} <= private_allowed, 'NONLOCAL_PRIVATE_ARTIFACT')
    for key in ('operator_home', 'connector_state'):
        root = deps.common.owned_path(context.P['paths'][key], context.ROOT)
        s.require(root.is_dir() and not any(root.iterdir()), 'REMOTE_STATE_NOT_PRISTINE')
    result = s.read(public / 'local-setup-result.json')
    s.require(result.get('cli_exit') == 0 and result.get('reported_state') == 'configured', 'CONFIGURED_SETUP_REQUIRED')
    dispatched = s.read(public / 'local-setup-dispatch.json')
    s.require(dispatched.get('request_id') == 'm1v12-local-setup' and dispatched.get('reservation_persisted') is True,
              'LOCAL_SETUP_DISPATCH_REQUIRED')
    selected, returned = s.read(output / 'normal-stop.reserved.json'), s.read(output / 'normal-stop.returned.json')
    deps.common.require_tags(selected, context); deps.common.require_tags(returned, context)
    expected_argv = next(v['argv'] for v in context.C['steps'] if v['component'] == 'nexus' and v['action'] == 'stop')
    s.require(selected.get('selection') == 'SUPPLEMENTAL_NORMAL_STOP_ONCE' and selected.get('argv') == expected_argv
        and selected.get('old_stop_output_sha256') == s.OLD_STOP_SHA and selected.get('control_sha256') == s.CONTROL_SHA
        and selected.get('pid') == s.PID and selected.get('birth_filetime') == s.BIRTH
        and selected.get('generation') == s.GENERATION and selected.get('task_digest') == s.TASK_DIGEST
        and selected.get('force_used') is False, 'SUPPLEMENTAL_STOP_SCOPE_CHANGED')
    s.require(returned.get('reservation_sha256') == s.sha(output / 'normal-stop.reserved.json')
        and returned.get('returncode') == 0 and returned.get('wrapper_exit_confirmed') is True
        and returned.get('force_used') is False and returned['reported'].get('state') == 'stopped'
        and returned['reported'].get('shutdown_outcome') == 'drained', 'SUPPLEMENTAL_NORMAL_STOP_UNCONFIRMED')
    paths = [*(public / n for n in sorted(names)), context.ROOT / 'private/controller.json', profile,
        *(ledger / (n + suffix) for n in sorted(HISTORY) for suffix in ('.reserved.json', '.returned.json')),
        *(output / ('normal-stop.' + suffix + '.json') for suffix in ('reserved', 'process', 'returned'))]
    return {'summary': summary, 'invocations': inventory, 'files': {str(p): s.sha(p) for p in paths},
            'controller_checkpoint_sha256': s.CHECKPOINT_SHA,
            'configured_profile_sha256': s.sha(profile),
            'profile_validation_scope': 'File existence and hash only; cleanup does not requalify profile contents.'}


def observe(context, deps, output, reference, *, task_reader, absence, port_probe):
    before = local_inputs(context, deps, output)
    s.require(before == reference['inputs'], 'PROOF_SNAPSHOT_CHANGED')
    nexus = deps.presence.check_component(context, 'nexus', task_reader=task_reader,
        inventory=before['invocations'], absence=absence)
    s.require(nexus['owner_cleanup_evidence'], 'NEXUS_PHYSICAL_CLEANUP_REQUIRED')
    name = context.C['tasks']['connector']['name']
    s.require(task_reader(name) is None, 'CONNECTOR_TASK_PRESENT')
    connector = {'name': name, 'absent': True, 'owner_cleanup_evidence': {},
        'canonical_absence': absence(context, 'connector'),
        'basis': 'CONFIGURED_LOCAL_SETUP_ONLY_NO_CONNECTOR_SELECTION'}
    helper = deps.presence.remote_helpers(context, before['invocations'])
    s.require(helper['selected'] is False, 'REMOTE_HELPER_SELECTED')
    port = port_probe(context, deps)
    s.require(local_inputs(context, deps, output) == before, 'INPUTS_CHANGED_DURING_OBSERVATION')
    return {'status': STATUS, 'tasks': {'nexus': nexus, 'connector': connector}, 'inputs': before,
        'remote_helper_evidence': helper, 'exclusive_port_probe_passed_not_reserved': port,
        'observed_at': time.time(), 'data_directories_retained': True, 'force_used': False,
        'controller_mutated': False, 'database_read': False, 'acceptance_promoted': False,
        'original_final_presence_passed': False,
        'original_branch_applicability': 'INAPPLICABLE_REQUIRES_NONZERO_SETUP_CLI_EXIT',
        'scope': 'Configured setup is retained; DEADLINE120 remains. Cleanup is not useful work, permission-cycle acceptance or final billing.'}


def port_probe(context, deps):
    host, port = deps.observation.endpoint(context)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind((host, port))
    return port


def close(context, deps, output, reference, proof_sha, manifest_sha):
    path = context.ROOT / 'public' / PRESENCE
    value = s.read(path)
    deps.common.require_tags(value, context)
    s.require(value.get('status') == STATUS and value.get('proof_snapshot_sha256') == proof_sha
        and value.get('supplement_manifest_sha256') == manifest_sha and value.get('force_used') is False
        and value.get('original_final_presence_passed') is False, 'RECONCILED_PRESENCE_REQUIRED')
    current = local_inputs(context, deps, output)
    s.require(current == reference['inputs'] == value['inputs'], 'INPUTS_CHANGED_BEFORE_CLOSE')
    s.require(set(value['tasks']) == {'nexus', 'connector'} and all(v.get('absent') is True for v in value['tasks'].values()),
              'TASK_ABSENCE_REQUIRED')
    for component, task in value['tasks'].items():
        deps.observation.validate_canonical_absence(context, component, task['canonical_absence'])
    return {'format': 'okto.m1.closed_campaign', 'revision': 1,
        'status': 'CLOSED_RECONCILED_CLEANUP_ACCEPTANCE_NOT_INFERRED', 'closed_at': datetime.now(timezone.utc).isoformat(),
        **current['summary'], 'controller_checkpoint_sha256': s.CHECKPOINT_SHA, 'controller_mutated': False,
        'database_read': False, 'final_presence_sha256': s.sha(path), 'final_presence_file': PRESENCE,
        'closed_without_force': True, 'replay_allowed': False, 'all_temporary_tasks_absent': True,
        'data_retained': True, 'acceptance_promoted': False, 'configured_setup_retained': True,
        'original_final_presence_passed': False, 'limits': 'DEADLINE120 and original failed stop retained. No useful-work acceptance or final billing inferred.'}


def main():
    p = s.parser()
    p.add_argument('operation', choices=('snapshot', 'observe', 'close'))
    p.add_argument('--proof-snapshot-sha256')
    args = p.parse_args()
    context, deps = s.load(args)
    output = s.HERE / 'runtime-private'
    reference_path = output / 'proof-snapshot.json'
    if args.operation == 'snapshot':
        # Root invokes only after real physical cleanup/uninstall evidence exists.
        # All hashes are computed now; no placeholders or guessed future receipts.
        reference = {**deps.common.tags(context), 'inputs': local_inputs(context, deps, output),
            'supplement_manifest_sha256': args.manifest_sha256, 'captured_at': time.time()}
        deps.common.reserve(reference_path, reference)
        print(json.dumps({'status': 'ACTUAL_CLEANUP_INPUTS_SNAPSHOTTED', 'proof_snapshot_sha256': s.sha(reference_path)}))
        return 0
    s.require(args.proof_snapshot_sha256 and s.sha(reference_path) == args.proof_snapshot_sha256, 'EXACT_PROOF_SNAPSHOT_REQUIRED')
    reference = s.read(reference_path)
    deps.common.require_tags(reference, context)
    s.require(reference.get('supplement_manifest_sha256') == args.manifest_sha256, 'SNAPSHOT_MANIFEST_CHANGED')
    if args.operation == 'observe':
        from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks
        value = observe(context, deps, output, reference, task_reader=WindowsTasks().read,
                        absence=deps.observation.canonical_absence, port_probe=port_probe)
        name = PRESENCE
    else:
        value = close(context, deps, output, reference, args.proof_snapshot_sha256, args.manifest_sha256)
        name = 'closure.json'
    value.update(proof_snapshot_sha256=args.proof_snapshot_sha256, supplement_manifest_sha256=args.manifest_sha256)
    path = deps.common.public_save(context, name, value)
    print(json.dumps({'status': value['status'], 'evidence_sha256': s.sha(path)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(s.safe_main(main))
