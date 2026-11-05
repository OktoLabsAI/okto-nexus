from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from unittest.mock import Mock
import threading
import time

import pytest

from okto_nexus.adapters.inbound.cli.service import run_service
from okto_nexus.adapters.outbound.service_manager.context import atomic_json, execution_context, read_json
from okto_nexus.adapters.outbound.service_manager.local import LocalServerLifecycle, launch_exclusion
from okto_nexus.application.service_lifecycle import ServiceLifecycle
from okto_nexus.bootstrap.local_discovery import LocalDiscoveryConfiguration
from okto_nexus.config import load_config


def make_adapter(tmp_path):
    home = tmp_path / 'home'
    config = load_config({}, ['--home', str(home), '--embedding-mode', 'off', '--trust-mode', 'strict'])
    context = execution_context(config, host='127.0.0.1', port=32123,
        project_root=tmp_path, log_level='warning', discovery=LocalDiscoveryConfiguration(), env=os.environ)
    return LocalServerLifecycle(home=home, database=home / 'nexus.db',
        host='127.0.0.1', port=32123, context=context)


def test_background_context_retains_resolved_settings_without_terminal_secrets(tmp_path):
    env = {**os.environ, 'OPENAI_API_KEY': 'secret-sentinel', 'PYTHONPATH': 'injected',
           'ARBITRARY_SETTING': 'not-copied', 'OKTO_NEXUS_HOME': str(tmp_path / 'home'),
           'OKTO_NEXUS_TRUST_MODE': 'strict'}
    config = load_config(env, ['--embedding-mode', 'off'])
    context = execution_context(config, host='127.0.0.1', port=32123,
        project_root=tmp_path, log_level='warning', discovery=LocalDiscoveryConfiguration(), env=env)
    assert 'secret-sentinel' not in json.dumps(context)
    assert not {'OPENAI_API_KEY', 'PYTHONPATH', 'ARBITRARY_SETTING'} & context['environment'].keys()
    assert context['executable'] == str(Path(sys.executable).absolute())
    assert context['cwd'] == str(tmp_path.resolve())
    assert context['arguments'][context['arguments'].index('--trust-mode') + 1] == 'strict'
    assert context['arguments'][context['arguments'].index('--home') + 1] == str(config.home_dir.resolve())


def test_pending_launch_is_not_repeated_and_uses_detached_non_shell_entrypoint(tmp_path, monkeypatch):
    adapter = make_adapter(tmp_path)
    spawn = Mock(return_value=Mock(pid=os.getpid()))
    monkeypatch.setattr('okto_nexus.adapters.outbound.service_manager.local.subprocess.Popen', spawn)
    first = adapter.start()
    receipt = read_json(adapter.home / 'service-launch.json')
    second = adapter.start()
    assert first['state'] == second['state'] == 'starting'
    assert read_json(adapter.home / 'service-launch.json') == receipt
    spawn.assert_called_once()
    command = spawn.call_args.args[0]
    options = spawn.call_args.kwargs
    assert command[0] == str(Path(sys.executable).absolute())
    assert command[2] == 'okto_nexus.adapters.inbound.cli.service_process'
    assert not options.get('shell') and options['close_fds']
    assert options['stdin'] == options['stdout'] == options['stderr'] == -3
    assert options['creationflags'] if os.name == 'nt' else options['start_new_session']


def test_saved_context_distinguishes_frozen_defaults_from_explicit_policy(tmp_path, monkeypatch):
    from okto_nexus.adapters.inbound.cli.service import resolve_local_service
    adapter = make_adapter(tmp_path)
    adapter.home.mkdir()
    atomic_json(adapter.home / 'service-context.json', adapter.context)
    assert 'feature_hitl' not in adapter.context['settings_pinned_fields']
    assert 'embedding_mode' in adapter.context['settings_pinned_fields']  # Explicit default.
    monkeypatch.setenv('OKTO_NEXUS_FEATURE_HITL', 'true')
    reused = resolve_local_service(['--home', str(adapter.home)])
    assert reused.adapter.context['settings_pinned_fields'] == adapter.context['settings_pinned_fields']
    args = reused.adapter.context['arguments']
    assert args[args.index('--feature-hitl') + 1] == 'false'
    selected = resolve_local_service(['--home', str(adapter.home), '--feature-hitl', 'false'])
    assert 'feature_hitl' in selected.adapter.context['settings_pinned_fields']
    assert read_json(adapter.home / 'service-context.json') == adapter.context


