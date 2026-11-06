"""Owned local compensation with real files/auth/SQLite and synthetic vault effects."""
from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tomllib

import pytest

import test_participant_init
from test_connection_setup_recovery import snapshot
from okto_nexus.application.participant_removal import ParticipantRemoval
from okto_nexus.application.participant_launch import ParticipantLaunch
from okto_nexus.application.participant_diagnostics import ParticipantDiagnostics, inspect_participant
from okto_nexus.application.terminal_connection import ConnectionError
from okto_nexus.adapters.outbound import participant_client, participant_files
from okto_nexus.adapters.outbound.provider_vault import WindowsCredentials, SystemKeyring
from okto_nexus.adapters.outbound.service_manager.context import atomic_json
from okto_nexus.adapters.inbound.cli.main import main

local_setup = test_participant_init.local_setup
setup = test_participant_init.setup


@pytest.fixture
def removal(setup, monkeypatch):
    s = setup
    calls = []
    def remove(service, name):
        calls.append((service, name))
        s.vault.values.pop((service, name), None)
    monkeypatch.setattr(s.vault, 'remove_if_present', remove, raising=False)
    flow = ParticipantRemoval(s.home, 'external', s.flow.save)
    return SimpleNamespace(s=s, flow=flow, calls=calls)


def complete(t, client='claude'):
    s = t.s
    path = s.root / ('.codex/config.toml' if client == 'codex' else '.mcp.json')
    path.parent.mkdir(exist_ok=True)
    raw = (b'# preserved comment\nmodel = "other"\n[mcp_servers.other]\ncommand="never-execute"\n' if client == 'codex' else
        b'{"mcpServers":{"other":{"command":"never-execute","env":{"SECRET":"other-private-value"}}},"theme":"dark"}')
    path.write_bytes(raw)
    selection = s.selection | dict(client=client, config_file=str(path))
    reviewed = s.flow.review(selection, s.key)
    s.flow.apply(reviewed, s.key, reviewed['review_revision'])
    return s.saves[-1], path, raw


@pytest.mark.parametrize('client', ['claude', 'codex'])
def test_remove_only_owned_entry_preserves_other_values_and_server(removal, monkeypatch, client):
    t = removal
    saved, path, original = complete(t, client)
    configured = path.read_bytes()
    acl = participant_files.access_revision(path)
    t.s.vault.values['unrelated', 'agent-key'] = 'must-preserve'
    def no_http(*args, **kwargs):
        raise AssertionError('Local removal cannot use HTTP')
    monkeypatch.setattr(participant_client, 'build_opener', no_http)
    planned = t.flow.review(saved)
    assert path.read_bytes() == configured and not t.calls
    assert 'other-private-value' not in json.dumps(planned['removal'])
    assert t.s.key not in json.dumps(planned)
    result = t.flow.apply(planned, planned['removal']['review_revision'])
    assert result['state'] == 'removed' and result['evidence_scope'] == 'retained_local_removal_receipt'
    if client == 'claude':
        assert json.loads(path.read_bytes()) == json.loads(original)
    else:
        # Core removes the owned table span, preserving all other bytes,
        # including the separator preceding it; it does not restore a backup.
        assert path.read_bytes() == configured[:configured.index(b'[mcp_servers.nexus]')]
        assert tomllib.loads(path.read_text()) == tomllib.loads(original.decode())
    assert participant_files.access_revision(path) == acl
    assert t.s.vault.values == {('unrelated', 'agent-key'): 'must-preserve'}
    assert snapshot(t.s.deps) == t.s.before
    backups = list(path.parent.glob('*.bak'))
    assert len(backups) == 2
    for backup in backups:
        participant_files._check_private(backup)
    assert t.flow.apply(t.s.saves[-1], result['review_revision']) == result
    assert len(t.calls) == 1 and len(list(path.parent.glob('*.bak'))) == 2


@pytest.mark.parametrize('stage', ['file_pending', 'vault_pending', 'done'])
def test_lost_removal_checkpoint_recovers_without_restoring_or_rewriting(removal, stage):
    t = removal
    saved, path, _ = complete(t)
    planned = t.flow.review(saved)
    persist = t.flow.save
    def fail(value):
        if value['removal']['stage'] == stage:
            raise OSError('private ' + t.s.key)
        persist(value)
    t.flow.save = fail
    with pytest.raises(OSError):
        t.flow.apply(planned, planned['removal']['review_revision'])
    retained = t.s.saves[-1]
    if stage != 'file_pending':
        with pytest.raises(ConnectionError, match='removal'):
            t.s.flow.apply(retained, t.s.key, retained['review_revision'])
    if stage == 'done':
        # After the file stage was confirmed, later unrelated edits are never
        # rolled back while the vault-only checkpoint resumes.
        path.write_bytes(path.read_bytes() + b'\n')
        after = path.read_bytes()
    t.flow.save = persist
    result = t.flow.apply(retained, planned['removal']['review_revision'])
    assert result['state'] == 'removed' and len(list(path.parent.glob('*.bak'))) == 2
    assert not t.s.vault.values
    if stage == 'done':
        assert path.read_bytes() == after
    assert snapshot(t.s.deps) == t.s.before


