"""Saved resume stages history without importing the source profile."""

import hashlib
import json

import pytest
from nexus_connector_core import CoreError

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
