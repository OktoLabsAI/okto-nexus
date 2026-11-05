"""Passive lifecycle diagnostics, including bounded corrupt/rotated input."""
from __future__ import annotations

from argparse import Namespace
import json
from unittest.mock import Mock

import pytest

from okto_nexus.adapters.inbound.cli.service import run_service, _show_logs
from okto_nexus.adapters.outbound.service_manager import logs
from okto_nexus.application.service_lifecycle import ServiceLifecycle


def writer(home, **kwargs):
    return logs.ServiceLog(home, generation='a' * 32, supervisor='detached', **kwargs)


def test_absent_logs_are_passive_and_do_not_require_saved_python(tmp_path, monkeypatch, capsys):
    import subprocess
    from okto_nexus.adapters.outbound.service_manager.local import LocalServerLifecycle
    monkeypatch.setattr(subprocess, 'Popen', Mock(side_effect=AssertionError('spawn')))
    monkeypatch.setattr(LocalServerLifecycle, 'inspect', Mock(side_effect=AssertionError('inspect')))
    home = tmp_path / 'absent'
    assert run_service(['logs', '--home', str(home), '--json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['reason'] == 'LOG_NOT_FOUND'
    assert report['service_state'] == report['work_state'] == 'not_checked'
    assert not home.exists()
    home.mkdir()
    (home / 'service-context.json').write_text('{invalid context')
    assert run_service(['logs', '--home', str(home), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['reason'] == 'LOG_NOT_FOUND'


def test_tail_and_json_expose_only_coded_records(tmp_path, capsys):
    log = writer(tmp_path)
    try:
        log.write('STARTING', state='STARTING')
        log.write('BOOTSTRAP_FAILED', error_code='CONFIG_ERROR')
        log.write('nxs_secret_value', error_code='password=sentinel')
        log.write('SERVICE_EXIT', state='DRAINED')
    finally:
        log.close()
    assert run_service(['logs', '--home', str(tmp_path), '--tail', '2', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert [event['code'] for event in result['events']] == ['BOOTSTRAP_FAILED', 'SERVICE_EXIT']
    assert result['events'][0]['error_code'] == 'CONFIG_ERROR' and result['truncated']
    assert 'sentinel' not in (tmp_path / 'logs' / logs.LOG_NAME).read_text()
    assert 'nxs_' not in (tmp_path / 'logs' / logs.LOG_NAME).read_text()


def test_corrupt_or_secret_bearing_lines_are_withheld(tmp_path):
    log = writer(tmp_path)
    log.write('STARTING', state='STARTING')
    log.close()
    path = tmp_path / 'logs' / logs.LOG_NAME
    valid = json.loads(path.read_text())
    with path.open('ab') as stream:
        stream.write(b'Authorization: Bearer private-value\n')
        stream.write(json.dumps({**valid, 'message': 'provider-key-sentinel'}).encode() + b'\n')
        stream.write(json.dumps({**valid, 'generation': 'private-value'}).encode() + b'\n')
        stream.write(json.dumps({**valid, 'code': ['malformed']}).encode() + b'\n')
    result, _ = logs.read_logs(tmp_path)
    assert len(result['events']) == 1 and result['discarded_records'] == 4
    assert result['reason'] == 'LOG_RECORDS_WITHHELD'
    assert 'private-value' not in json.dumps(result)
    assert 'provider-key-sentinel' not in json.dumps(result)


def test_follow_consumes_append_once_and_reopens_after_rotation(tmp_path):
    log = writer(tmp_path)
    log.write('STARTING', state='STARTING')
    first, cursor = logs.read_logs(tmp_path)
    assert len(first['events']) == 1
    assert logs.read_logs(tmp_path, cursor=cursor)[0]['events'] == []
    log.write('READY_FOR_QUERIES', state='READY')
    second, cursor = logs.read_logs(tmp_path, cursor=cursor)
    assert [item['code'] for item in second['events']] == ['READY_FOR_QUERIES']
    log.handler.doRollover()
    log.write('SERVICE_EXIT', state='DRAINED')
    log.close()
    rotated, _ = logs.read_logs(tmp_path, cursor=cursor)
    assert rotated['rotated']
    assert [item['code'] for item in rotated['events']] == ['SERVICE_EXIT']


def test_partial_record_is_not_emitted_until_completed(tmp_path):
    log = writer(tmp_path)
    log.write('STARTING')
    log.close()
    path = tmp_path / 'logs' / logs.LOG_NAME
    record = path.read_bytes()
    path.write_bytes(record[:40])
    partial, cursor = logs.read_logs(tmp_path)
    assert partial['events'] == [] and partial['discarded_records'] == 0
    with path.open('ab') as stream:
        stream.write(record[40:])
    full, cursor = logs.read_logs(tmp_path, cursor=cursor)
    assert len(full['events']) == 1
    assert logs.read_logs(tmp_path, cursor=cursor)[0]['events'] == []


def test_read_and_retention_are_bounded(tmp_path):
    log = writer(tmp_path, max_bytes=800)
    for _ in range(40):
        log.write('STARTING', state='STARTING')
    log.close()
    assert len(list((tmp_path / 'logs').glob('service.jsonl*'))) == 4
    assert all(p.stat().st_size < 800 for p in (tmp_path / 'logs').iterdir())
    path = tmp_path / 'logs' / logs.LOG_NAME
    path.write_bytes(b'x' * (logs.MAX_READ * 3) + b'\n')
    result, cursor = logs.read_logs(tmp_path)
    assert result['truncated'] and result['events'] == []
    assert len(cursor.pending) <= logs.MAX_RECORD + 1


def test_unavailable_log_is_not_inferred_as_stopped(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(logs, '_directory', Mock(side_effect=PermissionError('private-sentinel')))
    assert run_service(['logs', '--home', str(tmp_path), '--json']) == 3
    result = json.loads(capsys.readouterr().out)
    assert result['reason'] == 'LOG_UNAVAILABLE' and result['service_state'] == 'not_checked'
    assert 'private-sentinel' not in json.dumps(result)


def test_ctrl_c_ends_follow_without_lifecycle_mutation(tmp_path, capsys):
    adapter = Mock()
    adapter.logs.side_effect = lambda **kw: logs.read_logs(tmp_path, **kw)
    service = ServiceLifecycle(adapter, monotonic=lambda: 0, sleep=Mock(side_effect=KeyboardInterrupt))
    assert _show_logs(service, Namespace(tail=50, follow=True, json=True)) == 130
    assert json.loads(capsys.readouterr().out)['reason'] == 'LOG_NOT_FOUND'
    assert [call[0] for call in adapter.mock_calls] == ['logs']


def test_log_write_failure_is_bounded_and_does_not_emit_raw_error(tmp_path, monkeypatch, capsys):
    log = writer(tmp_path, max_bytes=1)
    log.write('STARTING')  # rotation intentionally skips an empty file
    monkeypatch.setattr(log.handler, 'doRollover', Mock(side_effect=OSError('private-sentinel')))
    try:
        log.write('STARTING', error_code={'untrusted': 'private-sentinel'})
        assert log.handler.failed
    finally:
        log.close()
    log.write('SERVICE_EXIT')  # a late readiness thread cannot reopen the file
    assert log.handler.stream is None
    assert 'private-sentinel' not in capsys.readouterr().err


@pytest.mark.parametrize('args', [['logs', '--tail', '0'], ['logs', '--tail', '10001'], ['status', '--follow']])
def test_log_flags_are_bounded_and_scoped(args):
    with pytest.raises(SystemExit) as exit_info:
        run_service(args)
    assert exit_info.value.code == 2