def test_uncertain_file_followed_by_edit_is_preserved(removal):
    t = removal
    saved, path, _ = complete(t)
    planned = t.flow.review(saved)
    persist = t.flow.save
    def fail(value):
        if value['removal']['stage'] == 'vault_pending':
            raise OSError('Lost file completion')
        persist(value)
    t.flow.save = fail
    with pytest.raises(OSError):
        t.flow.apply(planned, planned['removal']['review_revision'])
    retained = t.s.saves[-1]
    path.write_bytes(path.read_bytes() + b'\n')
    changed = path.read_bytes()
    t.flow.save = persist
    with pytest.raises(ConnectionError, match='changed'):
        t.flow.apply(retained, planned['removal']['review_revision'])
    assert path.read_bytes() == changed and not t.calls and t.s.vault.values


@pytest.mark.parametrize('change', ['unrelated', 'owned', 'approval'])
def test_removal_review_drift_is_refused_before_retirement(removal, change):
    t = removal
    saved, path, _ = complete(t)
    planned = t.flow.review(saved)
    approval = planned['removal']['review_revision']
    if change == 'unrelated':
        path.write_bytes(path.read_bytes() + b'\n')
    elif change == 'owned':
        path.write_bytes(path.read_bytes().replace(b'nexus.example', b'other.example'))
    else:
        approval = 'wrong'
    before = path.read_bytes()
    with pytest.raises(ConnectionError):
        t.flow.apply(planned, approval)
    assert path.read_bytes() == before and not t.calls and t.s.saves[-1]['removal']['stage'] == 'review'


def test_keep_config_is_explicit_for_changed_or_unavailable_file(removal):
    t = removal
    saved, path, _ = complete(t)
    path.write_text('{"mcpServers":{"nexus":{"url":"https://other.example"}}}')
    before = path.read_bytes()
    with pytest.raises(Exception):
        t.flow.review(saved)
    planned = t.flow.review(saved, keep_config=True)
    assert planned['removal']['review']['file'] is None
    t.flow.apply(planned, planned['removal']['review_revision'])
    assert path.read_bytes() == before and not t.s.vault.values


@pytest.mark.parametrize('state', ['review', 'credential_pending', 'credential_stored', 'file_pending'])
def test_compensate_partial_setup_without_claiming_an_unapplied_file(removal, state):
    t = removal
    s = t.s
    reviewed = s.flow.review(s.selection, s.key)
    saved = deepcopy(reviewed)
    if state != 'review':
        saved.update(state=state, approval=saved['review_revision'])
        if state != 'credential_pending':
            s.flow.vault(saved['review']).call('store', s.key)
    planned = t.flow.review(saved)
    assert planned['removal']['review']['file'] is None
    result = t.flow.apply(planned, planned['removal']['review_revision'])
    assert result['state'] == 'removed' and not Path(s.selection['config_file']).exists()
    assert not s.vault.values and len(t.calls) == (0 if state == 'review' else 1)


def test_recover_applied_but_unconfirmed_init_by_owned_compensation(removal):
    t = removal
    reviewed = t.s.flow.review(t.s.selection, t.s.key)
    persist = t.s.flow.save
    def fail(value):
        if value['state'] == 'done':
            raise OSError('Lost setup completion')
        persist(value)
    t.s.flow.save = fail
    with pytest.raises(OSError):
        t.s.flow.apply(reviewed, t.s.key, reviewed['review_revision'])
    saved = t.s.saves[-1]
    assert saved['state'] == 'file_pending'
    planned = t.flow.review(saved)
    result = t.flow.apply(planned, planned['removal']['review_revision'])
    assert result['state'] == 'removed' and not t.s.vault.values
    assert 'nexus' not in json.loads(Path(t.s.selection['config_file']).read_text())['mcpServers']


def test_advanced_setup_invalidates_unapproved_removal_review(removal):
    t = removal
    reviewed = t.s.flow.review(t.s.selection, t.s.key)
    planned = t.flow.review(reviewed)
    t.s.flow.apply(planned, t.s.key, planned['review_revision'])
    advanced = t.s.saves[-1]
    with pytest.raises(ConnectionError, match='advanced'):
        t.flow.apply(advanced, planned['removal']['review_revision'])
    refreshed = t.flow.review(advanced)
    assert refreshed['removal']['review']['file'] is not None


