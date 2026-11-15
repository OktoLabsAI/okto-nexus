"""Additive, one-shot Connector restart after persisted storage consent."""
from pathlib import Path
import argparse
import json
import runpy
import subprocess
import sys

HERE = Path(__file__).resolve().parent
RECOVERY = HERE.parent
sys.path.insert(0, str(RECOVERY))
from recovery_context import RecoveryContext, require, read_json, sha, pin, reserve
import recovery_connector as connector
import recovery_observation as observed

LIFECYCLE_SHA = '8980570ab636b7836ffa34a5976652c0cc19825af015c50d50a9c5b08bcf6a27'
ORIGINAL_CURRENT_READY = connector.current_ready


def validate_identity(state, server_id, agent_id):
    require(state.preferences.get('vault.fallback_file.approved') is True,
            'PERSISTED_STORAGE_CONSENT_REQUIRED')
    identity = state.identity_for(server_id, agent_id)
    require(identity is not None and identity.credential_epoch == 2 and not identity.revoked,
            'IMPORTED_EPOCH2_REQUIRED')


def validate_fresh(current, previous):
    require(current['generation'] != previous['generation']
            and current['cohort']['cycle_id'] != previous['cohort']['cycle_id'],
            'NEW_CONNECTOR_GENERATION_AND_CYCLE_REQUIRED')
    require(current['instance_id'] == previous['instance_id']
            and current['task']['digest'] == previous['task']['digest']
            and current['task']['name'] == previous['task']['name'],
            'CONNECTOR_SCOPE_CHANGED')


class View:
    def __init__(self, base, plan_sha):
        self.base, self.restart_plan_sha256 = base, plan_sha
        self.PUBLIC, self.PRIVATE = HERE / 'public', HERE / 'private'
        self.CONTROL = HERE

    def __getattr__(self, name):
        return getattr(self.base, name)

    def save(self, name, value):
        require(Path(name).name == name and name.endswith('.json'), 'INVALID_PUBLIC_NAME')
        reserve(self.PUBLIC / name, dict(value, lifecycle_plan_sha256=self.plan_sha256,
                                        consent_restart_plan_sha256=self.restart_plan_sha256))

    def require_tags(self, value):
        self.base.require_tags(value)
        require(value.get('consent_restart_plan_sha256') == self.restart_plan_sha256,
                'CONSENT_RESTART_RECEIPT_CHANGED')

    def require_ready(self):
        return {'nexus': self.base.require_nexus_ready(), 'connector': ORIGINAL_CURRENT_READY(self)}


def state_gate(base):
    from okto_nexus_connector.platform.paths import state_file
    from okto_nexus_connector.storage.state_store import StateStore
    state = StateStore(state_file(Path(base.P['paths']['connector_state']))).load()
    validate_identity(state, 'srv_a3f134b449dbffa20c126dae6f9a8aa9', 'm1-sonnet-remote')
    rotation = read_json(base.PUBLIC / 'rotation-import-result.json')
    require(rotation.get('status') == 'ROTATED_ONCE_IMPORTED_ONCE', 'ROTATION_IMPORT_REQUIRED')


def pre_start(view):
    base = view.base
    base.require_nexus_ready()
    base.require_migrated('connector')
    state_gate(base)
    stopped = read_json(base.PUBLIC / 'connector-stop-returned.json')
    base.require_tags(stopped)
    previous = read_json(base.PUBLIC / 'connector-owner-selection.json')
    base.require_tags(previous)
    projection = stopped.get('projection', {})
    require(stopped.get('returncode') == 0 or (stopped.get('returncode') == 4
            and projection.get('state') == 'stopping'
            and all(projection.get(k) == previous[k] for k in ('pid', 'generation', 'instance_id'))),
            'ORIGINAL_NORMAL_STOP_SELECTION_REQUIRED')
    # rc4 is preserved as an expired observation, never relabeled stop success.
    # Only subsequent retained-handle physical exit and native/canonical absence allow start.
    proof = connector.cleanup_valid(base)
    service = connector.installation(base)
    _, task = service.observe()
    require(task is not None and task.enabled and not task.active
            and task.digest == previous['task']['digest']
            and service.name == previous['task']['name'], 'SAME_INSTALLED_INACTIVE_TASK_REQUIRED')
    return previous, proof


