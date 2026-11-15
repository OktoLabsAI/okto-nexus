"""Additive read-only adoption of the exact owner reported by failed start."""
from pathlib import Path
import argparse, hashlib, json, sys

HERE = Path(__file__).resolve().parent
PLAN_SHA = '4dc1ccd4673c5ddff8959510198cd1673f52151e0dec278f850e9d5e73a6dbbb'
EXPECTED_PID = 54052
EXPECTED_GENERATION = 'f054384a3bdc356a513741a027b84013'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-helper-sha256', required=True)
    args = parser.parse_args()
    if digest(__file__) != args.expected_helper_sha256:
        raise RuntimeError('SUPPLEMENT_CHANGED')
    plan_path = HERE / 'lifecycle-plan.json'
    if digest(plan_path) != PLAN_SHA:
        raise RuntimeError('PLAN_CHANGED')
    plan = json.loads(plan_path.read_bytes())
    for name, source in plan['runtime_pins'].items():
        if Path(source['path']).resolve() != HERE / name or digest(source['path']) != source['sha256']:
            raise RuntimeError('FROZEN_RUNTIME_CHANGED')
    sys.path.insert(0, str(HERE))
    from recovery_context import RecoveryContext, require, read_json, pin, sha
    import recovery_observation as O
    X = RecoveryContext(plan_path, PLAN_SHA)
    source = X.PUBLIC / 'nexus-start-returned.json'
    started = read_json(source); X.require_tags(started)
    projection = started.get('projection', {})
    reported = projection.get('observed_owner', {})
    require(started.get('returncode') == 3 and projection.get('state') == 'degraded'
            and projection.get('reason') == 'SERVICE_UNREACHABLE'
            and projection.get('ready_for_queries') is False,
            'EXACT_START_FAILURE_REQUIRED')
    require(reported.get('pid') == EXPECTED_PID and reported.get('generation') == EXPECTED_GENERATION
            and reported.get('instance_id') == X.C['tasks']['nexus']['instance_id'],
            'REPORTED_OWNER_CHANGED')
    stdout = X.PRIVATE / 'nexus-start.stdout'
    require(sha(stdout) == started['stdout_sha256'], 'ORIGINAL_START_OUTPUT_CHANGED')
    before_sha = sha(source)
    require(not (X.PUBLIC / 'nexus-owner-selection.json').exists()
            and not (X.PUBLIC / 'nexus-late-ready-proof.json').exists(), 'ALREADY_SELECTED')
    previous = read_json(pin(X.P['old_selections']['nexus']))
    # capture itself requires actual READY/ready_for_queries, active native task,
    # acknowledged cycle, exact image hashes/births and all three live handles.
    chosen, handles = O.capture(X)
    try:
        require(all(chosen.get(k) == reported.get(k) for k in O.IDENTITY), 'LATE_OWNER_CHANGED')
        require(chosen['task']['digest'] == X.C['tasks']['nexus']['digest'], 'TASK_DEFINITION_CHANGED')
        require(chosen['generation'] != previous['generation']
                and chosen['cohort']['cycle_id'] != previous['cohort']['cycle_id'], 'OLD_COHORT_REFUSED')
        O.same_cycle(chosen['cohort'], O.cycle(X))
        O.same_owner(chosen, O.status(X, 'nexus'))
        require(not any(h.exited() for h in handles.values()), 'COHORT_EXITED_BEFORE_SELECTION')
        require(sha(source) == before_sha and sha(stdout) == started['stdout_sha256'], 'START_EVIDENCE_CHANGED')
        X.save('nexus-late-ready-proof.json', {
            'status': 'SAME_REPORTED_OWNER_NOW_CANONICALLY_READY',
            'start_returned_pin': {'path': str(source), 'sha256': before_sha},
            'original_returncode': 3, 'original_failure_preserved': True,
            'start_stdout_sha256': started['stdout_sha256'],
            'pid': chosen['pid'], 'generation': chosen['generation'],
            'instance_id': chosen['instance_id'], 'cohort': chosen['cohort'],
            'task_digest': chosen['task']['digest'], 'actual_ready_capture': True,
            'all_three_handles_alive': True, 'new_start_count': 0,
            'service_controls': 0, 'provider_calls': 0, 'exit_proof_claimed': False})
        X.save('nexus-owner-selection.json', chosen)
    finally:
        for handle in handles.values():
            handle.close()
    print(json.dumps({'status': 'LATE_READY_OWNER_SELECTED_OBSERVATION_ONLY',
        'pid': chosen['pid'], 'generation': chosen['generation'],
        'cycle_id': chosen['cohort']['cycle_id'], 'original_returncode': 3,
        'new_start_count': 0, 'provider_calls': 0}))


if __name__ == '__main__':
    main()
