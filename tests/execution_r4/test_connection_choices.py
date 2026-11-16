"""Passive local catalogs are hints; canonical admission remains mandatory."""
from dataclasses import asdict
import hashlib
from pathlib import Path

import pytest

from okto_nexus.adapters.inbound.cli.connection_choices import (
    ConnectionChoiceScope, list_connection_choices,
)
from okto_nexus.adapters.outbound.service_manager.context import atomic_json


def profile(home, project, name='first', *, server='server-a', operator=None, state='done'):
    directory = home / 'terminal/profiles'
    directory.mkdir(parents=True, exist_ok=True)
    selection = dict(project=str(project), agent='agent-' + name, client='codex', workspace_id='workspace-a')
    if operator:
        selection['operator_profile'] = operator
    value = dict(format=1, server_id=server, selection=selection, state=state,
        result={'binding': {'binding_id': 'binding-' + name}})
    atomic_json(directory / (name + '.json'), value)
    return directory / (name + '.json')


def scope(home, project, **kwargs):
    return ConnectionChoiceScope(home, project, 'server-a', **({'instance_id': 'instance-a'} | kwargs))


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob('*') if p.is_file()}


def test_empty_store_does_not_create_anything(tmp_path):
    home = tmp_path / 'absent'
    result = list_connection_choices(scope(home, tmp_path))
    assert result.complete and result.choices == ()
    assert not home.exists()


def test_legacy_and_multiple_connections_preserved_without_rewrite(tmp_path):
    home, project = tmp_path / 'home', tmp_path / 'project'
    project.mkdir()
    legacy = 'project-' + hashlib.sha256(str(project).encode()).hexdigest()[:24]
    profile(home, project, legacy)
    profile(home, project, 'claude-second', state='test_submitted')
    before = snapshot(home)
    result = list_connection_choices(scope(home, project))
    assert result.complete
    assert {c.profile for c in result.choices} == {legacy, 'claude-second'}
    assert all(c.requires_canonical_revalidation for c in result.choices)
    assert next(c for c in result.choices if c.profile == 'claude-second').setup_pending
    assert snapshot(home) == before
    assert 'ready' not in str(asdict(result))


def test_destinations_homes_projects_and_operator_topologies_do_not_mix(tmp_path):
    home, project = tmp_path / 'home', tmp_path / 'project'
    other_home, other_project = tmp_path / 'other-home', tmp_path / 'other-project'
    profile(home, project, 'right')
    profile(home, project, 'other-server', server='server-b')
    profile(home, project, 'remote', operator='human')
    profile(home, other_project, 'other-project')
    profile(other_home, project, 'other-home')
    assert [c.profile for c in list_connection_choices(scope(home, project)).choices] == ['right']
    assert [c.profile for c in list_connection_choices(scope(other_home, project)).choices] == ['other-home']


def test_remote_human_metadata_exact_without_vault_or_client(tmp_path, monkeypatch):
    home, project = tmp_path / 'home', tmp_path / 'project'
    profile(home, project, 'remote', operator='human')
    profile(home, project, 'other-human', operator='other')
    operators = home / 'terminal/operators'
    operators.mkdir()
    atomic_json(operators / 'human.json', dict(format=1, server_id='server-a', origin='https://nexus.example', username='alice'))
    from okto_nexus.adapters.outbound.operator_client import OperatorProfile
    monkeypatch.setattr(OperatorProfile, 'client', lambda *a: pytest.fail('must not open authenticated client'))
    monkeypatch.setattr(OperatorProfile, 'secret', lambda *a: pytest.fail('must not access vault'))
    selected = scope(home, project, instance_id=None, operator_profile='human', origin='https://nexus.example', username='alice')
    before = snapshot(home)
    assert [c.profile for c in list_connection_choices(selected).choices] == ['remote']
    wrong = scope(home, project, instance_id=None, operator_profile='human', origin='https://nexus.example', username='bob')
    assert not list_connection_choices(wrong).complete
    assert not list_connection_choices(wrong).choices
    assert snapshot(home) == before


def test_all_uncertainty_slots_are_retained_and_no_payload_exposed(tmp_path):
    home, project = tmp_path / 'home', tmp_path / 'project'
    profile(home, project)
    work = home / 'terminal/work'
    work.mkdir()
    atomic_json(work / 'first.json', dict(format=1,
        work={'state': 'submit_submitted', 'client_intent_id': 'original'},
        control={'state': 'resolve_submitted'}, authorization={'state': 'submitted'},
        decision={'approval_key': {'canonical_request_id': 'request'},
            'client_intent_id': 'decision-original', 'response_hash': 'private-not-a-label'}))
    before = snapshot(home)
    choice, = list_connection_choices(scope(home, project)).choices
    assert choice.work_pending and choice.control_pending
    assert choice.authorization_pending and choice.decision_pending
    assert 'private-not-a-label' not in str(asdict(choice))
    assert snapshot(home) == before


