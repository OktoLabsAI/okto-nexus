"""T-CLI-12 scripted CLI + canonical ASGI/SQLite, inert lifecycle and peer.

No Server process, provider, actual version execution or personal login is used.
"""
from collections import Counter
import json
from types import SimpleNamespace

from test_terminal_multi_harness import terminal as terminal, checking as checking, local_setup as local_setup
from test_connection_setup_recovery import snapshot
from okto_nexus.adapters.inbound.cli import connect
from okto_nexus.adapters.outbound.service_manager.context import read_json


def test_scripted_new_connection_exact_review_recovers_lost_finish_without_replay(
        request, tmp_path, monkeypatch, capsys):
    t = request.getfixturevalue('terminal')
    home = tmp_path / 'scripted-cli-home'
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=1),
        inspect=lambda: dict(state='ready', instance_id='synthetic-scripted-instance'),
        ensure_running=lambda **kwargs: dict(state='ready', instance_id='synthetic-scripted-instance'))
    monkeypatch.setattr(connect, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(connect, 'LocalOperatorHTTP', lambda **kwargs: t.call)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: False))

    def forbidden_input(*args, **kwargs):
        raise AssertionError('Scripted CLI must never prompt')

    monkeypatch.setattr('builtins.input', forbidden_input)
    def identities():
        with t.deps.connection_factory.unit_of_work(write=False) as uow:
            return tuple(row[0] for row in uow.connection.execute('SELECT agent_id FROM agents ORDER BY agent_id'))
    command = ['--home', str(home), '--new-connection', '--profile', 'stable-scripted',
        '--client', 'codex', '--project', t.selection['project'], '--json', '--no-chat']
    before = snapshot(t.deps)
    before_identities = identities()
    assert connect.run_connect(command + ['--plan']) == 0
    review = json.loads(capsys.readouterr().out)
    assert review['state'] == 'review'
    path = home / 'terminal/profiles/stable-scripted.json'
    retained = read_json(path)
    assert retained['review_revision'] == review['review_revision']
    assert retained['selection']['client'] == 'codex'
    assert retained['selection']['create_agent'] is True
    assert snapshot(t.deps) == before and t.turns == t.probes == []
    assert identities() == before_identities

    # Changed content cannot repurpose the reserved profile before any Test.
    profile_bytes = path.read_bytes()
    assert connect.run_connect(command + ['--name', 'Different identity', '--plan']) == 3
    conflict = json.loads(capsys.readouterr().out)
    assert conflict['state'] == 'refused' and conflict['code'] == 'PROFILE_CONFLICT'
    assert path.read_bytes() == profile_bytes and snapshot(t.deps) == before
    assert identities() == before_identities
    assert t.turns == t.probes == []

    approval = command + ['--approve', review['review_revision']]
    t.fault.after = 'setup:finish'
    assert connect.run_connect(approval) == 3
    capsys.readouterr()
    pending = read_json(path)
    assert pending['state'] == 'finish'
    assert pending['review_revision'] == review['review_revision']
    after_finish = snapshot(t.deps)
    after_identities = identities()
    assert set(after_identities) == set(before_identities) | {retained['selection']['agent']}
    assert len(after_identities) == len(before_identities) + 1
    assert len(t.turns) == len(t.probes) == 1
    effects = Counter(path for method, path in t.calls if method == 'POST'
                      and path.endswith(('setup:test', 'setup:finish')))
    assert sum(n for path, n in effects.items() if path.endswith('setup:test')) == 1
    assert sum(n for path, n in effects.items() if path.endswith('setup:finish')) == 1

    assert connect.run_connect(approval) == 0
    result = json.loads(capsys.readouterr().out)
    recovered = read_json(path)
    assert result['state'] == 'configured' and recovered['state'] == 'done'
    for field in ('selection', 'request', 'review_request', 'review_revision'):
        assert recovered[field] == pending[field]
    assert recovered['selection']['agent'] == retained['selection']['agent']
    assert recovered['request']['client_intent_id'] == retained['request']['client_intent_id']
    assert snapshot(t.deps) == after_finish
    assert identities() == after_identities
    assert len(t.turns) == len(t.probes) == 1
    assert Counter(path for method, path in t.calls if method == 'POST'
                   and path.endswith(('setup:test', 'setup:finish'))) == effects
    done_bytes = path.read_bytes()
    assert connect.run_connect(approval) == 0
    assert json.loads(capsys.readouterr().out) == result
    assert path.read_bytes() == done_bytes and snapshot(t.deps) == after_finish
    assert identities() == after_identities
    assert len(t.turns) == len(t.probes) == 1
