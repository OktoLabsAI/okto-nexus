"""Finite, opt-in installed CLI observation; no product imports in offline mode."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            value.update(block)
    return value.hexdigest()


def require(value, code):
    if not value:
        raise ValueError(code)


def save(name, value):
    with (ROOT / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)


def check_profile(plan, value):
    expected = plan['nexus']['profile_selection']
    require(value.get('state') == 'done' and value.get('result', {}).get('saved') is True,
            'COMPLETED_PROFILE_REQUIRED')
    require(value.get('server_id') == expected['server_id'] and
            value.get('selection', {}).get('agent') == expected['agent_id'] and
            value.get('selection', {}).get('project') == expected['project'] and
            value.get('result', {}).get('binding', {}).get('binding_id') == expected['binding_id'],
            'PROFILE_SELECTION_CHANGED')
    require(not any(value.get(key) for key in ('login_start_operation', 'login_start_plan')) and
            not value.get('selection', {}).get('login_start') and
            not value.get('selection', {}).get('remote_draft'), 'EXTRA_SETUP_EFFECT_NOT_SELECTED')


def validate(plan):
    for pin in plan['pins']:
        require(digest(pin['path']) == pin['sha256'], 'PIN_CHANGED')
    profile = Path(plan['nexus']['profile_path'])
    require(digest(profile) == plan['nexus']['profile_sha256'], 'PROFILE_BYTES_CHANGED')
    check_profile(plan, json.loads(profile.read_bytes()))


def worker(plan):
    require(Path(sys.prefix).resolve() == Path(plan['python_prefix']).resolve(), 'INSTALLED_PREFIX_REQUIRED')
    validate(plan)
    import okto_nexus.adapters.inbound.cli.connect as cli
    from okto_nexus.application.terminal_connection import ConnectionError
    require(Path(cli.__file__).resolve() == Path(plan['installed_connect']).resolve(), 'IMPORT_ORIGIN_CHANGED')
    profile = Path(plan['nexus']['profile_path']).resolve()
    counts = {'setup_get': 0, 'setup_non_get_attempts': 0, 'observe': 0}
    observed = {}
    selected_service = []
    original_read = cli.read_json
    original_resolve = cli.resolve_local_service
    original_flow = cli.TerminalConnection

    def guarded_read(path):
        value = original_read(path)
        if Path(path).resolve() == profile:
            # Called again by the real CLI after its profile guard is acquired.
            require(digest(profile) == plan['nexus']['profile_sha256'], 'PROFILE_BYTES_CHANGED')
            check_profile(plan, value)
        return value

    def resolve(*args, **kwargs):
        service = original_resolve(*args, **kwargs)
        status = service.inspect()
        native = status.get('user_service', {})
        require(status.get('state') == 'stopped' and
                status.get('instance_id') == plan['nexus']['instance_id'] and
                native.get('name') == plan['nexus']['task_name'] and native.get('state') == 3,
                'SELECTED_INSTALLED_SERVICE_MUST_ALREADY_BE_STOPPED')
        selected_service.append((service, native.get('definition_digest')))
        return service

    def denied(*args, **kwargs):
        raise ConnectionError('SVC20_SETUP_NOT_SELECTED', 'Only completed connection observation is selected.')

    class ObserveOnly(original_flow):
        def __init__(self, call, save, **kwargs):
            def readonly(method, path, body=None):
                if method != 'GET':
                    counts['setup_non_get_attempts'] += 1
                    return denied()
                counts['setup_get'] += 1
                return call(method, path, body)
            super().__init__(readonly, denied, **kwargs)

        review = denied
        apply = denied

        def observe(self, document):
            check_profile(plan, document)
            result = super().observe(document)
            counts['observe'] += 1
            for key in ('state', 'server_id', 'agent_id', 'binding_id', 'workspace_id', 'work_state'):
                observed[key] = result.get(key)
            return result

    cli.read_json = guarded_read
    cli.resolve_local_service = resolve
    cli.TerminalConnection = ObserveOnly
    cli.connect_login.resume = denied
    cli.connect_login.authorize = denied
    code = cli.run_connect(plan['nexus']['cli_arguments'])
    ready = selected_service[0][0].inspect() if selected_service else {}
    expected = plan['nexus']['profile_selection']
    confirmed = (code == 0 and counts['observe'] == 1 and counts['setup_non_get_attempts'] == 0 and
                 observed.get('state') == 'configured' and observed.get('work_state') == 'not_submitted' and
                 all(observed.get(key) == expected[key] for key in ('server_id', 'agent_id', 'binding_id')) and
                 ready.get('state') == 'ready' and ready.get('instance_id') == plan['nexus']['instance_id'] and
                 ready.get('user_service', {}).get('name') == plan['nexus']['task_name'] and
                 ready.get('user_service', {}).get('definition_digest') == selected_service[0][1] and
                 digest(profile) == plan['nexus']['profile_sha256'])
    save('nexus-observation.json', {
        'status': 'CONFIGURED_NEXT_CONNECT_OBSERVED' if confirmed else 'NEXT_CONNECT_UNCONFIRMED',
        'cli_exit_code': code, 'counts': counts, 'connection': observed,
        'service': {key: ready.get(key) for key in ('state', 'instance_id', 'pid', 'generation')},
        'native': {key: ready.get('user_service', {}).get(key) for key in ('name', 'state', 'definition_digest')},
        'acceptance_promoted': False,
        'limitation': 'Root must retain the canonical parent/launcher/runtime cohort and own subsequent lifecycle; this driver neither stops nor uninstalls.'})
    return 0 if confirmed else 3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-nexus', action='store_true')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    plan = json.loads((ROOT / 'plan.json').read_bytes())
    if not args.execute_nexus and not args.worker:
        print(json.dumps({'status': plan['status'], 'nexus_argv': plan['nexus']['canonical_argv'],
                          'connector': plan['connector'], 'effects': 0}, indent=2))
        return 0
    validate(plan)
    if args.worker:
        return worker(plan)
    save('nexus-selection.json', {'plan_sha256': digest(ROOT / 'plan.json'),
                                'selected_at': time.time(), 'single_invocation': True})
    # Inherit the selected caller environment; no credential is added/read, no PATH mutation.
    argv = [plan['python'], '-I', '-B', '-X', 'utf8', str(ROOT / 'run.py'), '--worker']
    with (ROOT / 'nexus-cli.stdout.private').open('xb') as out, (ROOT / 'nexus-cli.stderr.private').open('xb') as err:
        child = subprocess.Popen(argv, cwd=plan['nexus']['profile_selection']['project'],
            stdin=subprocess.DEVNULL, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            code = child.wait(timeout=180)
        except subprocess.TimeoutExpired:
            save('nexus-timeout.json', {'status': 'CLI_TIMEOUT_UNCONFIRMED_NO_REPLAY', 'pid': child.pid,
                'handle_retained': True, 'normal_cleanup_owner': 'root', 'forced_termination': False})
            # Only retain the already-selected CLI handle; no parallel stop or repeat.
            try:
                code = child.wait(timeout=7200)
            except subprocess.TimeoutExpired:
                save('nexus-handoff-expired.json', {'status': 'UNKNOWN', 'pid': child.pid,
                    'exit_confirmed': False, 'retry_allowed': False})
                return 3
            save('nexus-late-cli-exit.json', {'returncode': code, 'exit_confirmed': True,
                                           'acceptance_promoted': False})
            return 3
    save('nexus-cli-exit.json', {'returncode': code, 'exit_confirmed': True,
                               'stdout_sha256': digest(ROOT / 'nexus-cli.stdout.private'),
                               'stderr_sha256': digest(ROOT / 'nexus-cli.stderr.private')})
    return code


if __name__ == '__main__':
    raise SystemExit(main())
