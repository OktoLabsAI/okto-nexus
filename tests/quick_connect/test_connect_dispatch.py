"""Aliases and grammar failures remain ahead of service/setup authority."""
import json

import pytest

from okto_nexus.adapters.inbound.cli import connect
from okto_nexus.adapters.inbound.cli.main import main


@pytest.mark.parametrize('name', ['codex', 'claude', 'pi'])
def test_alias_calls_same_function_without_process_or_global_argv(monkeypatch, name):
    import sys
    before = list(sys.argv)
    calls = []
    monkeypatch.setattr(connect, 'run_connect', lambda args: calls.append(args) or 9)
    assert main([name, 'My project', '--id', 'reviewer']) == 9
    assert calls == [[name, 'My project', '--id', 'reviewer']]
    assert sys.argv == before


def test_product_command_wins_and_unknown_root_never_enters_connect(monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli import service
    monkeypatch.setattr(service, 'run_service', lambda args: 7 if args == ['status'] else 8)
    monkeypatch.setattr(connect, 'run_connect', lambda args: pytest.fail('connect called'))
    assert main(['service', 'status']) == 7
    assert main(['claud']) == 2
    output = capsys.readouterr().err
    assert 'claude' in output and 'stdio' not in output


@pytest.mark.parametrize('args', [
    ['codex', '--clinet', 'pi'], ['codex', '--pro', '/tmp'],
    ['codex', 'app', 'extra'], ['codex', '--client', 'claude'],
    ['codex', 'app', '--mode', 'participant'], ['--id', 'path/invalid'],
    ['codex', '--port', '70000'], ['codex', '--unknown-service', 'yes'],
])
def test_json_grammar_errors_are_one_document_before_any_context(monkeypatch, capsys, args):
    monkeypatch.setattr(connect, 'project_profile', lambda *a: pytest.fail('directory read'))
    monkeypatch.setattr(connect, 'resolve_local_service', lambda *a: pytest.fail('service read'))
    assert connect.run_connect([*args, '--json']) == 2
    value = json.loads(capsys.readouterr().out)
    assert value['code'] == 'INVALID_ARGUMENTS'
    assert value['effects_started'] is False and value['lifecycle_requested'] is False


def test_help_stays_pure_when_reached_through_alias(monkeypatch, capsys):
    monkeypatch.setattr(connect, 'project_profile', lambda *a: pytest.fail('directory read'))
    with pytest.raises(SystemExit) as caught:
        main(['claude', '--help'])
    assert caught.value.code == 0
    assert '--id HARNESS_ID' in capsys.readouterr().out
