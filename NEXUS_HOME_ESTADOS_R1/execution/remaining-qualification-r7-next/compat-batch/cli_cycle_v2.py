"""PREPARED actual installed CLI cycle over a separately owned real foreground Server."""
import argparse
import hashlib
import json
import sqlite3
import subprocess
import time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--gate', choices=['ROOT_APPROVED_COMPAT_BATCH'], required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--phase', choices=['s3-current', 's4-old'], required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--operator-cookie-file', type=Path, required=True)
    args = parser.parse_args()
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha(args.manifest) == args.manifest_sha256
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    assert manifest['status'] == 'PREPARED_BOUND_NOT_EXECUTED'
    root, home = args.root.resolve(), args.home.resolve()
    assert root.name.startswith('nexus-hst-compat-') and home.is_relative_to(root)
    python = manifest['phases'][args.phase]['python']
    profile = 'compat'
    service_args = ['--home', str(home), '--host', '127.0.0.1', '--port', str(args.port)]
    project, provider = root / 'project', root / 'provider-home'
    assert project.is_dir() and provider.is_dir()
    records = []

    def invoke(argv, *, allowed=(0,), timeout=30):
        command = [python, '-I', '-B', '-X', 'utf8', '-m', 'okto_nexus.adapters.inbound.cli.main', *argv, '--json']
        result = subprocess.run(command, cwd=root / 'cwd', stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding='utf-8', timeout=timeout, check=False)
        # Raw stdout is retained only inside this own private Temp tree.
        sequence = len(records) + 1
        (root / 'control' / f'cli-{args.phase}-{sequence}.stdout').write_text(result.stdout, encoding='utf-8')
        (root / 'control' / f'cli-{args.phase}-{sequence}.stderr').write_text(result.stderr, encoding='utf-8')
        value = json.loads(result.stdout)
        records.append({'argv': argv, 'exit_code': result.returncode})
        assert result.returncode in allowed, (result.returncode, value)
        return value

    def status():
        value = invoke(['service', 'status', *service_args])
        assert value['state'] == 'ready' and value['pid'] and value['generation']
        return {key: value[key] for key in ('pid', 'generation', 'instance_id')}

    owner = status()
    base = ['connect', 'codex', 'Compat project', '--id', 'compat-harness', '--profile', profile,
        '--project', str(project), '--provider-home', str(provider), '--no-chat', *service_args]
    review = invoke([*base, '--plan'])
    assert review['state'] == 'review' and review['review_revision']
    done = invoke([*base, '--approve', review['review_revision']])
    assert done['quick_connect']['status'] == 'connected'
    saved = json.loads((home / 'terminal/profiles/compat.json').read_text(encoding='utf-8'))
    binding = saved['result']['binding']

    def protected():
        # Read only selected invariants; never claim a whole-DB read-only snapshot.
        with sqlite3.connect((home / 'nexus.db').as_uri() + '?mode=ro', uri=True) as conn:
            scopes = {
                'execution_bindings': ('binding_id', binding['binding_id']),
                'agent_endpoints': ('endpoint_id', binding['endpoint_id']),
                'runtime_execution_grants': ('endpoint_id', binding['endpoint_id']),
                'execution_realizations': ('realization_ref', binding['realization_ref']),
                'execution_local_realizations': ('realization_ref', binding['realization_ref']),
                'workspaces': ('workspace_id', binding['workspace_id']),
            }
            rows = {table: conn.execute('SELECT * FROM ' + table + ' WHERE ' + field + '=? ORDER BY rowid', (value,)).fetchall()
                for table, (field, value) in scopes.items()}
            rows['runtime_profiles'] = conn.execute('SELECT * FROM runtime_profiles WHERE profile_id IN '
                '(SELECT profile_id FROM agent_endpoints WHERE endpoint_id=?) ORDER BY rowid', (binding['endpoint_id'],)).fetchall()
            return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()

    marker = 'compat-release'
    message = 'HST:' + json.dumps({'gate': marker, 'question': True, 'blocking': True, 'message': 'Compat inert result'})
    sent = invoke(['work', 'send', '--message', message, '--profile', profile, *service_args])
    assert sent['submission_turn_operation_id']
    deadline = time.monotonic() + 30
    while True:
        observed = invoke(['work', 'status', '--profile', profile, *service_args])
        if observed['requests']['items']:
            break
        assert time.monotonic() < deadline, 'No canonical CLI native question'
        time.sleep(.1)
    request = observed['requests']['items'][0]
    approval_id = request['approval_id']
    before_files = {name: sha(home / name) for name in ('terminal/profiles/compat.json', 'terminal/work/compat.json')}
    assert status() == owner
    before_protected = protected()
    ready = {'owner': owner, 'binding': binding, 'session_id': observed['session']['scope']['session_id'],
        'operation_id': sent['submission_turn_operation_id'], 'approval_id': approval_id,
        'phase': args.phase, 'before_files': before_files, 'browser_started': False}
    (root / 'control' / ('cli-active-' + args.phase + '.json')).write_text(json.dumps(ready, indent=2), encoding='utf-8')
    if args.phase == 's3-current':
        # Browser phase is separately gated; it must click Settings, not edit localStorage.
        deadline = time.monotonic() + 60
        while not (root / 'control/browser-s3.done').exists():
            assert time.monotonic() < deadline, 'Browser rollback evidence not completed'
            time.sleep(.1)
        assert before_files == {name: sha(home / name) for name in before_files}
        assert protected() == before_protected
        assert status() == owner
    reviewed = invoke(['work', 'answer', '--approval-id', approval_id, '--profile', profile, *service_args])
    assert reviewed['state'] == 'decision_review'
    proposal = reviewed['detail']['request_payload']['kwargs']
    cookie = json.loads(args.operator_cookie_file.read_text(encoding='utf-8'))['cookie']
    opener = build_opener(ProxyHandler({}))
    request = Request(f'http://127.0.0.1:{args.port}/api/v1/runtime-management/connections/me',
        headers={'X-Nexus-UI':'1','X-Nexus-Operator-Session-Required':'1','Cookie':'nexus_operator_session='+cookie})
    with opener.open(request, timeout=10) as response:
        raw = json.load(response)
    me = raw.get('data', raw)
    assert me['agent_id'] == (proposal.get('recipient_agent_id') or 'operator') == 'operator', 'No impersonation or recipient rewrite permitted'
    answer = root / 'control/answer.private.json'
    answer.write_text(json.dumps({'answers': {'format': {'answers': ['text']}}}), encoding='utf-8')
    decision = invoke(['work', 'answer', '--approval-id', approval_id, '--decision', 'approve',
        '--answer-file', str(answer), '--review', reviewed['review_revision'], '--profile', profile, *service_args])
    assert decision['canonical_state'] == 'CONFIRMED'
    # This releases only synthetic output. It does not ACK or write a runtime fact.
    (root / 'control' / marker).touch()
    deadline = time.monotonic() + 30
    while True:
        result = invoke(['work', 'status', '--profile', profile, *service_args])
        if result['state'] == 'completed':
            break
        assert time.monotonic() < deadline, 'Canonical CLI result did not complete'
        time.sleep(.1)
    assert any(op.get('result', {}).get('output_text') for op in result['operations'] if op.get('result'))
    assert status() == owner
    resume_before = protected()
    effects_before = sha(root / 'control/effects.jsonl')
    work_checkpoint = sha(home / 'terminal/work/compat.json')
    resumed = invoke(base)
    assert resumed['quick_connect']['status'] == 'connected'
    resumed_profile = json.loads((home / 'terminal/profiles/compat.json').read_text(encoding='utf-8'))
    assert resumed_profile['result']['binding'] == binding
    assert resumed_profile['selection']['project'] == saved['selection']['project']
    assert protected() == resume_before
    assert sha(root / 'control/effects.jsonl') == effects_before
    assert sha(home / 'terminal/work/compat.json') == work_checkpoint
    assert status() == owner
    invoke(['work', 'close', '--profile', profile, *service_args])
    (root / 'control' / ('cli-cycle-' + args.phase + '.json')).write_text(json.dumps({
        'owner': owner, 'binding': binding, 'decision_id': decision['decision_id'],
        'result_operation_id': sent['submission_turn_operation_id'], 'cli_commands': records,
        'no_web_step_required': args.phase == 's4-old',
        'limits': 'Actual installed CLI/foreground service; synthetic version/Test/native protocol peer, no provider.'}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
