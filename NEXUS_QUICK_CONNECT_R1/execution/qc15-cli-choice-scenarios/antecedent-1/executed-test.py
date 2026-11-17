"""Installed CLI + canonical ASGI/SQLite; discovery/version/Test/lifecycle inert."""
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest
from nexus_connector_core.discovery import fingerprint
from okto_nexus.adapters.inbound.cli import connect, main
from okto_nexus.bootstrap import embedded_inventory
from okto_nexus.application.terminal_connection import PREFIX
import test_terminal_connect as helper
from test_connection_setup_recovery import snapshot

local_setup = helper.local_setup
checking = helper.checking
terminal = helper.terminal


@pytest.fixture
def cli(terminal, local_setup, tmp_path, monkeypatch):
    t = terminal
    home = tmp_path / 'cli-home'
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=1),
        inspect=lambda: dict(state='ready', instance_id='qc15-inert-lifecycle'),
        ensure_running=lambda **kw: pytest.fail('plan must not start a service'))
    monkeypatch.setattr(connect, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(connect, 'LocalOperatorHTTP', lambda **kw: t.call)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr('builtins.input', lambda prompt: pytest.fail('unexpected stdin: ' + prompt))
    monkeypatch.chdir(t.selection['project'])
    def run(tokens):
        return main.main([*tokens, '--home', str(home)])
    return SimpleNamespace(t=t, home=home, run=run, client=local_setup[2])


def publish(c, monkeypatch, tmp_path, *, two_families=False):
    owner = c.t.app.state.embedded_inventory_owner
    first = owner.candidates[0]
    path = tmp_path / ('inert-claude.exe' if two_families else 'inert-second-codex.exe')
    path.write_bytes(b'QC15 inert candidate; never executable')
    second = replace(first, adapter_id='claude_stream' if two_families else first.adapter_id,
        executable=str(path), fingerprint=fingerprint(path), version=None, trust='untrusted')
    candidates = (first, second)
    monkeypatch.setattr(embedded_inventory, 'discover_local_candidates', lambda **kw:
        SimpleNamespace(candidates=tuple(c for c in candidates
            if not kw.get('adapter_ids') or c.adapter_id in kw['adapter_ids'])))
    c.client.portal.call(owner.refresh)
    assert len(owner.candidates) == 2
    return owner


def readonly(c, before):
    assert snapshot(c.t.deps) == before
    assert c.t.turns == c.t.probes == []
    assert not any(m != 'GET' for m, _ in c.t.calls)


def wire(c, capsys, tokens, expected):
    assert c.run(tokens) == expected
    output = capsys.readouterr()
    assert not output.err
    return json.loads(output.out)


@pytest.mark.parametrize('answer,expected_client', [('2', 'claude'), ('c', None)])
def test_bare_two_families_explicit_choice_or_cancel(cli, monkeypatch, tmp_path, capsys, answer, expected_client):
    c = cli
    publish(c, monkeypatch, tmp_path, two_families=True)
    before = snapshot(c.t.deps)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    prompts = []
    def choose(prompt):
        prompts.append(prompt)
        assert prompt == 'Harness: '
        return answer
    monkeypatch.setattr('builtins.input', choose)
    code = c.run(['connect', '--plan', '--no-chat'])
    out = capsys.readouterr().out
    assert prompts == ['Harness: ']
    assert '1. codex' in out and '2. claude' in out and 'c. Cancel' in out
    if expected_client is None:
        assert code == 3 and 'CONNECT_CANCELLED' in out
        assert not list(c.home.glob('terminal/profiles/*.json'))
    else:
        assert code == 0, out
        record, = c.home.glob('terminal/profiles/*.json')
        saved = json.loads(record.read_text())
        assert saved['selection']['client'] == 'claude'
        assert saved['review_request']['configuration']['adapter_id'] == 'claude_stream'
    readonly(c, before)


def test_bare_two_families_noninteractive_requires_choice(cli, monkeypatch, tmp_path, capsys):
    c = cli
    publish(c, monkeypatch, tmp_path, two_families=True)
    before = snapshot(c.t.deps)
    result = wire(c, capsys, ['connect', '--plan', '--json'], 3)
    assert result['code'] == 'CLIENT_SELECTION_REQUIRED'
    observed = {v['harness'] for v in result['choices'] if v['observed']}
    assert observed == {'codex', 'claude'}
    readonly(c, before)


def test_two_candidates_explicitly_choose_second_exact_ref(cli, monkeypatch, tmp_path, capsys):
    c = cli
    owner = publish(c, monkeypatch, tmp_path)
    me = c.t.call('GET', PREFIX + '/connections/me')
    options = c.t.call('GET', PREFIX + '/agents/' + me['agent_id'] + '/runtime-options?executor_id=' + owner.key.executor_id)
    refs = [v['candidate_ref'] for v in options['options'] if v['adapter_id'] == 'codex_app_server']
    assert len(refs) == 2 and refs[0] != refs[1]
    before = snapshot(c.t.deps)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    prompts = []
    def choose(prompt):
        prompts.append(prompt)
        assert prompt == 'Installation: '
        return '2'
    monkeypatch.setattr('builtins.input', choose)
    assert c.run(['connect', 'codex', 'App', '--profile', 'second', '--plan', '--no-chat']) == 0
    out = capsys.readouterr().out
    assert prompts == ['Installation: '] and refs[0] in out and refs[1] in out
    saved = json.loads((c.home / 'terminal/profiles/second.json').read_text())
    assert saved['selection']['candidate_ref'] == refs[1]
    assert saved['review_request']['configuration']['candidate_ref'] == refs[1]
    readonly(c, before)


def test_two_candidates_noninteractive_refuses_first_default(cli, monkeypatch, tmp_path, capsys):
    c = cli
    publish(c, monkeypatch, tmp_path)
    before = snapshot(c.t.deps)
    result = wire(c, capsys, ['connect', 'codex', 'App', '--profile', 'ambiguous', '--plan', '--json'], 3)
    assert result['code'] == 'INSTALLATION_SELECTION_REQUIRED'
    assert len(result['choices']) == 2
    assert result['choices'][0]['candidate_ref'] != result['choices'][1]['candidate_ref']
    readonly(c, before)


def test_unknown_shell_like_token_never_spawns(cli, monkeypatch, capsys):
    c = cli
    before = snapshot(c.t.deps)
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **kw: pytest.fail('unknown token spawned a subprocess'))
    result = wire(c, capsys, ['connect', 'codex;$(QC15)', 'App', '--profile', 'unknown', '--plan', '--json'], 3)
    assert result['code'] == 'CLIENT_SELECTION_REQUIRED'
    assert any(v['harness'] == 'codex' and v['observed'] for v in result['choices'])
    readonly(c, before)