@pytest.mark.parametrize('content', ['{', '[]', 'x' * 131073], ids=['broken', 'array', 'oversized'])
def test_invalid_or_oversized_checkpoint_is_not_empty_success(tmp_path, content):
    home, project = tmp_path / 'home', tmp_path / 'project'
    path = profile(home, project)
    path.write_text(content, encoding='utf-8')
    before = snapshot(home)
    result = list_connection_choices(scope(home, project))
    assert not result.complete and not result.choices
    assert result.issues[0].reason == 'checkpoint_unconfirmed'
    assert snapshot(home) == before


def test_invalid_work_checkpoint_preserved_not_adopted(tmp_path):
    home, project = tmp_path / 'home', tmp_path / 'project'
    profile(home, project)
    work = home / 'terminal/work'
    work.mkdir()
    (work / 'first.json').write_text('{', encoding='utf-8')
    result = list_connection_choices(scope(home, project))
    assert not result.complete and not result.choices
    assert (work / 'first.json').read_text() == '{'


def test_startup_and_unknown_work_stage_remain_pending(tmp_path):
    home, project = tmp_path / 'home', tmp_path / 'project'
    path = profile(home, project)
    import json
    value = json.loads(path.read_text())
    value['login_start_operation'] = {'state': 'installed'}
    atomic_json(path, value)
    work = home / 'terminal/work'
    work.mkdir()
    atomic_json(work / 'first.json', {'format': 1, 'work': {'state': 'future_state'}})
    choice, = list_connection_choices(scope(home, project)).choices
    assert choice.startup_pending and choice.work_pending


def test_foreign_work_scope_cannot_be_adopted(tmp_path):
    home, project = tmp_path / 'home', tmp_path / 'project'
    profile(home, project)
    work = home / 'terminal/work'
    work.mkdir()
    atomic_json(work / 'first.json', {'format': 1, 'scope': {'server_id': 'other-server'}})
    result = list_connection_choices(scope(home, project))
    assert not result.complete and not result.choices


def test_bounded_directory_and_document_reads(tmp_path, monkeypatch):
    home, project = tmp_path / 'home', tmp_path / 'project'
    for n in range(4):
        profile(home, project, 'profile' + str(n))
    from okto_nexus.adapters.inbound.cli import connection_choices
    monkeypatch.setattr(connection_choices, 'MAX_PROFILES', 2)
    result = list_connection_choices(scope(home, project))
    assert len(result.choices) == 2 and not result.complete
    assert result.issues[-1].reason == 'catalog_limit'


def test_symlink_profile_refused_without_reading_target(tmp_path, monkeypatch):
    home, project = tmp_path / 'home', tmp_path / 'project'
    path = profile(home, project)
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda p: p == path or original(p))
    result = list_connection_choices(scope(home, project))
    assert not result.complete and not result.choices


def test_deep_operator_metadata_fails_closed(tmp_path):
    home, project = tmp_path / 'home', tmp_path / 'project'
    operator = home / 'terminal/operators/human.json'
    operator.parent.mkdir(parents=True)
    operator.write_text('[' * 2000 + '0' + ']' * 2000)
    selected = scope(home, project, instance_id=None, operator_profile='human',
        origin='https://nexus.example', username='alice')
    result = list_connection_choices(selected)
    assert not result.complete and not result.choices


def test_local_instance_and_remote_human_must_be_selected(tmp_path):
    with pytest.raises(ValueError):
        list_connection_choices(ConnectionChoiceScope(tmp_path, tmp_path, 'server-a'))
    with pytest.raises(ValueError):
        list_connection_choices(scope(tmp_path, Path('relative')))
    # Legacy metadata cannot establish an instance association, even when the
    # caller selected one. Both are unconfirmed, never ready/adopted.
    profile(tmp_path, tmp_path, 'legacy')
    a = list_connection_choices(scope(tmp_path, tmp_path))
    b = list_connection_choices(scope(tmp_path, tmp_path, instance_id='instance-b'))
    assert a.choices == b.choices
    assert all(c.requires_canonical_revalidation for c in b.choices)
