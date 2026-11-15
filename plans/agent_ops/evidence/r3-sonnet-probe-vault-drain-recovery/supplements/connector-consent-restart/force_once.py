"""One explicitly authorized canonical force request; no OS termination API."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from recovery_context import RecoveryContext, require, read_json, sha, pin, reserve
import recovery_connector as connector
import recovery_observation as observed

LIFECYCLE_SHA = '8980570ab636b7836ffa34a5976652c0cc19825af015c50d50a9c5b08bcf6a27'


def validate_authorization(value, proposal, proposal_sha):
    require(value.get('status') == 'SPECIFIC_CONNECTOR_FORCE_AUTHORIZED'
            and value.get('proposal_sha256') == proposal_sha
            and type(value.get('max_canonical_force_calls')) is int
            and value['max_canonical_force_calls'] == 1
            and value.get('force_authorized') is True
            and value.get('target') == proposal['target']
            and isinstance(value.get('user_message_reference'), str)
            and bool(value['user_message_reference'].strip()), 'SPECIFIC_USER_AUTHORIZATION_REQUIRED')


def validate_status(raw, selected):
    require(all(raw.get(k) == selected[k] for k in ('pid', 'generation', 'instance_id')),
            'FORCE_OWNER_CHANGED')
    drain = raw.get('drain') or {}
    require(raw.get('running') is True and raw.get('ipc_ok') is True
            and raw.get('draining') is True and raw.get('state') == 'stopping'
            and drain.get('state') == 'DRAINING_PENDING'
            and drain.get('force_available') is True and drain.get('force_requested') is False,
            'CANONICAL_FORCE_NOT_AVAILABLE')
    return {k: drain.get(k) for k in ('state', 'phase', 'observation', 'force_available', 'force_requested')}


def preflight(base, proposal, handles):
    from okto_nexus_connector.daemon import manager
    selected = read_json(pin(proposal['pins']['selection']))
    watcher = read_json(pin(proposal['pins']['watcher']))
    base.require_tags(selected)
    base.require_tags(watcher)
    require(watcher['cohort'] == selected['cohort'] and watcher['retained_roles'] == list(observed.ROLES)
            and watcher.get('terminate_right') is False, 'ORIGINAL_OBSERVER_SCOPE_CHANGED')
    require(not (base.PUBLIC / 'connector-exit-proof.json').exists()
            and not (base.PUBLIC / 'connector-exit-watch-timeout.json').exists(), 'ORIGINAL_OBSERVER_NOT_CURRENT')
    require({k: selected[k] for k in ('pid', 'generation', 'instance_id')} == proposal['target']['owner']
            and selected['cohort'] == proposal['target']['cohort']
            and selected['task'] == proposal['target']['task'], 'EXACT_TARGET_CHANGED')
    service = connector.installation(base)
    _, task = service.observe()
    require(task is not None and task.active and task.enabled
            and task.digest == selected['task']['digest'] and service.name == selected['task']['name'],
            'EXACT_ACTIVE_TASK_REQUIRED')
    observed.same_cycle(selected['cohort'], connector.cycle(base))
    identities = dict((role, selected['cohort'][role]) for role in observed.ROLES)
    identities['observer'] = watcher['observer']
    for role, identity in identities.items():
        if role not in handles:
            handles[role] = observed.Process(identity['pid'])
        handle = handles[role]
        require(handle.pid == identity['pid'] and handle.birth == identity['birth']
                and handle.image in base.installed['python_images']
                and sha(handle.image) == base.installed['python_images'][handle.image]
                and not handle.exited(), 'LIVE_EXACT_COHORT_AND_OBSERVER_REQUIRED')
    raw = manager.status(Path(base.P['paths']['connector_state']), timeout=5).to_json()
    projection = validate_status(raw, selected)
    observed.same_cycle(selected['cohort'], connector.cycle(base))
    require(not any(handle.exited() for handle in handles.values()), 'COHORT_CHANGED_BEFORE_FORCE')
    return projection


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-proposal-sha256', required=True)
    parser.add_argument('--authorization-sha256', required=True)
    args = parser.parse_args()
    proposal_path = HERE / 'force-proposal.json'
    require(sha(proposal_path) == args.expected_proposal_sha256, 'FORCE_PROPOSAL_CHANGED')
    proposal = read_json(proposal_path)
    for item in proposal['pins'].values():
        pin(item)
    authorization = HERE / 'force-authorization.json'
    require(sha(authorization) == args.authorization_sha256, 'FORCE_AUTHORIZATION_CHANGED')
    validate_authorization(read_json(authorization), proposal, args.expected_proposal_sha256)
    base = RecoveryContext(ROOT / 'lifecycle-plan.json', LIFECYCLE_SHA)
    require(proposal['argv'] == connector.stop_argv(base) + ['--force', '--expected-generation', proposal['target']['owner']['generation']],
            'CANONICAL_FORCE_ARGV_CHANGED')
    public, private = HERE / 'public', HERE / 'private'
    for directory in (public, private):
        if not directory.exists():
            observed.secure_directory(directory, HERE)
    handles = {}
    try:
        before = preflight(base, proposal, handles)
        reserve(public / 'canonical-force-reserved.json', {
            'status': 'SINGLE_CANONICAL_FORCE_RESERVED', 'proposal_sha256': args.expected_proposal_sha256,
            'authorization_sha256': args.authorization_sha256, 'target': proposal['target'],
            'preflight': before, 'argv': proposal['argv'], 'force_authorized': True,
            'force_dispatched': False, 'provider_calls': 0})
        preflight(base, proposal, handles)
        with (private / 'canonical-force.stdout').open('xb') as out, \
                (private / 'canonical-force.stderr').open('xb') as err:
            child = subprocess.Popen(proposal['argv'], cwd=base.ROOT, env=base.connector_env(),
                stdin=subprocess.DEVNULL, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
            code = child.wait()  # Root retains wrapper; never kill/retry a pending command.
        result = {'status': 'CANONICAL_FORCE_RETURNED', 'proposal_sha256': args.expected_proposal_sha256,
                  'authorization_sha256': args.authorization_sha256, 'returncode': code,
                  'force_used': True, 'canonical_force_calls': 1, 'os_termination_calls': 0,
                  'provider_calls': 0, 'stdout_sha256': sha(private / 'canonical-force.stdout'),
                  'stderr_sha256': sha(private / 'canonical-force.stderr'),
                  'original_observer_force_false_means': 'OBSERVER_DID_NOT_TERMINATE_PROCESSES_ONLY',
                  'work_settlement_claimed': False}
        try:
            raw = read_json(private / 'canonical-force.stdout')
            data = raw.get('data', raw)
            result['projection'] = {k: data.get(k) for k in ('state', 'reason', 'code', 'pid', 'generation', 'instance_id', 'shutdown_outcome', 'stopped') if k in data}
        except (ValueError, TypeError, AttributeError):
            result['parse_error'] = 'CANONICAL_RESULT_UNCONFIRMED'
        exits = {}
        for role in observed.ROLES:
            try:
                exits[role] = handles[role].exited()
            except Exception:
                exits[role] = None
        result['physical_exits_at_return'] = exits
        result['all_three_physical_exits_at_return'] = all(value is True for value in exits.values())
        try:
            result['original_observer_still_live'] = not handles['observer'].exited()
        except Exception:
            result['original_observer_still_live'] = None
        reserve(public / 'canonical-force-returned.json', result)
        print(json.dumps(result))
        return code
    finally:
        # The separately retained original observer remains the authoritative exit proof.
        for handle in handles.values():
            handle.close()


if __name__ == '__main__':
    raise SystemExit(main())
