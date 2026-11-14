"""One-campaign supplemental reconciliation. Never repairs frozen evidence.

Import is inert. observe reads existing evidence plus task/owner/port state;
close projects the sealed checkpoint only. Both exclusively append evidence.
"""
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
import argparse
import hashlib
import importlib
import importlib.util
import json
import socket
import sys
import time

PROPOSAL_SHA = 'dd04c4c0507022c021b99c540c4d4c307232ceb0a4b9661d38bd6eeaf335b812'
APPROVAL_SHA = 'ee0d6f0dd13a1439499bf79e344451a603b11606e84ce7c5212c83de07931f8f'
DRIVER_ROOT = Path('C:/Users/jpamb/AppData/Local/Temp/m1-v11-operator-candidate-sqp53mdk')
HISTORY = {
    'lifecycle-initialize': ('lifecycle', ['initialize'], 0),
    'lifecycle-nexus-install': ('lifecycle', ['nexus', 'install'], 0),
    'lifecycle-nexus-start': ('lifecycle', ['nexus', 'start'], 3),
    'lifecycle-nexus-uninstall': ('lifecycle', ['nexus', 'uninstall'], 0),
    'plan-local_plan': ('plan', ['local_plan'], 0),
    'setup-local': ('setup', ['local'], 0),
}
PRESENCE = 'final-presence-reconciled.json'
STATUS = 'RECONCILED_LOCAL_ONLY_CONNECTOR_UNSELECTED_CLEANUP_CONFIRMED'
PUBLIC_NAMES = {
    'authorization-reference.json', 'cleanup-nexus.json', 'final-presence-original-refusal.json',
    'live-accounting.json', 'local-setup-dispatch.json', 'local-setup-result.json',
    'nexus-exit-proof.json', 'nexus-exit-watch-started.json', 'nexus-owner-selection.json',
    'root-driver-preparation.json',
    *('lifecycle-nexus-' + action + suffix for action in ('install', 'start', 'stop', 'uninstall')
      for suffix in ('.json', '-result.json')),
    *('process-nexus-' + action + '.json' for action in ('install', 'start', 'stop', 'uninstall')),
}
PRIVATE_NAMES = {'controller.json', 'controller.json.lock',
                 *(name + suffix for name in ('local-setup', 'nexus-install', 'nexus-start',
                   'nexus-stop-wrapper', 'nexus-stop', 'nexus-uninstall') for suffix in ('.stdout', '.stderr'))}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def check(value, code):
    if not value:
        raise ValueError(code)


def load_dependencies(args):
    check(args.expected_proposal_sha256 == PROPOSAL_SHA and digest(args.proposal) == PROPOSAL_SHA,
          'ONE_CAMPAIGN_PROPOSAL_REQUIRED')
    check(args.approval_sha256 == APPROVAL_SHA and digest(args.approval_path) == APPROVAL_SHA,
          'ORIGINAL_APPROVAL_REQUIRED')
    proposal = read(args.proposal)
    files = proposal['execution_bundle']['files']
    # Verify before importing; no replacement or monkeypatch of frozen modules.
    for key, entry in files.items():
        if key.startswith('root_driver_'):
            check(Path(entry['path']).parent == DRIVER_ROOT and digest(entry['path']) == entry['sha256'],
                  'FROZEN_DRIVER_CHANGED')
    check(digest(files['controller_token_collector']['path']) == files['controller_token_collector']['sha256'],
          'COLLECTOR_CHANGED')
    sys.path.insert(0, str(DRIVER_ROOT))
    common = importlib.import_module('driver_common')
    context = common.gate(args)
    final = importlib.import_module('confirm_final_presence')
    close = importlib.import_module('close_campaign')
    observation = importlib.import_module('m1_v11_observation')
    spec = importlib.util.spec_from_file_location('reconciliation_collector', files['controller_token_collector']['path'])
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    return context, SimpleNamespace(common=common, final=final, close=close,
                                    observation=observation, collector=collector)


