"""Future root selection only: requires real completed receipts and idle accounting.

No service, HTTP, model or credential access. Does not create a DONE receipt.
"""
from pathlib import Path
import argparse
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from next_connect import RECOVERY, RecoveryContext, require, read_json, sha, pin, reserve, validate_completed, accounting


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--completed-sha256', required=True)
    parser.add_argument('--rotation-sha256', required=True)
    parser.add_argument('--zero-admissions-only', action='store_true', required=True)
    args = parser.parse_args()
    lifecycle = RECOVERY / 'lifecycle-plan.json'
    base = RecoveryContext(lifecycle, '8980570ab636b7836ffa34a5976652c0cc19825af015c50d50a9c5b08bcf6a27')
    completed = {'path': str(RECOVERY / 'public/recovery02-profile-completed.json'), 'sha256': args.completed_sha256}
    rotation = {'path': str(RECOVERY / 'public/rotation-import-result.json'), 'sha256': args.rotation_sha256}
    done = read_json(pin(completed))
    imported = read_json(pin(rotation))
    profile_path = Path(base.P['paths']['operator_home']) / 'terminal/profiles/m1-sonnet-remote-recovery02.json'
    require(sha(profile_path) == done['profile_sha256'], 'DONE_PROFILE_CHANGED')
    profile = read_json(profile_path)
    plan = {'status': 'ROOT_SELECTED_AFTER_REAL_DONE_AND_ZERO_ADMISSIONS',
            'profile': 'm1-sonnet-remote-recovery02', 'agent_id': 'm1-sonnet-remote',
            'server_id': 'srv_a3f134b449dbffa20c126dae6f9a8aa9',
            'workspace_id': 'ws_1b0930e4c25dddad2ad1d11d903d6a52', 'origin': 'http://127.0.0.1:58631',
            'paths': base.P['paths'], 'completed': completed, 'rotation': rotation,
            'lifecycle_plan': {'path': str(lifecycle), 'sha256': base.plan_sha256},
            'settlement_gate': 'ZERO_EXECUTION_OPERATIONS_ONLY',
            'post_paid_branch': 'HELD_NO_SETTLEMENT_COMPANION',
            'prospective_order': ['actual recovery02 DONE', 'prove zero execution operations',
                'SVC20 stop/configured next-connect/final normal stop',
                'separate canonical start and fresh cohort watchers',
                'compose paid Context against the fresh cohort before first inference'],
            'paid_context_reuse_after_svc20': False,
            'pins': {name: {'path': str(HERE / name), 'sha256': sha(HERE / name)}
                     for name in ('next_connect.py', 'select_after_done.py')},
            'scope': 'One canonical Connector stop, one configured connect without productive start, final normal stop. Nexus remains same ready cohort. No install/uninstall or paid request.',
            'existing_quiet_evidence': {'path': 'C:/Users/jpamb/AppData/Local/Temp/r3-native-t19-t20-v2-fk9g74yv/public/qualification.json'},
            'no_productive_start': True, 'no_force': True, 'provider_calls_selected': 0}
    validate_completed(plan, done, profile, imported)
    require(done['rotation_import_result_pin']['sha256'] == rotation['sha256'], 'DONE_ROTATION_CHAIN_CHANGED')
    plan['selection_accounting'] = accounting(Path(plan['paths']['server_home']) / 'nexus.db', plan)
    quiet = plan['existing_quiet_evidence']
    quiet['sha256'] = sha(quiet['path'])
    reserve(HERE / 'selected-plan.json', plan)
    print(json.dumps({'selected_plan_sha256': sha(HERE / 'selected-plan.json'),
                      'effects': 0, 'service_execution_selected_separately': True}))


if __name__ == '__main__':
    main()
