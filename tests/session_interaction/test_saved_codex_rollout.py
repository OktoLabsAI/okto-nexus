"""Saved resume stages history without importing the source profile."""

import hashlib
import json
from dataclasses import replace

import pytest
from nexus_connector_core import CoreError, LaunchIntent, PreparedLaunch

from okto_nexus.application.execution_saved_resume import saved_opening_profile
from okto_nexus.bootstrap.embedded_codex_resume import _publish_rollout


@pytest.mark.parametrize('fork', [False, True])
def test_private_successor_publishes_only_exact_self_contained_rollout(tmp_path, fork):
    old_home, new_home = tmp_path / 'old', tmp_path / 'successor'
    source = old_home / 'sessions' / 'rollout-source.jsonl'
    source.parent.mkdir(parents=True)
    new_home.mkdir()
    (old_home / 'auth.json').write_text('synthetic-secret')
    (new_home / 'config.toml').write_text('successor settings')
    destination = new_home / 'sessions' / source.name
    metadata = {'id': 'exact-native'}
    if fork:
        metadata['history_base'] = {'thread_id': 'sibling'}
    header = json.dumps({'type': 'session_meta', 'payload': metadata}).encode()
    body = header + b'\n{"type":"response_item","payload":{"text":"fixture"}}\n'
    source.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    if fork:
        with pytest.raises(CoreError, match='CAPABILITY_UNSUPPORTED'):
            _publish_rollout(source, destination, new_home, digest)
        assert not destination.exists()
        return
    with pytest.raises(CoreError, match='PROFILE_DRIFT'):
        _publish_rollout(source, destination, new_home, '0' * 64)
    assert not destination.exists()
    _publish_rollout(source, destination, new_home, digest)
    identity = destination.stat().st_ino
    _publish_rollout(source, destination, new_home, digest)
    assert destination.read_bytes() == source.read_bytes() == body
    assert destination.stat().st_ino == identity and destination.stat().st_nlink == 1
    assert not (new_home / 'auth.json').exists() and not list(new_home.rglob('.nexus-rollout-*'))
    assert (new_home / 'config.toml').read_text() == 'successor settings'


def test_saved_profile_allows_a_fresh_capability_but_keeps_model_and_credentials_exact(tmp_path):
    intent = LaunchIntent('agent', 'workspace', 'codex_app_server', model='chosen-model')
    executable = str(tmp_path / 'codex.exe')
    # Codex receives its model in thread/resume, outside argv.
    prepared = PreparedLaunch(intent, None, (executable, 'app-server'), str(tmp_path), str(tmp_path),
                              'root-exact', 'old-profile', ('approved-credential', 'mcp-cap:old'))
    old = saved_opening_profile(prepared)['resume_configuration_sha256']
    successor = replace(prepared, profile_fingerprint='new-profile',
                        secret_refs=('approved-credential', 'mcp-cap:new'))
    assert saved_opening_profile(successor)['resume_configuration_sha256'] == old
    for changed in (replace(successor, intent=replace(intent, model='different-model')),
                    replace(successor, secret_refs=('changed-credential', 'mcp-cap:new'))):
        assert saved_opening_profile(changed)['resume_configuration_sha256'] != old
