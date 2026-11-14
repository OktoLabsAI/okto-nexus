"""Resume the reviewed, unapplied setup after the CLI encoding observation failed."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_case as original


def main():
    proposal = original.load('fda199aae01b33f9580d7c0152a43522e3330b70099350cce89684f0e3936927')
    base = original.BASE
    root = base / 'campaign'
    prefix = base / 'installation/venv'
    original.require(Path(sys.executable).resolve() == (prefix / 'Scripts/python.exe').resolve(), 'OWN_PYTHON_REQUIRED')
    original.verify_installed(proposal, prefix)
    previous_path = root / 'public/result.json'
    previous = json.loads(previous_path.read_bytes())
    original.require(previous['failure'] == 'CLI_JSON_UNCONFIRMED_plan'
        and previous['physical_owner_exit'] is True and previous['wrapper_processes_exited'] is True
        and previous['stop']['cli_exit'] == 0 and previous['stop']['state'] == 'stopped'
        and previous['preflight']['config']['credential_store'] == 'file'
        and previous['preflight']['account'] == {'account_present': False, 'requires_openai_auth': True, 'refresh_token': False}
        and previous['preflight']['physical_exit_observed'] is True,
        'EXACT_PRE_APPLY_FAILURE_REQUIRED')
    original.require(not (root / 'public/apply-reserved.json').exists()
        and not list((root / 'nexus-home/connection-tests').glob('*/journal.db')), 'SETUP_ALREADY_ATTEMPTED')
    profile_path = root / 'nexus-home/terminal/profiles' / (original.PROFILE + '.json')
    review = json.loads(profile_path.read_bytes())
    revision = original.validate_review(review, proposal, root)
    original.require(revision == '96d1661b79dd5d6050b62bf08252332c1e764b15ee96bf6ee0c290b26a46a33d',
        'ROOT_REVIEW_CHANGED')
    config = root / 'profile/.codex/config.toml'
    original.require(config.read_text(encoding='utf8') == original.CONFIG
        and not (root / 'profile/.codex/auth.json').exists(), 'AUTH_CONTEXT_CHANGED')
    output = root / 'resume-encoding'
    output.mkdir(exist_ok=False)
    (output / 'private').mkdir()
    result = {'status': 'UNCONFIRMED', 'scope': 'Same reviewed setup, first apply; no repeated plan or native preflight',
        'previous_result_sha256': original.sha(previous_path), 'profile_before_sha256': original.sha(profile_path),
        'review_revision': revision, 'driver_sha256': original.sha(__file__), 'model_turn_limit': 0,
        'change': 'Explicit Python -X utf8 because -I ignores PYTHONUTF8; one normal restart of the same own stopped service.'}
    original.write_once(output / 'reserved.json', result)
    env = original.environment(root, prefix, Path(proposal['pins']['native']['path']), os.environ)
    selection = ['--home', str(root / 'nexus-home'), '--host', '127.0.0.1', '--port', str(proposal['port']),
        '--project-root', str(root / 'project'), '--embedding-mode', 'off', '--feature-harness-integrations', 'true',
        '--metrics-mode', 'disabled', '--harness-root', str(Path(proposal['pins']['native']['path']).parent)]
    children = []

    def cli(label, args, timeout=90):
        argv = [sys.executable, '-I', '-B', '-X', 'utf8', '-m', 'okto_nexus.adapters.inbound.cli.main', *args, *selection]
        original.write_once(output / (label + '-reserved.json'), {'argv': argv, 'time': time.time()})
        with (output / 'private' / (label + '.stdout')).open('xb') as out, (output / 'private' / (label + '.stderr')).open('xb') as err:
            child = subprocess.Popen(argv, cwd=root, env=env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
            children.append(child)
            code = child.wait(timeout=timeout)
        raw = (output / 'private' / (label + '.stdout')).read_bytes()
        original.require(len(raw) <= 8 * 1048576, 'CLI_OUTPUT_TOO_LARGE')
        return code, json.loads(raw)

    proof = None
    started = False
    failure = None
    try:
        code, absent = cli('before', ['service', 'status', '--json'])
        original.require(absent['state'] == 'stopped' and absent['pid'] is None, 'PREDECESSOR_OWNER_NOT_ABSENT')
        started = True
        code, owner = cli('start', ['service', 'start', '--timeout', '120', '--json'], 150)
        original.require(code == 0 and owner['state'] == 'ready' and owner['ready_for_queries'] is True, 'SERVICE_NOT_READY')
        proof = original.ProcessProof(owner['pid'])
        result['owner'] = {key: owner[key] for key in ('pid', 'generation', 'instance_id', 'active_version')}
        result['owner']['birth_100ns'] = proof.birth
        code, observed = cli('confirmed', ['service', 'status', '--json'])
        original.require(code == 0 and observed['ready_for_queries'] is True and not proof.wait(0)
            and all(observed[key] == owner[key] for key in ('pid', 'generation', 'instance_id')),
            'OWNER_CHANGED')
        original.require(original.sha(profile_path) == result['profile_before_sha256']
            and config.read_text(encoding='utf8') == original.CONFIG
            and not (root / 'profile/.codex/auth.json').exists(), 'REVIEW_OR_AUTH_CHANGED')
        code, value = cli('apply', ['connect', '--profile', original.PROFILE, '--approve', revision,
            '--no-chat', '--timeout', '120', '--json'], 270)
        original.require(code == 3, 'EXPECTED_AUTH_REFUSAL_EXIT')
        result['cli'] = original.validate_failure(value, root)
        code, observed = cli('after', ['service', 'status', '--json'])
        original.require(code == 0 and observed['state'] == 'ready' and observed['ready_for_queries'] is True
            and all(observed[key] == owner[key] for key in ('pid', 'generation', 'instance_id')) and not proof.wait(0),
            'OWNER_NOT_RESPONSIVE_AFTER_FAILURE')
        result['owner_still_ready_after_failure'] = True
    except Exception as error:
        failure = str(error) if isinstance(error, original.Refused) else type(error).__name__
    finally:
        if started:
            try:
                code, stopped = cli('stop', ['service', 'stop', '--timeout', '45', '--json'])
                result['stop'] = {'cli_exit': code, 'state': stopped.get('state'), 'reason': stopped.get('reason')}
                result['physical_owner_exit'] = proof is not None and proof.wait(15)
            except Exception as error:
                result['stop_error'] = type(error).__name__
        if proof is not None:
            proof.close()
    result['wrapper_processes_exited'] = all(child.poll() is not None for child in children)
    if (failure is None and result.get('physical_owner_exit') is True and result['wrapper_processes_exited']
        and result['stop']['cli_exit'] == 0 and result['stop']['state'] == 'stopped'):
        try:
            result['journal'] = original.journal_proof(root)
            result['status'] = 'DX_T34_AUTH_ABSENT_DIAGNOSED_ZERO_TURN'
        except Exception as error:
            failure = str(error) if isinstance(error, original.Refused) else type(error).__name__
    result['failure'] = failure
    original.write_once(output / 'result.json', result)
    print(json.dumps(result), flush=True)
    return 0 if result['status'] == 'DX_T34_AUTH_ABSENT_DIAGNOSED_ZERO_TURN' else 3


if __name__ == '__main__':
    raise SystemExit(main())
