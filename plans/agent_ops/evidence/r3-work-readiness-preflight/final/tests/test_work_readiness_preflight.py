"""Read-only preflight retries never authorize a changed owner or replay work."""
import json
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from okto_nexus.adapters.inbound.cli import work
from okto_nexus.adapters.outbound.service_manager import inspection


OWNER = dict(instance_id='svc_test', pid=123, generation='generation')
READY = dict(OWNER, state='ready', ready_for_queries=True)
TRANSIENT = dict(state='degraded', reason='SERVICE_UNREACHABLE',
                 ready_for_queries=False, observation_retryable=True, observed_owner=OWNER)


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(work, 'time', SimpleNamespace(
        monotonic=lambda: clock.now, sleep=lambda seconds: setattr(clock, 'now', clock.now + seconds)))
    return clock


def service_sequence(clock, sequence):
    calls = []
    def inspect(*, timeout):
        calls.append(timeout)
        elapsed, status = sequence.pop(0)
        clock.now += elapsed
        return status
    return SimpleNamespace(inspect=inspect, calls=calls)


@pytest.mark.parametrize('error,kind,retryable', [
    (TimeoutError('private'), 'transient_transport', True),
    (URLError(ConnectionRefusedError('private')), 'transient_transport', True),
    (URLError(ConnectionResetError('private')), 'transient_transport', True),
    (URLError('private'), 'unclassified_transport', False),
    (PermissionError('private'), 'unclassified_transport', False),
    (ValueError('private'), 'invalid_response', False),
    (AttributeError('private'), 'invalid_response', False),
    *[(HTTPError('private-url', code, 'private', {}, None), 'http_response', False)
      for code in (302, 401, 403, 404, 500, 503)],
])
def test_inspection_classifies_without_exposing_exception(tmp_path, monkeypatch, error, kind, retryable):
    monkeypatch.setattr(inspection, '_held', lambda _: True)
    (tmp_path / 'nexus.serve.lock').write_text(json.dumps(OWNER), encoding='utf-8')
    def fail(*_args, **_kwargs):
        raise error
    monkeypatch.setattr(inspection, 'build_opener', lambda *_: SimpleNamespace(open=fail))
    result = inspection.inspect_local_server(home=tmp_path, database=tmp_path / 'nexus.db', host='127.0.0.1', port=1)
    assert result['observation_error'] == kind
    assert result['observation_retryable'] is retryable
    assert result['observed_owner']['generation'] == OWNER['generation']
    assert result['generation'] is None and not result['ready_for_queries']
    assert 'private' not in json.dumps(result)


@pytest.mark.parametrize('metadata', [{}, {'pid': True, 'generation': 'x'},
    {'pid': 1, 'generation': 'secret\ntext'}, {'pid': 1, 'generation': 'x' * 129}])
def test_owner_hint_is_bounded_and_optional(metadata):
    assert inspection._owner_hint(metadata, 'svc_test') is None


def test_retry_uses_remaining_budget_and_same_canonical_owner(clock):
    service = service_sequence(clock, [(1.9, TRANSIENT), (.2, READY)])
    assert work.inspect_work_service(service, timeout=5) == READY
    assert service.calls == [2, 2]
    assert clock.now == pytest.approx(2.2)


@pytest.mark.parametrize('final', [dict(READY, generation='other'), dict(READY, pid=456),
    dict(READY, instance_id='other'), dict(TRANSIENT, observed_owner=dict(OWNER, generation='other'))])
def test_changed_owner_is_not_retried_or_admitted(clock, final):
    service = service_sequence(clock, [(0, TRANSIENT), (0, final)])
    result = work.inspect_work_service(service, timeout=2)
    assert result['reason'] == 'INSTANCE_CHANGED' and not result['ready_for_queries']
    assert len(service.calls) == 2


@pytest.mark.parametrize('status', [dict(TRANSIENT, observation_retryable=False),
    dict(TRANSIENT, observed_owner=None), dict(state='failed', reason='INSTANCE_MISMATCH'),
    dict(state='degraded', reason='VERSION_INCOMPATIBLE'), dict(state='stopped', reason='NO_SERVICE_OWNER')])
def test_nontransient_or_unanchored_failure_returns_without_retry(clock, status):
    service = service_sequence(clock, [(0, status)])
    assert work.inspect_work_service(service, timeout=2) == status
    assert len(service.calls) == 1


def test_positive_failure_after_transport_keeps_its_reason(clock):
    failure = dict(state='failed', reason='CONFIG_ERROR')
    service = service_sequence(clock, [(0, TRANSIENT), (0, failure)])
    assert work.inspect_work_service(service, timeout=2) == failure


@pytest.mark.parametrize('failure', [dict(state='failed', reason='INSTANCE_MISMATCH'),
    dict(state='degraded', reason='VERSION_INCOMPATIBLE'),
    dict(TRANSIENT, observation_retryable=False, observation_error='invalid_response')])
