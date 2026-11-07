"""CLI format selection with synthetic reports and forbidden external effects."""
import json
from types import SimpleNamespace

import pytest

from okto_nexus.adapters.inbound.cli import doctor, participant_doctor


def forbid(*args, **kwargs):
    pytest.fail('Unexpected external diagnostic effect')


def managed(monkeypatch, tmp_path, state='ready'):
    calls = []
    monkeypatch.setattr(doctor, 'project_profile', lambda *args: ('synthetic-project', 'synthetic-profile'))
    monkeypatch.setattr(doctor, 'terminal_target_selection', lambda *args: (tmp_path, None))
    monkeypatch.setattr(doctor, '_profile', lambda *args: None)
    def inspect(**kwargs):
        calls.append(('inspect', kwargs))
        return dict(state=state, installed_version='0.3.3', active_version='0.3.3')
    monkeypatch.setattr(doctor, 'resolve_local_service', lambda *args, **kwargs: SimpleNamespace(inspect=inspect))
    monkeypatch.setattr(doctor, 'LocalOperatorHTTP', forbid)
    monkeypatch.setattr(doctor.OperatorProfile, 'client', forbid)
    return calls


@pytest.mark.parametrize('state,exit_code', [('ready', 0), ('unknown', 0), ('failed', 3)])
def test_managed_legacy_shape_and_exit_are_unchanged(monkeypatch, tmp_path, capsys, state, exit_code):
    calls = managed(monkeypatch, tmp_path, state)
    assert doctor.run_doctor(['--json']) == exit_code
    default = capsys.readouterr().out
    assert doctor.run_doctor(['--json', '--diagnostic-format', 'legacy']) == exit_code
    assert capsys.readouterr().out == default
    assert len(calls) == 2 and calls[0] == calls[1]
    result = json.loads(default)
    assert set(result) == {'format_version', 'profile', 'topology', 'state', 'checks', 'counts', 'effects'}
    assert all('subject' not in row and 'severity' not in row for row in result['checks'])
    assert doctor.run_doctor(['--json', '--diagnostic-format', 'v1']) == exit_code
    common = json.loads(capsys.readouterr().out)
    assert common['counts'] == result['counts'] and common['effects'] == result['effects']
    assert common['component'] == 'nexus' and common['scope'] == 'managed_project'
    assert common['mode'] == 'passive' and len(calls) == 3
    if state == 'failed':
        row = next(check for check in common['checks'] if check['id'] == 'local_service')
        assert row['code'] == 'SERVICE_NOT_READY'


def test_legacy_text_output_is_unchanged(monkeypatch, tmp_path, capsys):
    managed(monkeypatch, tmp_path)
    assert doctor.run_doctor([]) == 0
    default = capsys.readouterr().out
    assert doctor.run_doctor(['--diagnostic-format', 'legacy']) == 0
    assert capsys.readouterr().out == default


@pytest.mark.parametrize('mode', ['managed', 'participant'])
@pytest.mark.parametrize('format_value', ['v2', '', 'V1'])
def test_bad_selector_is_usage_error_before_any_effect(monkeypatch, mode, format_value):
    monkeypatch.setattr(doctor, 'project_profile', forbid)
    monkeypatch.setattr(participant_doctor, 'project_profile', forbid)
    with pytest.raises(SystemExit) as error:
        doctor.run_doctor(['--mode', mode, '--diagnostic-format', format_value])
    assert error.value.code == 2


@pytest.mark.parametrize('flags', [[], ['--check-server'], ['--check-mcp'], ['--check-environment']])
def test_participant_selection_preserves_explicit_flags_and_observed_effects(monkeypatch, tmp_path, capsys, flags):
    home = tmp_path / 'isolated'
    profile = home / 'terminal/participants/synthetic-profile.json'
    profile.parent.mkdir(parents=True)
    profile.write_text('{}', encoding='utf-8')
    before = profile.read_bytes()
    monkeypatch.setattr(participant_doctor, 'project_profile', lambda *args: ('synthetic-project', 'synthetic-profile'))
    monkeypatch.setattr(participant_doctor, '_check_private', lambda *args: None)
    monkeypatch.setattr(participant_doctor, 'read_json', lambda *args: {})
    calls = []
    def inspect(report, *args, **kwargs):
        calls.append({k: kwargs[k] for k in ('check_server', 'check_mcp', 'check_environment')})
        report.credential_read = kwargs['check_server'] or kwargs['check_mcp'] or kwargs['check_environment']
        report.mcp_checked = kwargs['check_mcp']
    monkeypatch.setattr(participant_doctor, 'inspect_participant', inspect)
    args = ['--mode', 'participant', '--profile', 'synthetic-profile', '--home', str(home), '--json'] + flags
    assert doctor.run_doctor(args) == 0
    legacy = capsys.readouterr().out
    assert doctor.run_doctor(args + ['--diagnostic-format', 'legacy']) == 0
    assert capsys.readouterr().out == legacy
    assert doctor.run_doctor(args + ['--diagnostic-format', 'v1']) == 0
    common = json.loads(capsys.readouterr().out)
    assert common['scope'] == 'participant'
    assert common['mode'] == ('explicit_checks' if flags else 'passive')
    assert common['effects'] == json.loads(legacy)['effects']
    assert calls[0] == calls[1] == calls[2]
    assert profile.read_bytes() == before


def test_requested_participant_check_not_executed_is_not_an_effect(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(participant_doctor, 'project_profile', lambda *args: ('synthetic-project', 'synthetic-profile'))
    monkeypatch.setattr(participant_doctor, 'inspect_participant', forbid)
    missing = tmp_path / 'missing'
    assert doctor.run_doctor(['--mode', 'participant', '--profile', 'synthetic-profile', '--home', str(missing),
        '--check-mcp', '--json', '--diagnostic-format', 'v1']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['mode'] == 'explicit_checks' and not any(report['effects'].values())
    assert not missing.exists()


@pytest.mark.parametrize('mode', ['managed', 'participant'])
@pytest.mark.parametrize('format_value', ['legacy', 'v1'])
def test_interrupt_exit_is_unchanged(monkeypatch, mode, format_value):
    def interrupted(*args):
        raise KeyboardInterrupt()
    monkeypatch.setattr(doctor, 'project_profile', interrupted)
    monkeypatch.setattr(participant_doctor, 'project_profile', interrupted)
    assert doctor.run_doctor(['--mode', mode, '--diagnostic-format', format_value]) == 130