def test_mixed_case_harness_is_normalized(cli, capsys):
    c = cli
    before = snapshot(c.t.deps)
    value = wire(c, capsys, ['connect', 'CoDeX', 'App', '--profile', 'case', '--plan', '--json'], 0)
    assert value['selection']['client'] == 'codex'
    saved = json.loads((c.home / 'terminal/profiles/case.json').read_text())
    assert saved['review_request']['configuration']['adapter_id'] == 'codex_app_server'
    readonly(c, before)


def test_stale_canonical_publication_is_unconfirmed_not_missing(cli, capsys):
    c = cli
    owner = c.t.app.state.embedded_inventory_owner
    assert owner.published_batch is not None
    publication = c.client.portal.call(__import__('asyncio').to_thread, owner._publish, owner.published_batch, 120001)
    assert publication.publication_sequence > owner.publication.publication_sequence
    me = c.t.call('GET', PREFIX + '/connections/me')
    current = c.t.call('GET', PREFIX + '/agents/' + me['agent_id'] + '/runtime-options?executor_id=' + owner.key.executor_id)
    assert current['adapter_freshness']['codex_app_server'] == 'STALE'
    assert any(v['candidate_ref'] for v in current['options'] if v['adapter_id'] == 'codex_app_server')
    before = snapshot(c.t.deps)
    value = wire(c, capsys, ['connect', 'codex', 'App', '--profile', 'stale', '--plan', '--json'], 3)
    assert value['code'] == 'INVENTORY_UNCONFIRMED'
    readonly(c, before)
