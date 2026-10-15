"""Compatibility annotations belong to one durable session, not its identity."""
import json
from dataclasses import asdict

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_canonical_grant_regressions import mcp_helpers
from test_pr34_remediation import tool


@pytest.mark.parametrize('surface', ['rest', 'mcp'])
def test_session_metadata_is_durable_opaque_and_idempotent(connected_local, surface):
    setup, binding, native = connected_local
    deps, _, client, headers, *_, root = setup
    client.headers['host'] = '127.0.0.1:8000'
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET role='reviewer',metadata=? WHERE agent_id='subject'", ('{"keep":"profile"}',))
        before = asdict(deps.repos.agents.get(uow, 'subject'))
    body = dict(agent_id='subject', kind='codex', project_root=str(root),
                endpoint_id=binding['endpoint_id'], idempotency_key='metadata-opening')
    def opening(**changes):
        args = dict(body, **changes)
        if surface == 'rest':
            return client.post('/api/v1/harness/sessions', headers=headers['subject'], json=args).json()
        return tool(client, headers['subject']['Authorization'].removeprefix('Bearer '), 'harness_open', args)
    mismatch = opening(role='admin')
    assert not mismatch['ok'] and mismatch['error']['code'] == 'VALIDATION_ERROR', mismatch
    assert native.opens == 0
    metadata = dict(connection_note='fixture', role='admin', agent_id='operator', configuration_revision=999)
    opened = opening(role='reviewer', metadata=metadata if surface == 'rest' else json.dumps(metadata))
    assert opened.get('ok') and opened['data']['metadata'] == metadata, opened
    wait_receipt(setup, opened['data'])
    sid = opened['data']['scope']['session_id']
    repeated = opening(role='reviewer', metadata=metadata)
    assert repeated['ok'] and repeated['data']['operation_id'] == opened['data']['operation_id'], repeated
    changed = opening(metadata=dict(metadata, connection_note='changed'))
    assert not changed['ok'] and changed['error']['code'] == 'CONFLICT', changed
    wait_receipt(setup, admit(setup, binding, 'metadata-close', 'runtime.close', session_id=sid), stages=('SUCCEEDED',))
    inspected = client.get('/api/v1/harness/sessions/' + sid, headers=headers['subject'])
    assert inspected.status_code == 200 and inspected.json()['data']['metadata'] == metadata, inspected.text
    assert inspected.json()['data']['scope']['agent_id'] == 'subject'
    intent = client.get('/v1/runtime/intents/metadata-opening', headers=headers['subject'])
    assert intent.status_code == 200, intent.text
    assert '_session_metadata' not in intent.json()['resolution']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        after = asdict(deps.repos.agents.get(uow, 'subject'))
        before.pop('last_seen_at')
        after.pop('last_seen_at')
        assert after == before
        operation = json.loads(uow.connection.execute("SELECT semantic_payload FROM execution_operations WHERE action='runtime.open'").fetchone()[0])
        assert 'metadata' not in operation['payload'] and '_session_metadata' not in operation['payload']
    assert native.opens == 1


@pytest.mark.parametrize('metadata', ['[]', '{', {'note': 'x' * 16384}])
def test_invalid_session_metadata_has_no_native_effect(connected_local, metadata):
    setup, binding, native = connected_local
    response = setup[2].post('/api/v1/harness/sessions', headers=setup[3]['subject'], json=dict(
        agent_id='subject', kind='codex', endpoint_id=binding['endpoint_id'], project_root=str(setup[-1]),
        idempotency_key='invalid-metadata', metadata=metadata))
    assert response.status_code == 422, response.text
    assert native.opens == 0
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM execution_sessions').fetchone()[0] == 0