def snapshot(context, reference, deps, ledger):
    """Pin all retained evidence and the exact complete finished local history."""
    c = deps.common
    check(reference['proposal_sha256'] == context.args.expected_proposal_sha256
          and reference['approval_sha256'] == context.args.approval_sha256, 'REFERENCE_SCOPE_CHANGED')
    pins = reference['retained_files']
    for raw, expected in pins.items():
        path = Path(raw)
        c.owned_path(path, context.ROOT if path.is_relative_to(context.ROOT) else ledger)
        check(digest(path) == expected, 'RETAINED_EVIDENCE_CHANGED')
    actual_public = {p.name for p in (context.ROOT / 'public').iterdir()}
    check(set(reference['public_names']) == PUBLIC_NAMES and set(reference['private_names']) == PRIVATE_NAMES,
          'REFERENCE_LOCAL_SCOPE_INVALID')
    check(actual_public - {PRESENCE, 'closure.json'} == set(reference['public_names']), 'PUBLIC_EVIDENCE_SET_CHANGED')
    check({p.name for p in (context.ROOT / 'private').iterdir()} == set(reference['private_names']),
          'PRIVATE_EVIDENCE_SET_CHANGED')
    expected_names = {name + suffix for name in HISTORY for suffix in ('.reserved.json', '.returned.json')}
    required_pins = {str(context.ROOT / 'public' / name) for name in PUBLIC_NAMES}
    required_pins |= {str(context.ROOT / 'private/controller.json')}
    required_pins |= {str(ledger / name) for name in expected_names}
    check(set(pins) == required_pins, 'REFERENCE_PIN_SET_INVALID')
    actual_names = {p.name for p in ledger.iterdir() if p.name.endswith(('.reserved.json', '.returned.json'))}
    check(actual_names == expected_names, 'EXACT_LOCAL_HISTORY_REQUIRED')
    inventory = c.invocation_inventory(context, ledger)
    check(set(inventory) == {name + '.reserved.json' for name in HISTORY}, 'EXACT_LOCAL_HISTORY_REQUIRED')
    for name, (mode, selection, code) in HISTORY.items():
        item = inventory[name + '.reserved.json']
        check(item['mode'] == mode and item['selection'] == selection and item.get('returncode') == code
              and item['returned_sha256'], 'EXACT_RETURNED_HISTORY_REQUIRED')
    # Empty native Connector/operator roots are additional positive evidence.
    for key in ('connector_state', 'operator_home'):
        path = c.owned_path(context.P['paths'][key], context.ROOT)
        check(path.is_dir() and not any(path.iterdir()), 'REMOTE_STATE_NOT_PRISTINE')
    checkpoint_path = context.ROOT / 'private/controller.json'
    checkpoint = read(checkpoint_path)
    collector_state = deps.collector.restore(checkpoint['collector'])
    summary = deps.close.checkpoint_summary(context, checkpoint, deps.collector.summary(collector_state))
    home = context.P['paths']['server_home']
    check(checkpoint['owners'] == {'local': home}, 'NONLOCAL_CONTROLLER_OWNER')
    check(set(checkpoint['requests']) == {'m1v11-local-setup'}, 'NONLOCAL_REQUEST_RESERVATION')
    request = checkpoint['requests']['m1v11-local-setup']
    check(request['kind'] == 'setup' and request['lane'] == 'local' and request['monitor']['home'] == home,
          'NONLOCAL_REQUEST_SCOPE')
    check(not checkpoint['collector']['state']['requests'] and not checkpoint['collector']['state']['streams']
          and not checkpoint['collector']['state']['threads'] and not checkpoint['collector']['state']['turns'],
          'WORK_ACCOUNTING_PRESENT')
    result = read(context.ROOT / 'public/local-setup-result.json')
    check(result.get('cli_exit') == 3 and result.get('reported_state') == 'unconfirmed'
          and result.get('reported_code') == 'INSTALLATION_UNCONFIRMED', 'ORIGINAL_SETUP_FAILURE_CHANGED')
    check(summary['faults_preserved'] == ['OBSERVATION_UNKNOWN', 'DEADLINE120']
          and summary['new_reserved_admissions'] == 1 and summary['cumulative_reserved_admissions'] == 7
          and summary['new_observed_tokens'] == 0 and summary['cumulative_minimum_observed_tokens'] == 89473
          and summary['unsettled_requests'] == 1, 'ORIGINAL_UNCERTAINTY_CHANGED')
    return {'invocation_evidence': inventory, 'controller_checkpoint_sha256': digest(checkpoint_path),
            'summary': summary, 'setup_result_sha256': digest(context.ROOT / 'public/local-setup-result.json'),
            'retained_files': pins}


def exclusive_port(context, deps):
    host, port = deps.observation.endpoint(context)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind((host, port))
    return port


def observe(context, reference, deps, ledger, *, task_reader, absence, port_probe):
    before = snapshot(context, reference, deps, ledger)
    inventory = before['invocation_evidence']
    nexus = deps.final.check_component(context, 'nexus', task_reader=task_reader, inventory=inventory, absence=absence)
    # Original Nexus branch still requires selected physical exit + pinned uninstall.
    check(nexus['owner_cleanup_evidence'], 'NEXUS_PHYSICAL_CLEANUP_REQUIRED')
    expected = context.C['tasks']['connector']
    check(task_reader(expected['name']) is None, 'CONNECTOR_TASK_STILL_PRESENT')
    connector_absence = absence(context, 'connector')
    connector = {'name': expected['name'], 'absent': True, 'canonical_absence': connector_absence,
                 'owner_cleanup_evidence': {}, 'basis': 'EXACT_RETURNED_LOCAL_ONLY_HISTORY_AND_PRISTINE_CONNECTOR_ROOT'}
    helper = deps.final.remote_helpers(context, inventory)
    check(helper.get('selected') is False, 'REMOTE_HELPER_WAS_SELECTED')
    port = port_probe(context, deps)
    check(snapshot(context, reference, deps, ledger) == before, 'EVIDENCE_CHANGED_DURING_OBSERVATION')
    retained = all(Path(context.P['paths'][k]).is_dir() for k in
                   ('server_home', 'connector_state', 'private_evidence', 'public_evidence'))
    check(retained, 'CAMPAIGN_DIRECTORIES_NOT_RETAINED')
    return {'status': STATUS, 'tasks': {'nexus': nexus, 'connector': connector}, **before,
            'remote_helper_evidence': helper, 'exclusive_port_probe_passed_not_reserved': port,
            'data_directories_retained': True, 'force_used': False, 'database_read': False,
            'controller_mutated': False, 'observed_at': time.time(),
            'original_helper_passed': False, 'original_refusal_code': 'POSSIBLE_UNSELECTED_START',
            'original_refusal_evidence': reference['original_refusal_evidence'],
            'acceptance_promoted': False, 'setup_still_unconfirmed': True,
            'scope': 'Supplemental one-campaign local-only reconciliation; instantaneous absence and port availability. No work success or final billing inferred.'}