def test_existing_service_is_reused_without_spawn_or_rewrite(tmp_path, monkeypatch):
    adapter = make_adapter(tmp_path)
    adapter.home.mkdir()
    ready = {'state': 'ready', 'generation': 'same', 'instance_id': 'svc_existing'}
    monkeypatch.setattr(adapter, 'inspect', lambda **_: ready)
    spawn = Mock(side_effect=AssertionError('Duplicate launch'))
    monkeypatch.setattr('okto_nexus.adapters.outbound.service_manager.local.subprocess.Popen', spawn)
    assert adapter.start() == ready
    assert not (adapter.home / 'service-context.json').exists()
    assert not spawn.called


def test_concurrent_start_waits_on_exclusion_without_spawn(tmp_path, monkeypatch):
    adapter = make_adapter(tmp_path)
    adapter.home.mkdir()
    spawn = Mock(side_effect=AssertionError('Duplicate launch'))
    monkeypatch.setattr('okto_nexus.adapters.outbound.service_manager.local.subprocess.Popen', spawn)
    with launch_exclusion(adapter.home, adapter.database):
        result = adapter.start()
    assert result['reason'] == 'CONCURRENT_START'
    assert not spawn.called


def test_status_waits_while_another_cli_prepares_before_launch_receipt(tmp_path):
    adapter = make_adapter(tmp_path)
    adapter.home.mkdir()
    with launch_exclusion(adapter.home, adapter.database):
        assert not (adapter.home / 'service-launch.json').exists()
        result = adapter.inspect()
        assert result['state'] == 'starting' and result['reason'] == 'CONCURRENT_START'


@pytest.mark.skipif(os.name != 'nt', reason='Windows CRT read handle denies DELETE sharing')
def test_receipt_write_survives_a_real_concurrent_windows_reader(tmp_path):
    path = tmp_path / 'service-launch.json'
    atomic_json(path, {'state': 'pending'})
    reader = path.open('r', encoding='utf-8')
    def close_reader():
        time.sleep(.05)
        reader.close()
    closer = threading.Thread(target=close_reader)
    closer.start()
    try:
        atomic_json(path, {'state': 'owned'})
    finally:
        closer.join(timeout=2)
        reader.close()
    assert read_json(path)['state'] == 'owned'
    assert not list(tmp_path.glob('.service-*'))


@pytest.mark.skipif(os.name != 'nt', reason='Windows replacement retry budget')
def test_persistent_receipt_write_failure_is_bounded_and_preserves_previous_state(tmp_path, monkeypatch):
    path = tmp_path / 'service-launch.json'
    atomic_json(path, {'state': 'pending'})
    error = PermissionError('persistent refusal')
    error.winerror = 5
    replace = Mock(side_effect=error)
    ticks = iter([0, 2])
    monkeypatch.setattr('okto_nexus.adapters.outbound.service_manager.context.os.replace', replace)
    monkeypatch.setattr('okto_nexus.adapters.outbound.service_manager.context.time.monotonic', lambda: next(ticks))
    with pytest.raises(PermissionError):
        atomic_json(path, {'state': 'owned'})
    replace.assert_called_once()
    assert read_json(path)['state'] == 'pending'
    assert not list(tmp_path.glob('.service-*'))


def test_installed_supervisor_never_falls_back_to_detached(tmp_path, monkeypatch):
    adapter = make_adapter(tmp_path)
    adapter.home.mkdir()
    (adapter.home / 'service-installation.json').write_text('{}')
    spawn = Mock(side_effect=AssertionError('Detached fallback'))
    monkeypatch.setattr('okto_nexus.adapters.outbound.service_manager.local.subprocess.Popen', spawn)
    assert adapter.start()['reason'] == 'INSTALLATION_RECEIPT_INVALID'
    assert not spawn.called


@pytest.mark.parametrize('state,reason', [('stopping', 'RUNTIME_DRAINING'),
    ('failed', 'INSTANCE_MISMATCH'), ('degraded', 'VERSION_INCOMPATIBLE')])
def test_facade_never_retries_failed_or_stopping_service(state, reason):
    adapter = Mock()
    adapter.start.return_value = {'state': state, 'reason': reason}
    service = ServiceLifecycle(adapter, monotonic=lambda: 0, sleep=Mock())
    assert service.ensure_running(timeout=1) == adapter.start.return_value
    adapter.start.assert_called_once()
    adapter.inspect.assert_not_called()


