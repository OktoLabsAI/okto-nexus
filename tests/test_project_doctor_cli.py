"""Doctor keeps local/remote ownership and credentials passive by default."""
import json
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.cli import doctor
from okto_nexus.application.project_diagnostics import DiagnosticReads, LEVELS
from okto_nexus.application.terminal_connection import ConnectionError


def fail(*args, **kwargs):
    pytest.fail('Unexpected diagnostic effect')


def remote_metadata(tmp_path):
    operator = tmp_path / 'terminal/operators/remote.json'
    operator.parent.mkdir(parents=True)
    operator.write_text(json.dumps(dict(format=1, origin='https://nexus.example',
        server_id='server-test', username='human')), encoding='utf-8')
    project = tmp_path / 'terminal/profiles/project.json'
    project.parent.mkdir(parents=True)
    project.write_text(json.dumps(dict(format=1, state='done', server_id='server-test',
        selection=dict(agent='subject', operator_profile='remote'))), encoding='utf-8')
    return {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}


def checks(capsys):
    report = json.loads(capsys.readouterr().out)
    assert tuple(row['id'] for row in report['checks']) == LEVELS
    assert all(row['reason'] and row['next_action'] for row in report['checks'])
    assert not any(report['effects'].values())
    return report, {row['id']: row for row in report['checks']}


def test_absent_instance_is_not_started_or_initialized(tmp_path, monkeypatch, capsys):
    import subprocess
    monkeypatch.setattr(subprocess, 'Popen', fail)
    monkeypatch.setattr(doctor, 'LocalOperatorHTTP', fail)
    home = tmp_path / 'absent'
    assert doctor.run_doctor(['--home', str(home), '--profile', 'project', '--check-server', '--json']) == 3
    report, rows = checks(capsys)
    assert report['topology'] == 'local_server'
    assert rows['local_service']['status'] == 'FAIL'
    assert rows['project_profile']['status'] == 'UNKNOWN'
    assert rows['work_result']['status'] == rows['mcp_negotiation']['status'] == 'UNKNOWN'
    assert not home.exists()


def test_remote_default_reads_metadata_without_vault_network_or_local_service(tmp_path, monkeypatch, capsys):
    before = remote_metadata(tmp_path)
    monkeypatch.setattr(doctor.OperatorProfile, 'client', fail)
    monkeypatch.setattr(doctor, 'resolve_local_service', fail)
    assert doctor.run_doctor(['--home', str(tmp_path), '--profile', 'project', '--json']) == 0
    report, rows = checks(capsys)
    assert report['topology'] == 'remote_operator' and report['state'] == 'incomplete'
    assert rows['local_service']['status'] == 'NOT_APPLICABLE'
    assert rows['operator_authentication']['status'] == rows['server_reachability']['status'] == 'UNKNOWN'
    assert {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()} == before


def test_ready_local_service_is_not_mistaken_for_authentication_or_work(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(doctor, 'resolve_local_service', lambda *a, **k: SimpleNamespace(inspect=lambda **kw: {
        'state': 'ready', 'installed_version': '0.3.3', 'active_version': '0.3.3'}))
    monkeypatch.setattr(doctor, 'LocalOperatorHTTP', fail)
    assert doctor.run_doctor(['--home', str(tmp_path), '--profile', 'project', '--json']) == 0
    _, rows = checks(capsys)
    assert rows['local_service']['status'] == rows['server_reachability']['status'] == 'PASS'
    assert rows['operator_authentication']['status'] == rows['work_result']['status'] == 'UNKNOWN'


@pytest.mark.parametrize('code,expected', [('SERVER_UNREACHABLE', 'UNKNOWN'), ('OPERATOR_LOGIN_REQUIRED', 'FAIL'),
                                         ('OPERATOR_VAULT_UNAVAILABLE', 'UNKNOWN')])
def test_remote_failure_never_uses_local_fallback_or_prints_remote_error_payload(tmp_path, monkeypatch, capsys, code, expected):
    before = remote_metadata(tmp_path)
    def unavailable(self):
        raise ConnectionError(code, 'nxs_hidden-token Cookie: hidden-session provider-password')
    monkeypatch.setattr(doctor.OperatorProfile, 'client', unavailable)
    monkeypatch.setattr(doctor, 'resolve_local_service', fail)
    result = doctor.run_doctor(['--home', str(tmp_path), '--profile', 'project', '--check-server', '--json'])
    assert result == (3 if expected == 'FAIL' else 0)
    raw = capsys.readouterr().out
    assert 'hidden' not in raw and 'provider-password' not in raw
    rows = {row['id']: row for row in json.loads(raw)['checks']}
    assert rows['operator_authentication']['status'] == expected
    assert rows['server_reachability']['status'] == 'UNKNOWN'
    assert {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()} == before


def test_corrupt_profile_is_a_failure_without_initializing_state(tmp_path, monkeypatch, capsys):
    remote_metadata(tmp_path)
    path = tmp_path / 'terminal/profiles/project.json'
    path.write_text('{malformed nxs_hidden', encoding='utf-8')
    monkeypatch.setattr(doctor, 'resolve_local_service', fail)
    assert doctor.run_doctor(['--home', str(tmp_path), '--profile', 'project', '--json']) == 3
    report, rows = checks(capsys)
    assert rows['project_profile']['code'] == 'PROFILE_INVALID'
    assert 'nxs_hidden' not in json.dumps(report)
    assert path.read_text(encoding='utf-8') == '{malformed nxs_hidden'


def test_diagnostic_transport_refuses_mutations_and_bounds_time_and_calls():
    now, calls = [10], []
    class Transport:
        timeout = 30
        def __call__(self, method, path):
            calls.append((method, path, self.timeout))
            return {}
    transport = Transport()
    read = DiagnosticReads(transport, timeout=4, max_calls=1, monotonic=lambda: now[0])
    with pytest.raises(ConnectionError, match='only read'):
        read('POST', '/api/v1/mutation', {})
    assert calls == []
    read('GET', '/api/v1/example')
    assert calls == [('GET', '/api/v1/example', 4)] and transport.timeout == 30
    with pytest.raises(ConnectionError) as limit:
        read('GET', '/api/v1/another')
    assert limit.value.code == 'DIAGNOSTIC_LIMIT'
    read = DiagnosticReads(transport, timeout=4, monotonic=lambda: now[0])
    now[0] = 15
    with pytest.raises(ConnectionError):
        read('GET', '/api/v1/expired')
    assert len(calls) == 1


@pytest.mark.parametrize('value', ['0', '-1', '31', 'nan', 'inf'])
def test_invalid_timeout_is_usage_error_without_effect(value, monkeypatch):
    monkeypatch.setattr(doctor, 'terminal_target_selection', fail)
    with pytest.raises(SystemExit) as result:
        doctor.run_doctor(['--timeout', value])
    assert result.value.code == 2
