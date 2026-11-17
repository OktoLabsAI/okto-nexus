"""Local path/disable/argv boundaries; canonical HTTP plus explicit synthetic setup."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import test_quick_connect_cli as fixtures

from okto_nexus.adapters.inbound.cli import connect, terminal_target

local_setup = fixtures.local_setup
checking = fixtures.checking
terminal = fixtures.terminal
quick_cli = fixtures.quick_cli
isolated_provider_environment = fixtures.isolated_provider_environment


def authority(c):
    tables = ('agents', 'execution_bindings', 'runtime_execution_grants', 'connection_setup_commits',
        'execution_sessions', 'execution_operations', 'agent_endpoints', 'connection_public_ids')
    with c.t.deps.connection_factory.unit_of_work(write=False) as uow:
        return {table: [{key: value for key, value in dict(row).items() if key != 'last_seen_at'}
            for row in uow.connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')] for table in tables}


def test_c12_removed_captured_directory_refuses_before_target_or_home_fallback(quick_cli, tmp_path, monkeypatch, capsys):
    c = quick_cli
    removed = tmp_path / 'captured-then-removed'
    removed.mkdir()
    assert removed.resolve().is_relative_to(tmp_path.resolve()) and Path.cwd() != removed
    removed.rmdir()  # Only this empty owned path; never the active Windows CWD.
    real_path = Path
    class PathPort:
        def __call__(self, *args, **kwargs):
            return real_path(*args, **kwargs)
        def cwd(self):
            return removed
    monkeypatch.setattr(connect, 'Path', PathPort())
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid captured CWD reached target/daemon resolution')
    monkeypatch.setattr(terminal_target, 'resolve_terminal_target', forbidden)
    monkeypatch.setattr(connect, 'resolve_local_service', forbidden)
    assert c.run(['connect', 'codex', '--profile', 'invalid-cwd', '--plan', '--json']) == 3
    value = json.loads(capsys.readouterr().out)
    assert value['state'] == 'refused' and value['code'] in ('CONFIG_ERROR', 'PROJECT_REQUIRED')
    assert isinstance(value['message'], str) and value['message']
    assert c.lifecycle == [] and not c.home.exists()
    assert c.t.turns == c.t.probes == []
    print('C12_DIAGNOSTIC ' + json.dumps({'code': value['code'], 'message': value['message']}))


def junction(link, target, own):
    assert os.name == 'nt'
    assert link.parent.resolve().is_relative_to(own.resolve())
    assert target.resolve().is_relative_to(own.resolve())
    assert not any(character in str(link) + str(target) for character in '&|<>^%!"')
    result = subprocess.run([str(Path('C:/Windows/System32/cmd.exe')), '/d', '/c', 'mklink', '/J', str(link), str(target)],
        cwd=own, stdin=subprocess.DEVNULL, capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        pytest.skip('Host cannot create an owned directory junction; return code ' + str(result.returncode))
    assert link.is_junction() and link.resolve(strict=True) == target.resolve(strict=True)


def test_c14_changed_junction_rejects_old_review_before_test_or_finish(quick_cli, tmp_path, capsys):
    if os.name != 'nt':
        pytest.skip('Windows junction scenario')
    c = quick_cli
    target_a, target_b, link = c.project, tmp_path / 'target-b', tmp_path / 'project-link'
    target_b.mkdir()
    marker_a, marker_b = target_a / 'keep-a.txt', target_b / 'keep-b.txt'
    marker_a.write_bytes(b'owned A data')
    marker_b.write_bytes(b'owned B data')
    junction(link, target_a, tmp_path)
    base = ['connect', 'codex', 'Linked Project', '--profile', 'linked', '--id', 'linked', '--project', str(link), '--json']
    review = fixtures.invoke(c, capsys, [*base, '--plan'])
    path = c.home / 'terminal/profiles/linked.json'
    before_bytes, before_db = path.read_bytes(), authority(c)
    assert review['selection']['project'] == str(target_a.resolve())
    assert link.parent.resolve() == tmp_path.resolve() and link.is_junction()
    assert link.resolve(strict=True) == target_a.resolve(strict=True)
    os.rmdir(link)  # Remove the verified reparse point only, never recursively.
    assert marker_a.read_bytes() == b'owned A data' and marker_b.read_bytes() == b'owned B data'
    junction(link, target_b, tmp_path)
    value = fixtures.invoke(c, capsys, [*base, '--approve', review['review_revision']], expected=3)
    assert value['state'] == 'refused' and value['code'] in ('PROFILE_CONFLICT', 'PROJECT_SELECTION_CHANGED', 'PROJECT_DIRECTORY_MISMATCH')
    assert path.read_bytes() == before_bytes and authority(c) == before_db
    assert c.t.turns == c.t.probes == []
    assert not any(method == 'POST' and route.endswith(('setup:test', 'setup:finish', 'public-ids/reserve')) for method, route in c.t.calls)
    assert marker_a.read_bytes() == b'owned A data' and marker_b.read_bytes() == b'owned B data'
    assert link.is_junction() and link.resolve(strict=True) == target_b.resolve(strict=True)


def test_f13_disabled_endpoint_id_stays_occupied_and_resume_is_not_connected(quick_cli, local_setup, capsys):
    c = quick_cli
    _, _, first = fixtures.first_connection(c, capsys, profile='first', name='Disabled Project', connect_id='disabled')
    reference = first['quick_connect']['canonical_reference']
    with c.t.deps.connection_factory.unit_of_work(write=False) as uow:
        revision = uow.connection.execute('SELECT revision FROM agent_endpoints WHERE endpoint_id=?', (reference['endpoint_id'],)).fetchone()[0]
    response = local_setup[2].patch('/api/v1/harness/endpoints/' + reference['endpoint_id'],
        headers=local_setup[3]['operator'], json={'expected_revision': revision, 'enabled': False})
    assert response.status_code == 200 and response.json()['data']['enabled'] is False
    before = authority(c)
    assert before['runtime_execution_grants'] and all(row['revoked_at'] for row in before['runtime_execution_grants'])
    row, = before['connection_public_ids']
    assert row['state'] == 'bound' and json.loads(row['canonical_ref_json']) == reference
    refused = fixtures.invoke(c, capsys, ['connect', 'codex', 'Disabled Project', '--profile', 'replacement',
        '--id', 'disabled', '--new-connection', '--json'], expected=3)
    assert refused['code'] == 'HARNESS_ID_ALREADY_EXISTS'
    resumed = fixtures.invoke(c, capsys, ['connect', '--profile', 'first', '--json'], expected=3)
    assert resumed['state'] != 'configured' and resumed.get('quick_connect', {}).get('status') != 'connected'
    assert authority(c) == before and len(c.t.turns) == len(c.t.probes) == 1


def test_h09_windows_json_resume_vector_roundtrip_without_a_shell(quick_cli, tmp_path, capsys):
    c = quick_cli
    name = 'Projeto Î© com espaÃ§os & echo INJECTED>H09_MARKER.txt & rem ^ % !'
    _, _, first = fixtures.first_connection(c, capsys, profile='argv', name=name)
    vector = first['quick_connect']['resume_argv']
    assert isinstance(vector, list) and all(isinstance(value, str) for value in vector)
    assert vector[3] == name
    wire = json.dumps(vector, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    loaded = json.loads(wire)
    echo = tmp_path / 'echo_argv.py'
    echo.write_text('import json,sys;sys.stdout.buffer.write(json.dumps(sys.argv[1:],ensure_ascii=False,separators=(",",":")).encode("utf-8"))', encoding='utf-8')
    cwd, temporary, home = tmp_path / 'echo-cwd', tmp_path / 'echo-tmp', tmp_path / 'echo-home'
    for path in (cwd, temporary, home):
        path.mkdir()
    env = {key: value for key, value in os.environ.items() if key.upper() in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE', 'PATHEXT')}
    env.update(TEMP=str(temporary), TMP=str(temporary), HOME=str(home), USERPROFILE=str(home), APPDATA=str(home), LOCALAPPDATA=str(home), PATH=str(home))
    before = authority(c)
    result = subprocess.run([sys.executable, '-I', '-B', str(echo), *loaded], cwd=cwd, env=env,
        input=b'', capture_output=True, shell=False, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0 and result.stderr == b''
    assert result.stdout == wire and json.loads(result.stdout) == vector
    assert not (cwd / 'H09_MARKER.txt').exists()
    assert authority(c) == before and len(c.t.turns) == len(c.t.probes) == 1
