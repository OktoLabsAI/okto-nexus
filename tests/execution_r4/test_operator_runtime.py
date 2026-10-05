"""Operator requests keep actor provenance and the subject's execution grant."""
import pytest

from test_local_realization import local_setup
from test_embedded_dispatch import connected_local, wait_receipt


def resolve(setup, binding, identity='operator', intent_id='operator-open',
            intent='runtime.start', **options):
    return setup[2].post('/v1/runtime/intents:resolve', headers=setup[3][identity], json={
        'client_intent_id': intent_id, 'intent': intent, 'agent_id': 'subject',
        'binding_id': binding['binding_id'],
        'workspace_binding_id': binding['workspace_binding_id'], **options})


def submit(setup, resolution):
    return setup[2].post('/v1/runtime/operations', headers=setup[3]['operator'],
        json={k: resolution[k] for k in
              ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')})


def test_operator_complete_cycle_preserves_actor_and_subject(connected_local):
    setup, binding, native = connected_local
    response = resolve(setup, binding, new_session=True)
    assert response.status_code == 200, response.text
    opened = response.json()
    assert opened['scope']['agent_id'] == 'subject'
    assert submit(setup, opened).status_code == 202
    wait_receipt(setup, opened)
    assert submit(setup, opened).status_code == 200
    recovered = setup[2].get('/v1/runtime/intents/operator-open', headers=setup[3]['operator'])
    assert recovered.status_code == 200 and recovered.json()['operation']['operation_id'] == opened['operation_id']
    reused = resolve(setup, binding, intent_id='operator-reuse', session_id=opened['session_id'])
    assert reused.status_code == 200, reused.text
    assert reused.json()['reuse'] and submit(setup, reused.json()).status_code == 200
    actions = [('turn.submit', {'text': 'Operator requested turn'}),
               ('turn.steer', {'text': 'Continue', 'target': {'kind': 'native_turn_id', 'expected_turn_id': 'turn-from-native'}}),
               ('turn.interrupt', {'target': {'kind': 'current_run', 'expected_turn_id': None}}),
               ('runtime.close', {})]
    for index, (action, options) in enumerate(actions):
        response = resolve(setup, binding, intent_id=f'operator-action-{index}',
                           intent=action, session_id=opened['session_id'], **options)
        assert response.status_code == 200, response.text
        resolution = response.json()
        admitted = submit(setup, resolution)
        assert admitted.status_code == 202, admitted.text
        wait_receipt(setup, resolution, ('SUCCEEDED',) if action == 'runtime.close' else ('SUBMITTED', 'SUCCEEDED'))
    assert native.opens == 1 and native.native.stopped
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute('SELECT actor_agent_id,subject_agent_id FROM execution_operations').fetchall()
        assert len(rows) == 5 and all(tuple(row) == ('operator', 'subject') for row in rows)
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_execution_grants').fetchone()[0] == 1
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants').fetchone()[0] == 2


def test_nonoperator_cannot_represent_another_agent(connected_local):
    setup, binding, native = connected_local
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("INSERT INTO agents(agent_id,created_at) VALUES ('outsider',?)", (setup[0].clock.now_iso(),))
        setup[3]['outsider'] = {'Authorization': 'Bearer ' + setup[1].state.auth.issue_key(uow, agent_id='outsider')}
    response = resolve(setup, binding, identity='outsider', new_session=True)
    assert response.status_code in (403, 404), response.text
    assert native.opens == 0


def test_operator_authority_change_after_resolve_refuses_admission(connected_local):
    setup, binding, native = connected_local
    response = resolve(setup, binding, new_session=True)
    assert response.status_code == 200, response.text
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET permissions='{}' WHERE agent_id='operator'")
    response = submit(setup, response.json())
    assert response.status_code in (403, 409), response.text
    assert native.opens == 0


def test_operator_reuses_subject_opening_and_reads_its_receipt(connected_local):
    from test_embedded_dispatch import admit
    setup, binding, native = connected_local
    opened = admit(setup, binding, 'subject-opening', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    response = resolve(setup, binding, session_id=opened['session_id'])
    assert response.status_code == 200, response.text
    assert response.json()['reuse']
    assert submit(setup, response.json()).status_code == 200
    history = setup[2].get('/v1/runtime/intents/operator-open', headers=setup[3]['operator'])
    assert history.status_code == 200, history.text
    assert history.json()['operation']['operation_id'] == opened['operation_id']
    assert native.opens == 1


def test_operator_start_prompt_retains_provenance_for_both_operations(connected_local):
    setup, binding, native = connected_local
    response = resolve(setup, binding, new_session=True, text='Explicit initial turn')
    assert response.status_code == 200, response.text
    admitted = submit(setup, response.json())
    assert admitted.status_code == 202, admitted.text
    wait_receipt(setup, response.json())
    child, = admitted.json()['follow_up_operation_ids']
    wait_receipt(setup, {'operation_id': child})
    assert native.native.sent[0][0] == 'send_turn'
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        rows = uow.connection.execute('SELECT actor_agent_id,subject_agent_id FROM execution_operations').fetchall()
        assert len(rows) == 2 and all(tuple(row) == ('operator', 'subject') for row in rows)
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_client_intents WHERE actor_guard_digest IS NOT NULL').fetchone()[0] == 2


@pytest.mark.parametrize('mutation', [
    "UPDATE agents SET permissions='{}' WHERE agent_id='operator'",
    "UPDATE runtime_execution_grants SET revoked_at='2026-01-01T00:00:00Z'",
])
def test_operator_change_or_subject_grant_revocation_refuses_dispatch(connected_local, mutation):
    from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
    setup, binding, native = connected_local
    owner = setup[1].state.embedded_dispatch_owner
    setup[2].portal.call(owner.pump.stop)
    response = resolve(setup, binding, new_session=True)
    assert response.status_code == 200, response.text
    assert submit(setup, response.json()).status_code == 202
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute(mutation)
    # Exercise the same pre-send gate used by the embedded pump, before native I/O.
    from okto_nexus.errors import OktoNexusError
    pump = owner.pump
    reservation = reserve_execution_dispatch(setup[0].connection_factory,
        server_id=pump.channel.server_id, executor_id=binding['executor_id'],
        remote_ready=True, channel=pump.channel)
    assert reservation is not None
    with pytest.raises(OktoNexusError):
        begin_execution_send(setup[0].connection_factory, reservation=reservation,
            remote_ready=True, channel=pump.channel,
            access=pump.access, fresh_publications=setup[1].state.inventory_fresh_publications)
    assert native.opens == 0


def test_operator_change_invalidates_lease_and_capability_authority(connected_local):
    import json
    from okto_nexus.application.execution_capabilities import ExecutionCapabilityService
    from okto_nexus.errors import OktoNexusError
    setup, binding, native = connected_local
    opened = resolve(setup, binding, new_session=True).json()
    assert submit(setup, opened).status_code == 202
    wait_receipt(setup, opened)
    owner = setup[1].state.embedded_dispatch_owner
    with setup[0].connection_factory.unit_of_work() as uow:
        lease = dict(uow.connection.execute('SELECT * FROM execution_leases ORDER BY lease_serial DESC LIMIT 1').fetchone())
        service = ExecutionCapabilityService(factory=setup[0].connection_factory, access=owner.pump.access)
        service._authority(uow, opened['scope'], grant_id=lease['grant_id'])
        uow.connection.execute("UPDATE agents SET permissions='{}' WHERE agent_id='operator'")
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        with pytest.raises(OktoNexusError, match='operator authority changed'):
            service._authority(uow, opened['scope'], grant_id=lease['grant_id'])
    with pytest.raises(OktoNexusError, match='operator authority changed'):
        owner.leases.issue(json.loads(lease['request_json']), channel=owner.pump.channel)
    assert native.opens == 1


def test_actor_namespace_and_schema_are_preserved(connected_local):
    import json
    from pathlib import Path
    from jsonschema import Draft202012Validator
    setup, binding, native = connected_local
    first = resolve(setup, binding, new_session=True)
    assert first.status_code == 200, first.text
    second = resolve(setup, binding, identity='subject', new_session=True)
    assert second.status_code == 200, second.text
    assert first.json()['operation_id'] != second.json()['operation_id']
    schema = json.loads((Path(__file__).parents[2] / 'plans/contratos/http-target.schema.json').read_text())
    Draft202012Validator({'$defs': schema['$defs'], **schema['$defs']['IntentResolution']}).validate(first.json())
    changed = resolve(setup, binding, new_session=True, text='Different content')
    assert changed.status_code == 409
    assert native.opens == 0


def test_operator_start_projection_requires_subject_grant(connected_local):
    setup, binding, native = connected_local
    from urllib.parse import urlencode
    url = '/v1/agents/subject/runtime-options?' + urlencode({
        'executor_id': binding['executor_id'], 'workspace_id': binding['workspace_id']})
    def choice():
        response = setup[2].get(url, headers=setup[3]['operator'])
        assert response.status_code == 200, response.text
        return next(item for item in response.json()['options'] if item['candidate_ref'] == binding['candidate_ref'])
    before = choice()
    # This local fixture has no native version observation. Authorization is
    # available, but technical readiness must remain a separate refusal.
    assert not before['can_start'] and 'TECHNICAL_NOT_READY' in before['policy_reasons']
    assert 'AUTHORIZATION_REQUIRED' not in before['policy_reasons']
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='2026-01-01T00:00:00Z'")
    row = choice()
    assert not row['can_start'] and 'AUTHORIZATION_REQUIRED' in row['policy_reasons']
    assert native.opens == 0
