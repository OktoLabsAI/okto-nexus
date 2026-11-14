"""Read-only checkpoint projection and neutral closure; never creates a controller."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from driver_common import HERE, gate, invocation_inventory, main_guard, parser, public_save, read_json, require, require_tags, sha


def checkpoint_summary(context, checkpoint, work_summary):
    unsealed = {k: v for k, v in checkpoint.items() if k != 'state_sha256'}
    seal = hashlib.sha256(json.dumps(unsealed, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    contract = context.P['controller_preparation']
    require(checkpoint.get('state_sha256') == seal and checkpoint.get('format') == 11
        and checkpoint.get('root') == str(context.ROOT)
        and checkpoint.get('proposal_sha256') == context.args.expected_proposal_sha256
        and checkpoint.get('authorization_sha256') == context.args.approval_sha256
        and checkpoint.get('policy') == contract['policy'] and checkpoint.get('ancestry') == contract['ancestry'],
        'CHECKPOINT_SCOPE_OR_SEAL_INVALID')
    requests, policy = checkpoint['requests'], contract['policy']
    require(isinstance(requests, dict) and len(requests) <= policy['max_new_admissions'], 'RESERVATION_LIMIT_INVALID')
    setup = 0
    for request in requests.values():
        require(request.get('kind') in ('setup', 'work'), 'REQUEST_KIND_INVALID')
        if request['kind'] == 'setup':
            count = request['monitor']['high_water']
            require(type(count) is int and count >= 0, 'SETUP_ACCOUNTING_INVALID')
            setup += count
    work = work_summary['known_observed_tokens']
    require(type(work) is int and work >= 0, 'WORK_ACCOUNTING_INVALID')
    faults = checkpoint['faults']
    require(isinstance(faults, list) and all(isinstance(v, str) and re.fullmatch('[A-Z0-9_]{1,128}', v) for v in faults), 'FAULT_PROJECTION_INVALID')
    return {'faults_preserved': list(faults), 'new_reserved_admissions': len(requests),
        'cumulative_reserved_admissions': policy['carry_in_admissions'] + len(requests),
        'prior_carry_in_tokens': policy['carry_in_tokens'], 'new_observed_tokens': setup + work,
        'cumulative_minimum_observed_tokens': policy['carry_in_tokens'] + setup + work,
        'billing_final': False, 'unsettled_requests': sum(not r.get('settled') for r in requests.values())}


def verify_wrappers(context, directory):
    proofs = {}
    for path in directory.glob('*.reserved.json'):
        reserved = read_json(path)
        require_tags(reserved, context)
        returned_path = path.with_name(path.name.replace('.reserved.json', '.returned.json'))
        returned = read_json(returned_path)
        require_tags(returned, context)
        require(returned.get('mode') == reserved.get('mode') and returned.get('selection') == reserved.get('selection')
            and returned.get('wrapper_exit_confirmed') is True, 'WRAPPER_EXIT_UNCONFIRMED')
        proofs[path.name] = {'reservation_sha256': sha(path), 'returned_sha256': sha(returned_path),
            'returncode': returned['returncode']}
    require(bool(proofs), 'NO_FINITE_INVOCATIONS')
    return proofs


def before_controller_summary(context, inventory, final):
    for value in inventory.values():
        selection = value['selection']
        safe = selection == ['initialize'] or (len(selection) == 2 and selection[0] in ('nexus', 'connector')
            and selection[1] in ('install', 'uninstall'))
        require(value['mode'] == 'lifecycle' and safe and value.get('returncode') == 0,
            'NO_CONTROLLER_EFFECT_SCOPE_UNCONFIRMED')
    require(all(v.get('canonical_absence', {}).get('state') == 'stopped'
        and v.get('canonical_absence', {}).get('reason') == 'NO_SERVICE_OWNER' for v in final['tasks'].values()),
        'NO_CONTROLLER_OWNER_ABSENCE_REQUIRED')
    public = context.ROOT / 'public'
    require(not any((public / name).exists() for name in ('lifecycle-nexus-start.json',
        'lifecycle-connector-start.json', 'remote-pty-reservation.json', 'remote-supervisor-checked.json')),
        'NO_CONTROLLER_START_EVIDENCE_PRESENT')
    policy = context.P['controller_preparation']['policy']
    return {'faults_preserved': [], 'new_reserved_admissions': 0,
        'cumulative_reserved_admissions': policy['carry_in_admissions'], 'prior_carry_in_tokens': policy['carry_in_tokens'],
        'new_observed_tokens': 0, 'cumulative_minimum_observed_tokens': policy['carry_in_tokens'],
        'billing_final': False, 'unsettled_requests': 0,
        'accounting_scope': 'No model-capable command selected; only completed initialize/install/uninstall and positive canonical absence. No controller created.'}


def main():
    context = gate(parser().parse_args())
    final_path = context.ROOT / 'public/final-presence.json'
    final = read_json(final_path)
    require_tags(final, context)
    require(final.get('status') == 'NORMAL_CLEANUP_CONFIRMED' and final.get('force_used') is False
        and final.get('data_directories_retained') is True
        and set(final['tasks']) == {'nexus', 'connector'}
        and all(v.get('absent') is True for v in final['tasks'].values()), 'FINAL_CLEANUP_REQUIRED')
    wrappers = verify_wrappers(context, HERE / 'runtime-private')
    inventory = invocation_inventory(context)
    checkpoint_path = context.ROOT / 'private/controller.json'
    before = None
    if checkpoint_path.exists():
        before = sha(checkpoint_path)
        checkpoint = read_json(checkpoint_path)
        entry = context.P['execution_bundle']['files']['controller_token_collector']
        require(sha(entry['path']) == entry['sha256'], 'COLLECTOR_CHANGED')
        spec = importlib.util.spec_from_file_location('closure_token_collector', entry['path'])
        collector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(collector)  # pure restore/summary only; no Controller import
        summary = checkpoint_summary(context, checkpoint, collector.summary(collector.restore(checkpoint['collector'])))
        require(sha(checkpoint_path) == before, 'CHECKPOINT_CHANGED_DURING_CLOSURE')
    else:
        summary = before_controller_summary(context, inventory, final)
        require(not checkpoint_path.exists(), 'CONTROLLER_APPEARED_DURING_CLOSURE')
    value = {'format': 'okto.m1.closed_campaign', 'revision': 1,
        'status': 'CLOSED_NORMAL_CLEANUP_ACCEPTANCE_NOT_INFERRED', 'closed_at': datetime.now(timezone.utc).isoformat(),
        **summary, 'controller_checkpoint_sha256': before, 'controller_mutated': False,
        'final_presence_sha256': sha(final_path), 'wrapper_exit_evidence': wrappers,
        'closed_without_force': True, 'replay_allowed': False, 'all_temporary_tasks_absent': True,
        'data_retained': True, 'acceptance_promoted': False,
        'first_useful_result': 'requires separate canonical evidence review',
        'limits': 'Closure is not M1 acceptance, a work result, effective provider configuration or final billing. Faults/uncertainty remain. No historical failure cause or fixed token count is copied.'}
    path = public_save(context, 'closure.json', value)
    print(json.dumps({'status': value['status'], 'closure_sha256': sha(path), 'checkpoint_sha256': before,
        'minimum_observed_tokens': summary['cumulative_minimum_observed_tokens'],
        'cumulative_reservations': summary['cumulative_reserved_admissions']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main_guard(main))