def closure(context, reference, deps, ledger, *, helper_sha, reference_sha):
    final_path = context.ROOT / 'public' / PRESENCE
    final = read(final_path)
    deps.common.require_tags(final, context)
    check(final.get('status') == STATUS and final.get('helper_sha256') == helper_sha
          and final.get('reference_sha256') == reference_sha and final.get('force_used') is False
          and final.get('original_helper_passed') is False and final.get('data_directories_retained') is True,
          'SUPPLEMENTAL_PRESENCE_REQUIRED')
    check(set(final['tasks']) == {'nexus', 'connector'} and all(
        value.get('absent') is True and value['canonical_absence']['state'] == 'stopped'
        and value['canonical_absence']['reason'] == 'NO_SERVICE_OWNER' for value in final['tasks'].values()),
        'FINAL_ABSENCE_REQUIRED')
    current = snapshot(context, reference, deps, ledger)
    check(all(final.get(k) == v for k, v in current.items()), 'EVIDENCE_CHANGED_AFTER_OBSERVATION')
    return {'format': 'okto.m1.closed_campaign', 'revision': 1,
            'status': 'CLOSED_RECONCILED_CLEANUP_ACCEPTANCE_NOT_INFERRED',
            'closed_at': datetime.now(timezone.utc).isoformat(), **current['summary'],
            'controller_checkpoint_sha256': current['controller_checkpoint_sha256'],
            'controller_mutated': False, 'database_read': False, 'final_presence_sha256': digest(final_path),
            'final_presence_file': PRESENCE, 'wrapper_exit_evidence': current['invocation_evidence'],
            'closed_without_force': True, 'replay_allowed': False, 'all_temporary_tasks_absent': True,
            'data_retained': True, 'acceptance_promoted': False, 'setup_still_unconfirmed': True,
            'original_helper_passed': False, 'original_refusal_code': 'POSSIBLE_UNSELECTED_START',
            'limits': 'Neutral supplemental closure only. Faults and unsettled setup persist; zero new observed tokens does not prove zero provider use or final billing.'}


def main():
    p = argparse.ArgumentParser()
    for name in ('proposal', 'expected-proposal-sha256', 'approval-path', 'approval-sha256',
                 'reference', 'reference-sha256', 'expected-helper-sha256'):
        p.add_argument('--' + name, required=True)
    p.add_argument('operation', choices=('observe', 'close'))
    args = p.parse_args()
    helper_sha = digest(__file__)
    check(helper_sha == args.expected_helper_sha256 and digest(args.reference) == args.reference_sha256,
          'SUPPLEMENTAL_PIN_CHANGED')
    reference = read(args.reference)
    original = reference['original_refusal_evidence']
    check(digest(original['path']) == original['sha256'], 'ORIGINAL_REFUSAL_EVIDENCE_CHANGED')
    context, deps = load_dependencies(args)
    ledger = DRIVER_ROOT / 'runtime-private'
    if args.operation == 'observe':
        from okto_nexus.adapters.outbound.service_manager.windows_tasks import WindowsTasks
        result = observe(context, reference, deps, ledger, task_reader=WindowsTasks().read,
                         absence=deps.observation.canonical_absence, port_probe=exclusive_port)
        name = PRESENCE
    else:
        result = closure(context, reference, deps, ledger, helper_sha=helper_sha, reference_sha=args.reference_sha256)
        name = 'closure.json'  # distinct status; preserves original gate's no-replay sentinel.
    result.update(helper_sha256=helper_sha, reference_sha256=args.reference_sha256)
    path = deps.common.public_save(context, name, result)
    print(json.dumps({'status': result['status'], 'evidence_sha256': digest(path), 'path': str(path)}))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status': 'RECONCILIATION_REFUSED', 'code': str(error) if isinstance(error, ValueError) else type(error).__name__}))
        raise SystemExit(2)
