"""Pending exact-profile fences over installed CLI and real HTTP/SQLite.

Only a response is lost: canonical Finish already committed. No native/provider
process, real account, fake authority DTO or workspace ACL is introduced.
"""
from collections import Counter
import hashlib
import json

import pytest
import test_quick_connect_cli as fixtures

local_setup = fixtures.local_setup
checking = fixtures.checking
terminal = fixtures.terminal
quick_cli = fixtures.quick_cli
isolated_provider_environment = fixtures.isolated_provider_environment


def database_fingerprints(c):
    with c.t.deps.connection_factory.unit_of_work(write=False) as uow:
        names = [row[0] for row in uow.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        assert len(names) <= 512
        result = {}
        for name in names:
            if name.startswith('telemetry'):
                continue
            rows = uow.connection.execute('SELECT * FROM "' + name.replace('"', '""') + '" LIMIT 2001').fetchall()
            assert len(rows) <= 2000, name
            encoded = [json.dumps({key: value for key, value in dict(row).items() if key != 'last_seen_at'},
                sort_keys=True, separators=(',', ':'), default=lambda value: value.hex() if isinstance(value, bytes) else str(value))
                for row in rows]
            result[name] = sorted(hashlib.sha256(value.encode()).hexdigest() for value in encoded)
        return result


def effect_posts(c):
    return Counter(path for method, path in c.t.calls if method == 'POST'
        and path.endswith(('setup:test', 'setup:finish', 'public-ids/reserve')))


@pytest.mark.parametrize('changed', ['harness', 'root', 'id'])
def test_pending_finish_rejects_changed_selector_then_recovers_same_receipt(quick_cli, tmp_path, capsys, changed):
    c = quick_cli
    base = ['connect', 'codex', 'Pending Project', '--profile', 'pending', '--id', 'held', '--json']
    review = fixtures.invoke(c, capsys, [*base, '--plan'])
    c.t.fault.after = 'setup:finish'
    uncertain = fixtures.invoke(c, capsys, [*base, '--approve', review['review_revision']], expected=3)
    assert uncertain['code'] == 'OUTCOME_UNKNOWN' and uncertain['possible_effect'] is True
    assert uncertain['quick_connect']['status'] == 'unknown'
    path = c.home / 'terminal/profiles/pending.json'
    checkpoint_bytes = path.read_bytes()
    pending = json.loads(checkpoint_bytes)
    assert pending['state'] == 'finish'
    intent = pending['request']['client_intent_id']
    with c.t.deps.connection_factory.unit_of_work(write=False) as uow:
        public = dict(uow.connection.execute("SELECT * FROM connection_public_ids WHERE connect_id='held'").fetchone())
        assert public['state'] == 'bound' and public['client_intent_id'] == intent
        reference = json.loads(public['canonical_ref_json'])
        assert uow.connection.execute('SELECT COUNT(*) FROM connection_setup_commits').fetchone()[0] == 1
    assert len(c.t.turns) == len(c.t.probes) == 1
    before = database_fingerprints(c)
    posts = effect_posts(c)
    other_root = tmp_path / 'other-approved-only-if-reviewed'
    other_root.mkdir()
    variants = {
        'harness': ['connect', 'claude', '--profile', 'pending', '--json'],
        'root': ['connect', '--profile', 'pending', '--project', str(other_root), '--json'],
        'id': ['connect', '--profile', 'pending', '--id', 'different-id', '--json'],
    }
    refused = fixtures.invoke(c, capsys, variants[changed], expected=3)
    assert refused['state'] == 'refused' and refused['code'] == 'PROFILE_CONFLICT'
    assert refused['possible_effect'] is False
    assert path.read_bytes() == checkpoint_bytes
    assert database_fingerprints(c) == before
    assert effect_posts(c) == posts and len(c.t.turns) == len(c.t.probes) == 1
    recovered = fixtures.invoke(c, capsys, ['connect', '--profile', 'pending', '--json'])
    assert recovered['quick_connect']['status'] == 'connected'
    assert recovered['quick_connect']['canonical_reference'] == reference
    assert recovered['setup_run_id'] == intent
    final = json.loads(path.read_bytes())
    assert final['state'] == 'done'
    for key in ('request', 'review_request', 'review_revision', 'server_id'):
        assert final[key] == pending[key], key
    assert final['result']['public_connection']['canonical_ref'] == reference
    assert final['result']['public_connection']['reservation_ref'] == public['reservation_ref']
    assert database_fingerprints(c) == before
    assert effect_posts(c) == posts and len(c.t.turns) == len(c.t.probes) == 1


def test_non_operator_http_denial_does_not_reveal_namespace_occupant(quick_cli, local_setup, capsys):
    c = quick_cli
    _, _, first = fixtures.first_connection(c, capsys, profile='first', name='Authorization Project', connect_id='occupied')
    reference = first['quick_connect']['canonical_reference']
    client, headers = local_setup[2:4]
    response = client.get('/api/v1/runtime-management/connections/public-ids',
        params={'workspace_id': reference['workspace_id'], 'connect_id': 'occupied'}, headers=headers['subject'])
    assert response.status_code == 403
    value = response.json()
    assert value['error']['code'] == 'PERMISSION_DENIED'
    assert 'items' not in value and 'canonical_ref' not in response.text
    for identifier in reference.values():
        assert identifier not in response.text
    assert str(c.project) not in response.text
    assert str(c.home) not in response.text
    assert 'provider_home' not in response.text and 'reservation_ref' not in response.text
    assert response.headers['cache-control'] == 'no-store'
    assert len(c.t.turns) == len(c.t.probes) == 1
