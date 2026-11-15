"""Same authorized force selection; own retained cohort replaces expired observer."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
from recovery_context import RecoveryContext, require, read_json, sha, pin, reserve
import recovery_connector as connector
import recovery_observation as observed

ORIGINAL_SOURCE_SHA = '179da35eddf2bf32f3871e907828a05615a6ac64775975723875d8667e556950'
PROPOSAL_SHA = 'c35871e2af447c3532cb51dbc223bdb07a31807242c2abbe7187a88a7bea5a7e'


def preflight(base, proposal, handles, original):
    from okto_nexus_connector.daemon import manager
    selected = read_json(pin(proposal['pins']['selection']))
    base.require_tags(selected)
    require({k: selected[k] for k in ('pid', 'generation', 'instance_id')} == proposal['target']['owner']
            and selected['cohort'] == proposal['target']['cohort']
            and selected['task'] == proposal['target']['task'], 'EXACT_AUTHORIZED_TARGET_CHANGED')
    require(not (base.PUBLIC / 'connector-exit-proof.json').exists(), 'ORIGINAL_COHORT_ALREADY_EXITED')
    expired = read_json(base.PUBLIC / 'connector-exit-watch-timeout.json')
    base.require_tags(expired)
    require(expired.get('physical_exit_confirmed') is False
            and expired.get('cohort') == selected['cohort'], 'OLD_OBSERVER_TIMEOUT_REQUIRED')
    service = connector.installation(base)
    _, task = service.observe()
    require(task is not None and task.active and task.enabled
            and task.digest == selected['task']['digest'] and service.name == selected['task']['name'],
            'EXACT_ACTIVE_TASK_REQUIRED')
    observed.same_cycle(selected['cohort'], connector.cycle(base))
    for role in observed.ROLES:
        identity = selected['cohort'][role]
        if role not in handles:
            handles[role] = observed.Process(identity['pid'])
        handle = handles[role]
        require(handle.pid == identity['pid'] and handle.birth == identity['birth']
                and handle.image in base.installed['python_images']
                and sha(handle.image) == base.installed['python_images'][handle.image]
                and not handle.exited(), 'LIVE_EXACT_COHORT_REQUIRED')
    value = manager.status(Path(base.P['paths']['connector_state']), timeout=5).to_json()
    projection = original.validate_status(value, selected)
    observed.same_cycle(selected['cohort'], connector.cycle(base))
    require(not any(h.exited() for h in handles.values()), 'COHORT_CHANGED_BEFORE_FORCE')
    return selected, projection


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-source-sha256', required=True)
    parser.add_argument('--authorization-sha256', required=True)
    args = parser.parse_args()
    require(sha(__file__) == args.expected_source_sha256, 'RETAINED_FORCE_SOURCE_CHANGED')
    require(sha(HERE / 'force_once.py') == ORIGINAL_SOURCE_SHA, 'ORIGINAL_FORCE_SOURCE_CHANGED')
    import force_once as original
    require(sha(HERE / 'force-proposal.json') == PROPOSAL_SHA, 'ORIGINAL_FORCE_PROPOSAL_CHANGED')
    proposal = read_json(HERE / 'force-proposal.json')
    for item in proposal['pins'].values():
        pin(item)
    authorization = HERE / 'force-authorization.json'
    require(sha(authorization) == args.authorization_sha256, 'FORCE_AUTHORIZATION_CHANGED')
    original.validate_authorization(read_json(authorization), proposal, PROPOSAL_SHA)
    base = RecoveryContext(ROOT / 'lifecycle-plan.json', original.LIFECYCLE_SHA)
    require(proposal['argv'] == connector.stop_argv(base) + ['--force', '--expected-generation', proposal['target']['owner']['generation']],
            'ORIGINAL_CANONICAL_ARGV_CHANGED')
    public, private = HERE / 'public', HERE / 'private'
    for directory in (public, private):
        if not directory.exists():
            observed.secure_directory(directory, HERE)
    handles = {}
    own = None
    try:
        selected, before = preflight(base, proposal, handles, original)
        own = observed.Process(os.getpid())
        observer = {'pid': own.pid, 'birth': own.birth}
        reserve(public / 'canonical-force-reserved.json', {
            'status': 'SINGLE_CANONICAL_FORCE_RESERVED', 'proposal_sha256': PROPOSAL_SHA,
            'authorization_sha256': args.authorization_sha256, 'target': proposal['target'],
            'preflight': before, 'argv': proposal['argv'], 'force_authorized': True,
            'force_dispatched': False, 'provider_calls': 0,
            'retained_observer': observer, 'retained_roles': list(observed.ROLES),
            'observer_terminate_right': False, 'additive_source_sha256': args.expected_source_sha256,
            'expired_observer_timeout_sha256': sha(base.PUBLIC / 'connector-exit-watch-timeout.json')})
        preflight(base, proposal, handles, original)
        with (private / 'canonical-force.stdout').open('xb') as out, \
                (private / 'canonical-force.stderr').open('xb') as err:
            child = subprocess.Popen(proposal['argv'], cwd=base.ROOT, env=base.connector_env(),
                stdin=subprocess.DEVNULL, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
            code = child.wait()  # One canonical call; no OS kill, cancellation or replay.
        result = {'status': 'CANONICAL_FORCE_RETURNED', 'proposal_sha256': PROPOSAL_SHA,
                  'authorization_sha256': args.authorization_sha256, 'returncode': code,
                  'force_used': True, 'canonical_force_calls': 1, 'os_termination_calls': 0,
                  'provider_calls': 0, 'stdout_sha256': sha(private / 'canonical-force.stdout'),
                  'stderr_sha256': sha(private / 'canonical-force.stderr'),
                  'observer': observer, 'physical_exit_confirmed': False,
                  'work_settlement_claimed': False, 'old_observer_timeout_preserved': True}
        try:
            raw = read_json(private / 'canonical-force.stdout')
            data = raw.get('data', raw)
            result['projection'] = {k: data.get(k) for k in ('state', 'reason', 'code', 'pid', 'generation', 'instance_id', 'shutdown_outcome', 'stopped') if k in data}
        except (ValueError, TypeError, AttributeError):
            result['parse_error'] = 'CANONICAL_RESULT_UNCONFIRMED'
        reserve(public / 'canonical-force-returned.json', result)
        print(json.dumps(result), flush=True)
        deadline = time.monotonic() + 3600
        while time.monotonic() < deadline:
            if all(h.exited() for h in handles.values()):
                proof = {'cohort': selected['cohort'], 'observed_at': time.time(), 'force_used': True,
                    'observer': observer, 'observer_terminate_right': False,
                    'provenance': 'FRESH_RETAINED_HANDLES_AFTER_ORIGINAL_OBSERVER_TIMEOUT',
                    'force_proposal_sha256': PROPOSAL_SHA,
                    'force_returned_sha256': sha(public / 'canonical-force-returned.json'),
                    'expired_observer_timeout_sha256': sha(base.PUBLIC / 'connector-exit-watch-timeout.json'),
                    'exits': {role: {'pid': h.pid, 'birth': h.birth, 'physical_exit': True,
                                    'exit_code': h.exit_code()} for role, h in handles.items()},
                    'work_settlement_claimed': False}
                # This path did not exist; preserve all original timeout/start/selection receipts.
                base.save('connector-exit-proof.json', proof)
                reserve(public / 'canonical-force-physical-exit.json', dict(proof,
                    original_namespace_proof_sha256=sha(base.PUBLIC / 'connector-exit-proof.json')))
                print(json.dumps({'status': 'ALL_THREE_PHYSICAL_EXITS_CONFIRMED', 'force_used': True}), flush=True)
                return code
            time.sleep(.2)
        reserve(public / 'canonical-force-observation-timeout.json', {'physical_exit_confirmed': False,
            'force_used': True, 'cohort': selected['cohort'], 'observer': observer,
            'status': 'UNKNOWN_NO_REPLAY_NO_RESTART'})
        return 3
    finally:
        if own is not None:
            own.close()
        for h in handles.values():
            h.close()


if __name__ == '__main__':
    raise SystemExit(main())
