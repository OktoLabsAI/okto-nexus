"""External activity cannot admit or settle the existing managed work flow.

HTTP, SQLite, Core and the dispatch owner are real; the native provider is the
existing explicitly synthetic peer. These contracts do not qualify real M1.
"""
import json
import time

import pytest

from test_harness_canonical import qualified_bridge as qualified_bridge_fixture
from test_embedded_dispatch import (
    local_setup as local_setup_fixture, qualified_contract as qualified_contract_fixture,
    connect_local, admit, wait_receipt,
)
from test_canonical_delivery import enable, send
from test_canonical_result_publication import current_turn, emit


qualified_bridge = qualified_bridge_fixture
local_setup = local_setup_fixture
qualified_contract = qualified_contract_fixture
MANAGEMENT = '/api/v1/observations'
PUBLISH = '/v1/observations/activity'


@pytest.fixture
def observed_runtime(local_setup):
    from okto_nexus.domain.ids import resolve_workspace_id
    deps, app, client, headers, body, _, root = local_setup
    deps.config.feature_observations = True
    deps.config.feature_attention = True
    workspace = resolve_workspace_id(str(root))
    # Test setup precedes canonical binding/grant creation, so no live authority
    # is repaired or bypassed after changing the subject's explicit permissions.
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id=workspace, root_realpath=str(root),
                                    last_seen_at=deps.clock.now_iso())
        stored = uow.connection.execute("SELECT permissions FROM agents WHERE agent_id='subject'").fetchone()[0]
        permissions = json.loads(stored) if stored else {}
        permissions['observations'] = dict(manage_self=True, publish=True)
        deps.repos.agents.set_permissions(uow, agent_id='subject', preset_id=None, permissions=permissions)
    body['workspace_id'] = workspace
    setup, binding, native = connect_local(local_setup)
    enable(setup, binding)
    response = client.post(MANAGEMENT + '/sources', headers=headers['operator'], json=dict(
        agent_id='subject', source_kind='custom', workspace_ids=[workspace], registration_ref='runtime-isolation'))
    assert response.status_code == 200, response.text
    source = response.json()['data']['source']
    path = MANAGEMENT + '/sources/' + source['source_id']
    response = client.post(path + '/instances', headers=headers['operator'], json=dict(
        expected_revision=source['revision'], workspace_id=workspace, external_instance_ref='separate-terminal'))
    assert response.status_code == 200, response.text
    instance = response.json()['data']['instance']
    response = client.post(path + '/tokens', headers=headers['operator'], json=dict(
        expected_revision=source['revision'], instance_grants=[dict(
            observed_instance_id=instance['observed_instance_id'], generation=instance['generation'])]))
    assert response.status_code == 200, response.text
    token = response.json()['data']['token']
    sequence = 0

    def publish(state, **extra):
        nonlocal sequence
        sequence += 1
        return client.post(PUBLISH, headers={'Authorization': 'Bearer ' + token}, json=dict(
            schema_version=1, source_id=source['source_id'], observed_instance_id=instance['observed_instance_id'],
            generation=instance['generation'], sequence=sequence, state=state, evidence='inferred',
            observed_at=deps.clock.now_iso(), **extra))

    return setup, binding, native, publish


@pytest.mark.parametrize('disable_observations', [False, True])
def test_external_done_and_seen_do_not_release_a_turn_or_wake_queued_work(observed_runtime, monkeypatch, disable_observations):
    setup, binding, native, publish = observed_runtime
    deps, _, client, headers, *_ = setup
    for state in ('working', 'blocked', 'idle'):
        response = publish(state)
        assert response.status_code == 200, response.text
    with deps.connection_factory.unit_of_work(write=False) as uow:
        for table in ('messages', 'message_deliveries', 'delivery_outbox', 'execution_operations',
                      'execution_sessions', 'handoffs', 'approvals'):
            assert uow.connection.execute('SELECT count(*) FROM ' + table).fetchone()[0] == 0, table
    assert native.opens == 0
    if disable_observations:
        deps.config.feature_observations = False
        assert publish('blocked').status_code == 409
    first = send(setup, monkeypatch)
    assert first['ok'], first
    turn = current_turn(setup)
    wait_receipt(setup, turn, stages=('SUBMITTED',))
    second = send(setup, monkeypatch)
    assert second['ok'], second
    assert native.opens == 1 and len(native.native.sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        admitted_turns = {row[0] for row in uow.connection.execute(
            "SELECT operation_id FROM execution_operations WHERE action='turn.submit'")}
    assert len(admitted_turns) == 2 and turn['operation_id'] in admitted_turns
    queued_turn, = admitted_turns - {turn['operation_id']}

    if not disable_observations:
        response = publish('idle', current_completion_ref='terminal-done-is-not-work-result')
        assert response.status_code == 200, response.text
        response = client.get('/api/v1/attention?kind=external_completion_unseen', headers=headers['operator'])
        assert response.status_code == 200, response.text
        items = response.json()['data']['items']
        assert len(items) == 1 and items[0]['allowed_actions'] == ['inspect_external_observation']
        item = items[0]
        response = client.post('/api/v1/attention/' + item['attention_id'] + '/seen', headers=headers['operator'],
            json=dict(source_revision=item['source_revision'], preference_revision=item['seen_state']['revision'], seen=True))
        assert response.status_code == 200, response.text
    response = client.get(MANAGEMENT + '/summary', headers=headers['operator'])
    assert response.status_code == 200, response.text
    assert response.json()['data']['activity']['unknown' if disable_observations else 'idle'] == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        receipts = uow.connection.execute('SELECT stage FROM execution_receipts WHERE operation_id=? '
            'ORDER BY receipt_revision DESC LIMIT 1', (turn['operation_id'],)).fetchone()
        assert receipts[0] == 'SUBMITTED'
        assert {row[0] for row in uow.connection.execute(
            "SELECT operation_id FROM execution_operations WHERE action='turn.submit'")} == admitted_turns
        assert uow.connection.execute('SELECT count(*) FROM execution_receipts WHERE operation_id=? '
            "AND stage IN ('SUBMITTED','RUNNING','SUCCEEDED')", (queued_turn,)).fetchone()[0] == 0
        assert uow.connection.execute('SELECT count(*) FROM delivery_outbox').fetchone()[0] == 2
        assert uow.connection.execute('SELECT count(*) FROM runtime_results').fetchone()[0] == 0
    assert native.opens == 1 and len(native.native.sent) == 1

    # Only the correlated canonical native event settles this turn and permits
    # the queued logical delivery to reach its existing managed session.
    emit(setup, native, turn, 'A canonical synthetic result.')
    deadline = time.monotonic() + 15
    while len(native.native.sent) < 2:
        assert time.monotonic() < deadline, 'Queued work did not resume after the canonical terminal event'
        time.sleep(.02)
    assert native.opens == 1 and len(native.native.sent) == 2
    closed = admit(setup, binding, 'observation-isolation-close', 'runtime.close', session_id=turn['session_id'])
    wait_receipt(setup, closed, stages=('SUCCEEDED',))
