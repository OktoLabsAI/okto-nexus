"""Initial setup and native registration checkpoints with disposable OS adapters."""
import json
import os
import time
from types import SimpleNamespace as NS

import pytest

import test_terminal_connect as terminal_fixtures
from test_service_start import make_adapter
from test_user_service_installation import FakeTasks
from okto_nexus.adapters.inbound.cli import connect, terminal_target
from okto_nexus.adapters.outbound.service_manager.context import read_json
from okto_nexus.adapters.outbound.service_manager.installation import ServerInstallation, SUPERVISOR
from okto_nexus.application.service_lifecycle import ServiceLifecycle

terminal = terminal_fixtures.terminal
checking = terminal_fixtures.checking
local_setup = terminal_fixtures.local_setup
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows login-task review; no POSIX qualification claim')


@pytest.fixture
def login(terminal, tmp_path, monkeypatch):
    t = terminal
    root = tmp_path / 'lifecycle-host'
    root.mkdir()
    adapter = make_adapter(root)
    tasks = FakeTasks()
    adapter.installation = ServerInstallation(adapter.home, adapter.database, tasks=tasks)
    process = dict(active=True, supervisor='detached', generation='first', drain=True)
    effects = []
    def inspect(**kwargs):
        return dict(state='ready' if process['active'] else 'stopped',
            generation=process['generation'] if process['active'] else None,
            supervisor=process['supervisor'], instance_id=adapter.installation.instance_id)
    def stop(before, **kwargs):
        effects.append('drain')
        if process['drain']:
            process['active'] = False
        return dict(before, state='stopping', shutdown=dict(state='DRAINED' if process['drain'] else 'UNCONFIRMED'))
    native_start = tasks.start
    def start(name, expected):
        native_start(name, expected)
        process.update(active=True, supervisor=SUPERVISOR, generation='supervised')
    tasks.start = start
    monkeypatch.setattr(adapter, '_inspect_process', inspect)
    monkeypatch.setattr(adapter, 'request_stop', stop)
    monkeypatch.setattr('okto_nexus.adapters.outbound.service_manager.local.subprocess.Popen',
        lambda *args, **kwargs: pytest.fail('Detached fallback or duplicate process'))
    service = ServiceLifecycle(adapter, monotonic=time.monotonic, sleep=time.sleep)
    monkeypatch.setattr(connect, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(connect, 'LocalOperatorHTTP', lambda **kwargs: t.call)
    args = ['--profile', 'project', '--agent', 'subject', '--project', t.selection['project'], '--json']
    return NS(t=t, service=service, adapter=adapter, tasks=tasks, process=process, effects=effects,
        args=args, path=adapter.home / 'terminal/profiles/project.json')


def plan(r, capsys, *flags):
    assert connect.run_connect([*r.args, '--plan', *flags]) == 0
    return json.loads(capsys.readouterr().out)


def apply(r, capsys, review, *flags):
    code = connect.run_connect([*r.args, '--approve', review['review_revision'], *flags])
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize('new_identity', [False, True])
def test_same_initial_review_covers_setup_and_user_login_transition(login, capsys, new_identity):
    r = login
    if new_identity:
        r.args = [value for value in r.args if value not in ('--agent', 'subject')]
        r.args += ['--new-agent', 'new-login-project']
    review = plan(r, capsys, '--start-at-login')
    choice = review['selection']['login_start']
    assert choice['action'] == 'install' and choice['scope']['home'] == str(r.adapter.home)
    assert 'context_digest' in choice['scope'] and 'environment' not in choice['scope']
    assert not r.effects and not r.tasks.calls and not r.t.turns
    code, result = apply(r, capsys, review)
    assert code == 0 and result['state'] == 'configured', result
    assert result['login_start']['operation_state'] == 'done'
    assert r.effects == ['drain']
    assert [call[0] for call in r.tasks.calls] == ['create', 'start']
    assert len(r.t.probes) == len(r.t.turns) == 1
    saved = read_json(r.path)
    assert saved['state'] == 'done' and saved['login_start_operation']['state'] == 'done'
    assert connect.run_connect(['--profile', 'project', '--json']) == 0
    capsys.readouterr()
    assert len(r.tasks.calls) == 2 and len(r.t.turns) == 1
    if new_identity:
        with r.t.deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute("SELECT COUNT(*) FROM agents WHERE agent_id='new-login-project'").fetchone()[0] == 1


def test_declining_login_keeps_on_demand_and_invalidates_only_unapproved_review(login, capsys):
    r = login
    original = plan(r, capsys, '--start-at-login')
    review = plan(r, capsys, '--no-start-at-login')
    assert 'login_start' not in review['selection']
    assert original['review_revision'] != review['review_revision']
    code, result = apply(r, capsys, review)
    assert code == 0 and result['state'] == 'configured'
    assert r.effects == r.tasks.calls == []
    assert len(r.t.turns) == 1


@pytest.mark.parametrize('failure', ['drain_timeout', 'checkpoint_loss'])
def test_partial_install_resumes_without_new_setup_or_model_test(login, capsys, monkeypatch, failure):
    r = login
    review = plan(r, capsys, '--start-at-login')
    if failure == 'drain_timeout':
        r.process['drain'] = False
    else:
        write = connect.atomic_json
        injected = False
        def fail_once(path, value):
            nonlocal injected
            if value.get('login_start_operation', {}).get('state') == 'installed' and not injected:
                injected = True
                raise OSError('Injected checkpoint response loss after native registration')
            return write(path, value)
        monkeypatch.setattr(connect, 'atomic_json', fail_once)
    code, result = apply(r, capsys, review, '--timeout', '.3')
    assert code == 3, result
    if failure == 'checkpoint_loss':
        assert result['possible_effect'] is True
    else:
        assert result['state'] == 'login_start_pending' and result['setup_state'] == 'configured'
    saved = read_json(r.path)
    assert saved['state'] == 'done' and saved['login_start_operation']['state'] == 'pending'
    run_id = saved['request']['client_intent_id']
    if failure == 'drain_timeout':
        before = list(r.effects)
        assert connect.run_connect(['--profile', 'project', '--agent', 'other', '--json']) == 3
        assert json.loads(capsys.readouterr().out)['code'] == 'PROFILE_CONFLICT'
        assert r.effects == before and not r.tasks.calls
    r.process['drain'] = True
    assert connect.run_connect(['--profile', 'project', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == 'configured' and result['login_start']['operation_state'] == 'done'
    assert read_json(r.path)['request']['client_intent_id'] == run_id
    assert len(r.t.probes) == len(r.t.turns) == 1
    assert [call[0] for call in r.tasks.calls] == ['create', 'start']
    with r.t.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_execution_grants').fetchone()[0] == 1


def test_changed_context_refuses_before_test_or_drain(login, capsys, tmp_path):
    r = login
    review = plan(r, capsys, '--start-at-login')
    r.adapter.context = dict(r.adapter.context, cwd=str(tmp_path))
    code, result = apply(r, capsys, review)
    assert code == 3 and result['code'] == 'LOGIN_START_REVIEW_CHANGED'
    assert not r.t.turns and not r.effects and not r.tasks.calls


def test_existing_connection_can_review_startup_without_reapplying_setup(login, capsys):
    r = login
    first = plan(r, capsys)
    assert apply(r, capsys, first)[0] == 0
    before = read_json(r.path)['request']
    review = plan(r, capsys, '--start-at-login')
    assert review['state'] == 'login_start_review' and not r.tasks.calls
    declined = plan(r, capsys, '--no-start-at-login')
    assert declined['state'] == 'configured' and not r.tasks.calls
    review = plan(r, capsys, '--start-at-login')
    assert apply(r, capsys, review)[0] == 0
    assert read_json(r.path)['request'] == before
    assert len(r.t.turns) == 1
    # A later disable is deliberate. Reconnect cannot restore enablement.
    assert r.service.disable_user_service()['enablement_confirmed']
    assert connect.run_connect(['--profile', 'project', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['login_start']['current_user_service']['enabled'] is False
    assert [call for call in r.tasks.calls if call[0] == 'enabled'] == [('enabled', r.adapter.installation.name, False)]


def test_disabled_existing_task_is_enabled_only_by_exact_new_review(login, capsys):
    r = login
    r.process['active'] = False
    assert r.service.install_user_service()['installation_state'] == 'installed'
    assert r.service.disable_user_service()['enablement_confirmed']
    # Existing running instance with its installed but disabled task.
    r.process.update(active=True, supervisor=SUPERVISOR)
    review = plan(r, capsys, '--start-at-login')
    assert review['selection']['login_start']['action'] == 'enable'
    code, result = apply(r, capsys, review)
    assert code == 0, result
    assert result['login_start']['current_user_service']['enabled']
    assert not r.effects and [c[0] for c in r.tasks.calls].count('create') == 1


def test_remote_operator_option_never_resolves_local_startup(monkeypatch, tmp_path, capsys):
    service = NS(operator_profile='remote', adapter=NS(home=tmp_path),
        ensure_running=lambda **kwargs: pytest.fail('Startup before topology rejection'))
    monkeypatch.setattr(terminal_target, 'resolve_terminal_target', lambda *args: service)
    assert connect.run_connect(['--profile', 'remote', '--project', str(tmp_path),
        '--operator-profile', 'remote', '--start-at-login', '--json']) == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'REMOTE_STARTUP_NOT_LOCAL'
    assert not (tmp_path / 'terminal').exists()
