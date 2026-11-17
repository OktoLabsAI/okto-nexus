"""CLI integration on real canonical authorities, synthetic Test peers."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_quick_connect_cli import (  # noqa: F401
    checking, invoke, isolated_provider_environment, local_setup, quick_cli, terminal,
)
from test_terminal_multi_harness import two_harnesses  # noqa: F401
from test_quick_connect_extra_scenarios import canonical_snapshot


@pytest.mark.parametrize('field', ['name', 'harness', 'root'])
def test_f21_customize_real_review_creates_fresh_exact_intent(quick_cli, two_harnesses, checking, monkeypatch, capsys, field):
    from okto_nexus.adapters.inbound.cli import connect
    c = quick_cli
    owner = c.t.app.state.embedded_inventory_owner
    checking[2].portal.call(owner.refresh)
    assert {candidate.adapter_id for candidate in owner.candidates} == {'codex_app_server', 'claude_stream'}
    assert all(Path(candidate.executable).is_relative_to(c.project.parent) for candidate in owner.candidates)
    root_a = c.project
    root_b = root_a.parent / 'explicit-physical-root-b'
    root_b.mkdir()
    values = dict(name=('2', 'New Logical Name'), harness=('3', 'claude'), root=('4', str(root_b)))
    choice, replacement = values[field]
    answers = iter(['customize', choice, replacement, 'y'])
    old_records = []
    final_records = []
    before = canonical_snapshot(c)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    def answer(prompt):
        value = next(answers)
        assert c.t.turns == c.t.probes == []  # every input precedes the only final y
        assert canonical_snapshot(c) == before
        if value == 'customize':
            assert 'Confirm this review' in prompt
            paths = list((c.home / 'terminal/profiles').glob('*.json'))
            assert len(paths) == 1
            old_records.append((paths[0], json.loads(paths[0].read_text())))
        elif value == choice:
            assert prompt == 'Customize: '
        elif value == replacement:
            expected = dict(name='New project name: ', harness='New harness (codex/claude/pi): ', root='Existing execution folder: ')
            assert prompt == expected[field]
        else:
            assert value == 'y' and 'Confirm this review' in prompt
            paths = list((c.home / 'terminal/profiles').glob('*.json'))
            assert len(paths) == 2
            new_path = next(p for p in paths if p != old_records[0][0])
            final_records.append((new_path, json.loads(new_path.read_text())))
        return value
    monkeypatch.setattr('builtins.input', answer)
    assert c.run(['connect', 'codex', 'Original Logical Name', '--no-chat']) == 0
    capsys.readouterr()
    assert len(c.t.turns) == len(c.t.probes) == 1
    old_path, old = old_records[0]
    new_path, new_review = final_records[0]
    superseded = json.loads(old_path.read_text())
    new = json.loads(new_path.read_text())
    assert superseded['state'] == 'superseded' and superseded['superseded_by_profile'] == new_path.stem
    assert superseded['request'] == old['request'] and superseded['review_request'] == old['review_request']
    assert superseded['review_revision'] == old['review_revision']
    assert new['state'] == 'done' and new_path.stem != old_path.stem
    assert new['request']['client_intent_id'] != old['request']['client_intent_id']
    assert new['review_revision'] != old['review_revision']
    assert new['request']['public_connection']['reservation_ref'] != old['request']['public_connection']['reservation_ref']
    assert new['review_revision'] == new_review['review_revision']
    assert new['request'] == new_review['request'] or new['request'] | {'inventory_revision': new_review['request']['inventory_revision']} == new_review['request']
    selected = new['selection']
    assert selected['label'] == ('New Logical Name' if field == 'name' else 'Original Logical Name')
    assert selected['client'] == ('claude' if field == 'harness' else 'codex')
    assert selected['project'] == str(root_b if field == 'root' else root_a)
    assert selected['quick_connect']['cwd_resolution']['invocation_cwd'] == str(root_a)
    assert selected['quick_connect']['cwd_resolution']['project_root'] == selected['project']
    assert Path.cwd() == root_a
    after = canonical_snapshot(c)
    assert len(after['connection_setup_commits']) == len(before['connection_setup_commits']) + 1
    assert len(after['execution_bindings']) == len(before['execution_bindings']) + 1
    assert len(after['runtime_execution_grants']) == len(before['runtime_execution_grants']) + 1
    assert len(after['connection_public_ids']) == len(before['connection_public_ids']) + 1
    assert after['connection_public_ids'][0]['state'] == 'bound'
    assert after['connection_public_ids'][0]['reservation_ref'] == new['request']['public_connection']['reservation_ref']
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    refused = invoke(c, capsys, ['connect', '--profile', old_path.stem, '--approve', old['review_revision'], '--json'], expected=3)
    assert refused['code'] == 'REVIEW_SUPERSEDED'
    assert canonical_snapshot(c) == after and len(c.t.turns) == len(c.t.probes) == 1


def test_h01_bound_public_id_and_project_are_printed_before_chat_callback(quick_cli, monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli import connect, work
    c = quick_cli
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr('builtins.input', lambda prompt: 'y' if 'Confirm this review' in prompt else pytest.fail(prompt))
    observed = []
    def chat(service, profile, *, timeout):
        text = capsys.readouterr().out
        assert 'Conexão configurada — ID do Harness: codex' in text
        assert 'Project: Chat Logical Project | Harness: codex' in text
        assert 'Connection shortcut:' not in text and profile not in text
        document = json.loads((c.home / 'terminal/profiles' / (profile + '.json')).read_text())
        assert document['state'] == 'done'
        assert document['result']['public_connection']['state'] == 'bound'
        assert len(c.t.turns) == len(c.t.probes) == 1
        observed.append(dict(profile=profile, bound=True))
        return 37  # observation spy only; never enters or submits project work
    monkeypatch.setattr(work, 'interactive_work', chat)
    assert c.run(['connect', 'codex', 'Chat Logical Project']) == 37
    assert len(observed) == 1 and observed[0]['bound']