def test_vault_failure_is_pending_and_profile_cannot_reactivate(removal, monkeypatch, capsys):
    t = removal
    saved, path, _ = complete(t)
    directory = t.s.home / 'terminal/participants'
    participant_files.private_directory(directory)
    target = directory / 'external.json'
    atomic_json(target, saved)
    base = ['--home', str(t.s.home), '--profile', 'external', '--json']
    assert main(['participant', 'remove', *base, '--plan']) == 0
    reviewed = json.loads(capsys.readouterr().out)
    remove = t.s.vault.remove_if_present
    def fail(*args):
        raise RuntimeError('SECRET ' + t.s.key)
    monkeypatch.setattr(t.s.vault, 'remove_if_present', fail)
    assert main(['participant', 'remove', *base, '--approve', reviewed['review_revision']]) == 3
    raw = capsys.readouterr().out
    assert t.s.key not in raw and 'SECRET' not in raw
    assert 'resume the same participant remove intent' in json.loads(raw)['message']
    retained = json.loads(target.read_text())
    assert retained['removal']['stage'] == 'vault_pending'
    for command in (['init'], ['connect', '--mode', 'participant'], ['participant', 'launch']):
        assert main([*command, *base]) == 3
        assert json.loads(capsys.readouterr().out)['code'] == 'PARTICIPANT_PROFILE_RETIRED'
    assert main(['init', *base, '--plan']) == 0
    assert json.loads(capsys.readouterr().out)['state'] == 'removal_in_progress'
    report = ParticipantDiagnostics('external')
    inspect_participant(report, t.s.home, retained, check_server=True, check_mcp=True, check_environment=True)
    assert not report.credential_read and not report.mcp_checked
    assert report.checks['participant_profile']['code'] == 'PARTICIPANT_PROFILE_RETIRED'
    with pytest.raises(ConnectionError):
        ParticipantLaunch(t.s.home, 'external', lambda _: None)._setup(retained)
    before = path.read_bytes()
    monkeypatch.setattr(t.s.vault, 'remove_if_present', remove)
    assert main(['participant', 'remove', *base]) == 0
    assert json.loads(capsys.readouterr().out)['state'] == 'removed'
    assert path.read_bytes() == before and not t.s.vault.values
    assert main(['participant', 'remove', *base, '--refresh', '--plan']) == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'PARTICIPANT_REMOVAL_APPROVED'


def test_absent_profile_creates_nothing(tmp_path, capsys):
    home = tmp_path / 'absent'
    assert main(['participant', 'remove', '--home', str(home), '--profile', 'missing', '--json']) == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'PARTICIPANT_PROFILE_ABSENT'
    assert not home.exists()


def test_generic_manual_profile_removes_only_its_vault_entry(removal):
    t = removal
    selection = t.s.selection | dict(client='generic', config_file=None)
    reviewed = t.s.flow.review(selection, t.s.key)
    t.s.flow.apply(reviewed, t.s.key, reviewed['review_revision'])
    planned = t.flow.review(t.s.saves[-1])
    assert planned['removal']['review']['file'] is None
    result = t.flow.apply(planned, planned['removal']['review_revision'])
    assert result['state'] == 'removed' and not t.s.vault.values
    assert not Path(t.s.selection['config_file']).exists()


@pytest.mark.parametrize('code', [1168, 5])
def test_windows_vault_only_treats_confirmed_absence_as_success(code):
    backend = object.__new__(WindowsCredentials)
    def delete(*args):
        error = OSError('Synthetic native credential error')
        error.winerror = code
        raise error
    backend.api = SimpleNamespace(CRED_TYPE_GENERIC=1, CredDelete=delete)
    if code == 1168:
        backend.remove_if_present('isolated', 'agent-key')
    else:
        with pytest.raises(OSError):
            backend.remove_if_present('isolated', 'agent-key')


@pytest.mark.parametrize('after', [None, 'still-present', 'unavailable'])
def test_keyring_deletion_uncertainty_requires_independent_absence(after):
    backend = object.__new__(SystemKeyring)
    values = iter(['initial', after])
    def get(*args):
        value = next(values)
        if value == 'unavailable':
            raise RuntimeError('Locked keyring')
        return value
    def delete(*args):
        raise RuntimeError('Uncertain delete response')
    backend.api = SimpleNamespace(get_password=get, delete_password=delete)
    if after is None:
        backend.remove_if_present('isolated', 'agent-key')
    else:
        with pytest.raises(RuntimeError):
            backend.remove_if_present('isolated', 'agent-key')


@pytest.mark.skipif(os.name != 'nt', reason='Actual Windows credential manager; synthetic isolated setup only')
def test_windows_participant_vault_compensation_and_absent_replay(setup, monkeypatch):
    import pywintypes
    s = setup
    backend = WindowsCredentials()
    monkeypatch.setattr(participant_client, 'open_backend', lambda: backend)
    reviewed = s.flow.review(s.selection, s.key)
    vault = s.flow.vault(reviewed['review'])
    try:
        s.flow.apply(reviewed, s.key, reviewed['review_revision'])
        saved = s.saves[-1]
        assert vault.call('load') == s.key
        flow = ParticipantRemoval(s.home, 'external', s.flow.save)
        planned = flow.review(saved)
        assert flow.apply(planned, planned['removal']['review_revision'])['state'] == 'removed'
        vault.call('remove')  # Native ERROR_NOT_FOUND is a safe absent replay.
        with pytest.raises(pywintypes.error) as missing:
            backend.api.CredRead(vault.service + '/agent-key', backend.api.CRED_TYPE_GENERIC)
        assert missing.value.winerror == 1168
        assert s.key not in Path(s.selection['config_file']).read_text()
        assert snapshot(s.deps) == s.before
    finally:
        backend.remove_if_present(vault.service, 'agent-key')
