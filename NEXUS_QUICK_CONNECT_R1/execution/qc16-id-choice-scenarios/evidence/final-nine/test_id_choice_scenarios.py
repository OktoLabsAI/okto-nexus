"""Canonical collision choices with scripted TTY; never real PTY/provider QA."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
import test_quick_connect_cli as fixtures
from test_public_connection_ids import public_request

from okto_nexus.adapters.inbound.cli import connect

local_setup = fixtures.local_setup
checking = fixtures.checking
terminal = fixtures.terminal
quick_cli = fixtures.quick_cli
isolated_provider_environment = fixtures.isolated_provider_environment


@pytest.fixture
def choices(quick_cli, monkeypatch, capsys):
    c = quick_cli
    _, review, result = fixtures.first_connection(c, capsys, profile='first', name='Choice Project')
    first_path = c.home / 'terminal/profiles/first.json'
    c.first_bytes = first_path.read_bytes()
    c.first_path = first_path
    c.first_result = result
    c.first_review = review
    c.displays = []
    c.prompts = []
    display = connect._display
    def capture(value, as_json):
        c.displays.append(deepcopy(value))
        return display(value, as_json)
    monkeypatch.setattr(connect, '_display', capture)
    return c


def protected(c):
    tables = ('agents', 'workspaces', 'execution_bindings', 'agent_endpoints',
        'runtime_execution_grants', 'connection_setup_commits', 'execution_sessions',
        'execution_operations', 'agent_execution_policies', 'agent_runtime_overrides', 'connection_public_ids')
    with c.t.deps.connection_factory.unit_of_work(write=False) as uow:
        # Activity timestamps are metadata; every identity/permission/grant field stays exact.
        return {table: [{key: value for key, value in dict(row).items() if key != 'last_seen_at'}
            for row in uow.connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')] for table in tables}


def scripted(c, monkeypatch, answers):
    values = iter(answers)
    c.prompts.clear()
    def read(prompt):
        c.prompts.append(prompt)
        return next(values)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr('builtins.input', read)


def untouched(c, before):
    assert protected(c) == before
    assert c.first_path.read_bytes() == c.first_bytes
    assert len(c.t.turns) == len(c.t.probes) == 1


@pytest.mark.parametrize('requested', ['codex', 'claude'], ids=['F03-same-family', 'F04-cross-family-explicit-resume'])
def test_explicit_resume_uses_actual_binding_family(choices, monkeypatch, capsys, requested):
    c = choices
    before = protected(c)
    scripted(c, monkeypatch, ['r', 'y'])
    assert c.run(['connect', requested, 'Choice Project', '--id', 'codex',
        '--profile', 'resume-' + requested, '--no-chat']) == 0
    output = capsys.readouterr().out
    assert c.prompts == ['Choice: ', 'Confirm resume? [y/N] ']
    assert 'Resume the existing codex' in output
    if requested == 'claude':
        assert 'requested: claude' in output
    result = c.displays[-1]
    assert result['state'] == 'configured'
    assert result['quick_connect']['operation'] == 'reused'
    assert result['quick_connect']['harness'] == 'codex'
    assert result['quick_connect']['canonical_reference'] == c.first_result['quick_connect']['canonical_reference']
    binding = next(row for row in result['configuration']['connections'] if row['binding_id'] == result['binding_id'])
    assert binding['adapter_id'] == 'codex_app_server'
    untouched(c, before)


@pytest.mark.parametrize('choice,answers,chosen,profile', [
    ('i', ['i', 'reviewer', 'n'], 'reviewer', 'manual-id'),
    ('s', ['s', 'n'], 'codex-2', 'suggested-id'),
], ids=['F05-manual-id', 'F06-suggested-id'])
def test_alternate_id_has_new_unapproved_review_then_exact_profile_apply(choices, monkeypatch, capsys,
        choice, answers, chosen, profile):
    c = choices
    before = protected(c)
    scripted(c, monkeypatch, answers)
    assert c.run(['connect', 'codex', 'Choice Project', '--id', 'codex', '--profile', profile, '--no-chat']) == 0
    output = capsys.readouterr().out
    assert c.prompts[0] == 'Choice: '
    assert ('ID do Harness: ' in c.prompts) is (choice == 'i')
    assert 'Review revision:' in output and 'ID do Harness (proposed): ' + chosen in output
    path = c.home / 'terminal/profiles' / (profile + '.json')
    pending = json.loads(path.read_text())
    assert pending['state'] == 'review'
    assert pending['review_revision'] != c.first_review['review_revision']
    assert pending['selection']['public_connection']['connect_id'] == chosen
    assert pending['request']['public_connection'] == pending['review_request']['public_connection']
    assert pending['request']['workspace_id'] == c.first_result['workspace_id']
    untouched(c, before)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    assert c.run(['connect', '--profile', profile, '--approve', pending['review_revision'], '--json', '--no-chat']) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied['quick_connect']['connect_id'] == chosen and applied['quick_connect']['connect_id_status'] == 'bound'
    reference = applied['quick_connect']['canonical_reference']
    assert set(reference) == set(c.first_result['quick_connect']['canonical_reference'])
    assert reference['workspace_id'] == c.first_result['workspace_id']
    assert reference['binding_id'] != c.first_result['binding_id']
    assert len(c.t.turns) == 2
    assert pending['version_check_required'] is False
    assert len(c.t.probes) == 1  # The same installation is already technically qualified.
    assert c.first_path.read_bytes() == c.first_bytes
    after = protected(c)
    for table, rows in before.items():
        assert all(row in after[table] for row in rows), table


def test_cancel_reports_lifecycle_and_metadata_without_false_no_effect_claim(choices, monkeypatch, capsys):
    c = choices
    before = protected(c)
    scripted(c, monkeypatch, ['c'])
    assert c.run(['connect', 'codex', 'Choice Project', '--id', 'codex', '--profile', 'cancelled', '--no-chat']) == 0
    output = capsys.readouterr().out
    result = c.displays[-1]
    assert result['state'] == 'canceled'
    assert result['lifecycle_requested'] is True
    assert result['canonical_metadata_revalidation_requested'] is True and result['effects_started'] is None
    assert 'Canonical metadata revalidation' in output
    assert not (c.home / 'terminal/profiles/cancelled.json').exists()
    untouched(c, before)


def test_explicit_add_never_offers_resume_or_accepts_r(choices, monkeypatch, capsys):
    c = choices
    before = protected(c)
    scripted(c, monkeypatch, ['r', 'c'])
    assert c.run(['connect', 'codex', 'Choice Project', '--id', 'codex', '--profile', 'add-cancelled',
        '--new-connection', '--no-chat']) == 0
    output = capsys.readouterr().out
    assert c.prompts == ['Choice: ', 'Choice: ']
    assert 'r. Resume' not in output and 'Choose one of the displayed actions.' in output
    assert c.displays[-1]['state'] == 'canceled'
    untouched(c, before)


def test_json_cross_family_conflict_never_reads_stdin(choices, monkeypatch, capsys):
    c = choices
    before = protected(c)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr('builtins.input', lambda prompt: pytest.fail('JSON conflict requested input'))
    assert c.run(['connect', 'claude', 'Choice Project', '--id', 'codex', '--profile', 'json-conflict', '--json']) == 3
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == 'refused' and result['code'] == 'HARNESS_ID_ALREADY_EXISTS'
    assert result['possible_effect'] is False
    assert result['choices'] == [{'connect_id': 'claude', 'proposed': True}]
    untouched(c, before)


def test_exact_binding_contradiction_is_refused_before_collision_menu(choices, monkeypatch, capsys):
    c = choices
    before = protected(c)
    monkeypatch.setattr(connect.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr('builtins.input', lambda prompt: pytest.fail('Contradictory exact selector opened a menu'))
    assert c.run(['connect', 'codex', 'Choice Project', '--id', 'codex', '--profile', 'contradictory',
        '--binding-id', 'not-the-bound-connection', '--no-chat']) == 3
    output = capsys.readouterr().out
    assert c.displays[-1]['code'] == 'CONNECTION_SELECTOR_CONFLICT'
    assert 'r. Resume' not in output
    untouched(c, before)


def test_other_intent_reservation_remains_pending_without_another_setup(choices, local_setup, monkeypatch, capsys):
    c = choices
    _, request = public_request(local_setup, name='held', intent='other-owned-intent',
        workspace_id=c.first_result['workspace_id'])
    reserved = c.t.call('POST', '/api/v1/runtime-management/connections/public-ids/reserve',
        {'approved': True, 'request': request})
    assert reserved['state'] == 'reserved' and reserved['connect_id'] == 'held'
    before = protected(c)
    monkeypatch.setattr('builtins.input', lambda prompt: pytest.fail('JSON pending collision requested input'))
    assert c.run(['connect', 'codex', 'Choice Project', '--id', 'held', '--profile', 'pending-conflict', '--json']) == 3
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result['code'] == 'HARNESS_ID_PENDING' and result['possible_effect'] is False
    assert request['client_intent_id'] not in output
    assert request['public_connection']['reservation_ref'] not in output
    untouched(c, before)
