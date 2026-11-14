"""One separately selected canonical normal stop; no restart, force or replay."""
from pathlib import Path
import json
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
import supplement_common as s


def retained_zero_effect(context):
    root = context.ROOT
    raw = root / 'private/nexus-stop.stdout'
    result = s.read(root / 'public/lifecycle-nexus-stop-result.json')
    s.require(s.sha(raw) == s.OLD_STOP_SHA and result['output_sha256'] == s.OLD_STOP_SHA
        and result['returncode'] == 3 and result['reported_state'] == 'degraded', 'OLD_STOP_EVIDENCE_CHANGED')
    value = s.read(raw)
    s.require(value.get('state') == 'degraded' and value.get('reason') == 'SERVICE_UNREACHABLE'
        and value.get('next_action') == 'Inspect startup/transport diagnostics for this instance; no process was started.'
        and not any(k in value for k in ('shutdown', 'wait_timed_out', 'shutdown_outcome')), 'OLD_STOP_NOT_ZERO_EFFECT')
    control_path = Path(context.P['paths']['server_home']) / 'service-control.json'
    s.require(s.sha(control_path) == s.CONTROL_SHA, 'CONTROL_CHANGED_BEFORE_NEW_SELECTION')
    control = s.read(control_path)
    s.require(control.get('desired') == 'running' and control.get('generation') is None
        and control.get('launch_requested') is False, 'CONTROL_NOT_RUNNING_PRISTINE')
    s.require(s.sha(root / 'private/controller.json') == s.CHECKPOINT_SHA, 'CONTROLLER_CHANGED')
    return {'old_stop_output_sha256': s.OLD_STOP_SHA, 'control_sha256': s.CONTROL_SHA,
            'controller_checkpoint_sha256': s.CHECKPOINT_SHA}


def validate_owner(context, current, handle):
    s.require(current['pid'] == s.PID and current['generation'] == s.GENERATION
        and current['instance_id'] == context.C['tasks']['nexus']['instance_id']
        and current['task']['name'] == context.C['tasks']['nexus']['name']
        and current['task']['digest'] == s.TASK_DIGEST
        and handle.birth() == s.BIRTH and handle.wait(0) is False, 'EXACT_LIVE_OWNER_REQUIRED')


def run(context, deps, output, *, observe, process, popen=subprocess.Popen):
    # Original gate already validates installed product, canonical commands and
    # all original source hashes, including the zero-effect branch analyzed.
    retained = retained_zero_effect(context)
    choices = [v for v in context.C['steps'] if v['component'] == 'nexus' and v['action'] == 'stop']
    s.require(len(choices) == 1, 'ONE_CANONICAL_STOP_REQUIRED')
    command = choices[0]
    argv = command['argv']
    s.require(argv[0] == context.P['package_pins']['python'] and '--force' not in argv
        and command['task_name'] == context.C['tasks']['nexus']['name'], 'NORMAL_STOP_SCOPE_CHANGED')
    current = observe(context, 'nexus')  # original observer requires READY/task active
    handle = process(s.PID)
    try:
        validate_owner(context, current, handle)
        reservation = {**deps.common.tags(context), 'selection': 'SUPPLEMENTAL_NORMAL_STOP_ONCE',
            'prior_stop_effect': 'REFUSED_BEFORE_REQUEST_STOP', **retained, 'selected_at': time.time(),
            'pid': s.PID, 'birth_filetime': s.BIRTH, 'generation': s.GENERATION,
            'task_digest': s.TASK_DIGEST, 'argv': argv, 'force_used': False, 'replay_allowed': False}
        deps.common.reserve(output / 'normal-stop.reserved.json', reservation)
        with (output / 'normal-stop.stdout').open('xb') as stdout, (output / 'normal-stop.stderr').open('xb') as stderr:
            retained_zero_effect(context)
            validate_owner(context, observe(context, 'nexus'), handle)
            # No control/model mutation occurs before this explicit canonical CLI.
            child = popen(argv, env=context.env(), cwd=str(context.ROOT), stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            deps.common.reserve(output / 'normal-stop.process.json', {**deps.common.tags(context), 'pid': child.pid,
                'reservation_sha256': s.sha(output / 'normal-stop.reserved.json')})
            returncode = child.wait()  # CLI has its canonical bound; never kill on timeout.
        parse_error = None
        try:
            raw = s.read(output / 'normal-stop.stdout')
            if not isinstance(raw, dict):
                raise TypeError('Expected JSON object')
        except (OSError, ValueError, TypeError) as error:
            parse_error = type(error).__name__
            raw = {'state': 'unknown', 'reason': 'STOP_OUTPUT_NOT_CANONICAL'}
        result = {**deps.common.tags(context), 'status': 'SUPPLEMENTAL_NORMAL_STOP_CLI_RETURNED',
            'returncode': returncode, 'wrapper_exit_confirmed': True, 'force_used': False,
            'reservation_sha256': s.sha(output / 'normal-stop.reserved.json'),
            'stdout_sha256': s.sha(output / 'normal-stop.stdout'), 'stderr_sha256': s.sha(output / 'normal-stop.stderr'),
            'reported': {k: raw.get(k) for k in ('state', 'reason', 'pid', 'generation', 'instance_id', 'shutdown_outcome')},
            'output_parse_error': parse_error,
            'physical_owner_exit_inferred': False, 'completed_at': time.time()}
        deps.common.reserve(output / 'normal-stop.returned.json', result)
        return result
    finally:
        handle.close()


def main():
    args = s.parser().parse_args()
    context, deps = s.load(args)
    output = deps.common.secure_directory(s.HERE / 'runtime-private', s.HERE)
    result = run(context, deps, output, observe=deps.observation.status, process=deps.observation.PhysicalProcess)
    print(json.dumps({'status': result['status'], 'returncode': result['returncode'],
        'evidence_sha256': s.sha(output / 'normal-stop.returned.json'), 'reported': result['reported']}))
    return result['returncode']


if __name__ == '__main__':
    raise SystemExit(s.safe_main(main))