def test_late_positive_failure_preserves_diagnostic(clock, failure):
    service = service_sequence(clock, [(2.1, failure)])
    assert work.inspect_work_service(service, timeout=2) == dict(failure, readiness_wait_expired=True)


@pytest.mark.parametrize('elapsed,status', [(2, TRANSIENT), (2.1, READY)])
def test_late_io_does_not_admit_or_reset_deadline(clock, elapsed, status):
    service = service_sequence(clock, [(elapsed, status)])
    result = work.inspect_work_service(service, timeout=2)
    assert result['reason'] == 'READINESS_DEADLINE_EXCEEDED'
    assert not result['ready_for_queries'] and len(service.calls) == 1


def test_sleep_consumes_remaining_budget_without_another_read(clock):
    service = service_sequence(clock, [(1.95, TRANSIENT)])
    assert work.inspect_work_service(service, timeout=2)['reason'] == 'READINESS_DEADLINE_EXCEEDED'
    assert service.calls == [2] and clock.now == 2


def test_remote_verification_contract_is_not_retried(clock):
    calls = []
    def inspect():
        calls.append(True)
        return dict(state='failed', reason='AUTH_REQUIRED')
    service = SimpleNamespace(operator_http=object(), inspect=inspect)
    assert work.inspect_work_service(service, timeout=30)['reason'] == 'AUTH_REQUIRED'
    assert calls == [True]


@pytest.mark.parametrize('explicit', [False, True])
def test_slow_scheduler_is_not_a_new_default_deadline(clock, explicit):
    calls = []
    def inspect(**kwargs):
        calls.append(kwargs)
        # Healthy HTTP followed by a slow read-only native Scheduler query.
        clock.now += 3
        return READY
    service = SimpleNamespace(inspect=inspect)
    result = work.inspect_work_service(service, timeout=2 if explicit else None)
    assert calls == ([dict(timeout=2)] if explicit else [{}])
    assert result['state'] == ('unknown' if explicit else 'ready')


def test_default_transient_is_one_inspection_without_retry(clock):
    calls = []
    service = SimpleNamespace(inspect=lambda: (calls.append(True), TRANSIENT)[1])
    assert work.inspect_work_service(service) == TRANSIENT
    assert calls == [True] and clock.now == 0


@pytest.mark.parametrize('timeout', ['0', '-1', '30.1', 'nan', 'inf'])
def test_cli_rejects_invalid_readiness_budget_before_resolution(timeout, monkeypatch):
    monkeypatch.setattr(work, 'resolve_local_service', lambda *_: pytest.fail('resolved invalid selection'))
    with pytest.raises(SystemExit) as error:
        work.run_work(['status', '--readiness-timeout', timeout])
    assert error.value.code == 2


@pytest.mark.parametrize('action,final,expected,dispatches', [
    ('send', READY, 0, 1),
    ('send', dict(READY, state='stopping'), 3, 0),
    ('status', dict(READY, state='stopping'), 0, 0),
    ('interrupt', dict(READY, state='stopping'), 0, 1),
    ('send', dict(READY, generation='other'), 3, 0),
])
def test_cli_dispatch_once_only_after_readiness_and_existing_drain_policy(
        tmp_path, monkeypatch, clock, action, final, expected, dispatches):
    from okto_nexus.adapters.inbound.cli import terminal_target
    from okto_nexus.adapters.outbound.service_manager.locking import ExclusiveFileLock
    target = tmp_path / 'terminal/profiles/p.json'
    target.parent.mkdir(parents=True)
    target.write_text('{}', encoding='utf-8')
    service = service_sequence(clock, [(0, TRANSIENT), (0, final)])
    service.adapter = SimpleNamespace(home=tmp_path)
    monkeypatch.setattr(terminal_target, 'terminal_target_selection', lambda *_: (tmp_path, None))
    monkeypatch.setattr(terminal_target, 'resolve_terminal_target', lambda *_: service)
    sent, opened = [], []
    def submit(*args, **kwargs):
        sent.append((args, kwargs))
        return dict(state='completed')
    def open_flow(*_):
        opened.append(True)
        assert len(service.calls) == 2
        return SimpleNamespace(submit=submit, observe=lambda **_: dict(state='completed'))
    monkeypatch.setattr(work, 'open_work', open_flow)
    argv = [action, '--profile', 'p', '--json', '--readiness-timeout', '5']
    if action == 'send':
        argv += ['--message', 'synthetic']
    assert work.run_work(argv) == expected
    assert len(sent) == dispatches
    assert len(opened) == int(expected == 0)
    if opened:
        guard = ExclusiveFileLock(target.with_suffix('.guard'))
        guard.acquire()
        guard.release()