def start(view):
    previous, proof = pre_start(view)
    for path in (view.PUBLIC, view.PRIVATE):
        if not path.exists():
            observed.secure_directory(path, HERE)
    argv = connector.commands(view)['start']
    view.save('connector-start-reserved.json', {'state': 'RESERVED_BEFORE_DISPATCH', 'argv': argv,
        'previous_cohort': previous['cohort'], 'previous_generation': previous['generation'],
        'previous_exit_proof_sha256': sha(view.base.PUBLIC / 'connector-exit-proof.json'),
        'original_stop_returncode': read_json(view.base.PUBLIC / 'connector-stop-returned.json')['returncode'],
        'native_inactive': proof['native_inactive'], 'provider_calls': 0, 'force_used': False})
    pre_start(view)
    with (view.PRIVATE / 'connector-start.stdout').open('xb') as out, \
            (view.PRIVATE / 'connector-start.stderr').open('xb') as err:
        child = subprocess.Popen(argv, cwd=view.ROOT, env=view.connector_env(), stdin=subprocess.DEVNULL,
                                 stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
        code = child.wait()  # Retained wrapper; no kill, replay, or hidden restart.
    result = {'returncode': code, 'stdout_sha256': sha(view.PRIVATE / 'connector-start.stdout'),
              'stderr_sha256': sha(view.PRIVATE / 'connector-start.stderr')}
    try:
        raw = read_json(view.PRIVATE / 'connector-start.stdout')
        data = raw.get('data', raw)
        result['projection'] = {k: data.get(k) for k in ('state', 'reason', 'code', 'pid', 'generation', 'instance_id') if k in data}
    except (ValueError, TypeError, AttributeError):
        result['parse_error'] = 'CLI_JSON_UNCONFIRMED'
    view.save('connector-start-returned.json', result)
    require(code == 0 and not result.get('parse_error'), 'CONNECTOR_START_UNCONFIRMED_NO_REPLAY')
    return result


def select(view):
    receipt = read_json(view.PUBLIC / 'connector-start-returned.json')
    view.require_tags(receipt)
    require(receipt.get('returncode') == 0 and not receipt.get('parse_error'), 'START_NOT_CONFIRMED')
    current, handles = connector.capture(view)
    try:
        previous = read_json(view.base.PUBLIC / 'connector-owner-selection.json')
        view.base.require_tags(previous)
        validate_fresh(current, previous)
        view.save('connector-owner-selection.json', current)
        return current
    finally:
        for handle in handles.values():
            handle.close()


def install_routing(plan_sha):
    def routed_current(context):
        if Path(context.PUBLIC).resolve() == RECOVERY / 'public':
            context = View(context, plan_sha)
        return ORIGINAL_CURRENT_READY(context)
    connector.current_ready = routed_current
    def ready(base):
        return {'nexus': base.require_nexus_ready(), 'connector': routed_current(base)}
    RecoveryContext.require_ready = ready


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-plan-sha256', required=True)
    parser.add_argument('--script')
    parser.add_argument('--script-sha256')
    parser.add_argument('action', choices=('start', 'select', 'watch', 'stop', 'cleanup', 'uninstall', 'run'))
    args, rest = parser.parse_known_args()
    plan = HERE / 'plan.json'
    require(sha(plan) == args.expected_plan_sha256, 'RESTART_PLAN_CHANGED')
    for item in read_json(plan)['pins'].values():
        pin(item)
    base = RecoveryContext(RECOVERY / 'lifecycle-plan.json', LIFECYCLE_SHA)
    view = View(base, args.expected_plan_sha256)
    if args.action == 'run':
        require(args.script is not None and args.script_sha256 is not None, 'PINNED_SCRIPT_REQUIRED')
        script = Path(args.script).resolve()
        require(script.is_relative_to(RECOVERY) and script != Path(__file__).resolve(), 'RECOVERY_SCRIPT_REQUIRED')
        require(sha(script) == args.script_sha256, 'RECOVERY_SCRIPT_CHANGED')
        install_routing(args.expected_plan_sha256)
        if rest and rest[0] == '--':
            rest = rest[1:]
        sys.argv = [str(script), *rest]
        sys.path.insert(0, str(script.parent))
        runpy.run_path(str(script), run_name='__main__')
        return
    require(not rest and args.script is None and args.script_sha256 is None, 'UNEXPECTED_ARGUMENTS')
    if args.action == 'start':
        result = start(view)
    elif args.action == 'select':
        result = select(view)
    elif args.action == 'watch':
        result = connector.watch(view)
    elif args.action == 'stop':
        result = connector.normal_stop(view)
    elif args.action == 'cleanup':
        result = connector.cleanup_valid(view)
        view.save('connector-cleanup.json', result)
    else:
        result = connector.lifecycle(view, 'uninstall')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