@pytest.mark.parametrize('initial', [
    {'state': 'starting', 'reason': 'STARTUP_PENDING'},
    {'state': 'unknown', 'reason': 'INSTANCE_METADATA_UNAVAILABLE'},
])
def test_wait_timeout_leaves_one_launch_intact_and_recovers_by_inspection(initial):
    adapter = Mock()
    adapter.start.return_value = adapter.inspect.return_value = initial
    ticks = iter([0, 0, 2, 2])
    service = ServiceLifecycle(adapter, monotonic=lambda: next(ticks), sleep=Mock())
    result = service.ensure_running(timeout=1)
    assert result['wait_timed_out'] and result['state'] == initial['state']
    assert result['reason'] == initial['reason']
    adapter.start.assert_called_once()
    adapter.stop.assert_not_called()
    adapter.inspect.return_value = {'state': 'ready', 'generation': 'same-launch'}
    assert service.inspect()['generation'] == 'same-launch'


def test_transient_metadata_failure_waits_for_current_owner_without_another_start():
    adapter = Mock()
    adapter.start.return_value = {'state': 'unknown', 'reason': 'INSTANCE_METADATA_UNAVAILABLE'}
    adapter.inspect.return_value = {'state': 'ready', 'generation': 'same-launch'}
    service = ServiceLifecycle(adapter, monotonic=lambda: 0, sleep=Mock())
    assert service.ensure_running(timeout=1)['generation'] == 'same-launch'
    adapter.start.assert_called_once()
    adapter.inspect.assert_called_once()
    adapter.request_stop.assert_not_called()


def test_saved_context_selects_same_endpoint_without_repeating_flags(tmp_path, monkeypatch, capsys):
    adapter = make_adapter(tmp_path)
    monkeypatch.setattr('okto_nexus.adapters.outbound.service_manager.local.subprocess.Popen', Mock(return_value=Mock(pid=os.getpid())))
    adapter.start()
    assert run_service(['status', '--home', str(adapter.home), '--json']) == 3
    result = json.loads(capsys.readouterr().out)
    assert result['effective_configuration']['port'] == adapter.port
    assert result['effective_configuration']['bind_host'] == adapter.host
    assert result['reason'] == 'STARTUP_PENDING'


def test_restart_does_not_start_when_drain_is_pending():
    adapter = Mock()
    adapter.inspect.return_value = {'state': 'stopping', 'generation': 'g', 'reason': 'RUNTIME_DRAINING'}
    adapter.request_stop.return_value = {**adapter.inspect.return_value,
        'shutdown': {'state': 'DRAINING_PENDING', 'resources': [{'session_id': 'existing'}]}}
    ticks = iter([0, 0, 2])
    service = ServiceLifecycle(adapter, monotonic=lambda: next(ticks), sleep=Mock())
    assert service.restart(timeout=1)['wait_timed_out']
    adapter.start.assert_not_called()


def test_lost_shutdown_response_is_recovered_by_correlated_durable_receipt():
    adapter = Mock()
    adapter.inspect.side_effect = [{'state': 'ready', 'generation': 'g'}, {'state': 'stopped'}]
    adapter.request_stop.return_value = {'state': 'stopping', 'shutdown': {'state': 'UNCONFIRMED'}}
    adapter.shutdown_receipt.return_value = 'DRAINED'
    service = ServiceLifecycle(adapter, monotonic=lambda: 0, sleep=Mock())
    assert service.stop(timeout=1)['shutdown_outcome'] == 'drained'
    adapter.shutdown_receipt.assert_called_once_with('g')


def test_unconfirmed_exit_does_not_authorize_restart():
    adapter = Mock()
    adapter.inspect.side_effect = [{'state': 'ready', 'generation': 'g'}, {'state': 'stopped'}]
    adapter.request_stop.return_value = {'state': 'stopping', 'shutdown': {'state': 'UNCONFIRMED'}}
    adapter.shutdown_receipt.return_value = None
    service = ServiceLifecycle(adapter, monotonic=lambda: 0, sleep=Mock())
    result = service.restart(timeout=1)
    assert result['shutdown_outcome'] == 'unconfirmed'
    adapter.start.assert_not_called()
