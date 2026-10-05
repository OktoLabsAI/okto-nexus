"""The real keyless dashboard joins scoped Core execution without minted keys."""
import pytest

from test_embedded_dispatch import local_setup, connected_local, qualified_contract, wait_receipt, admit
from test_canonical_result_publication import emit, wait_result, current_turn
from okto_nexus.domain.base import iso_plus
from okto_nexus.domain.runtime_context import RuntimeRequestContext
from okto_nexus.errors import OktoNexusError
from okto_nexus.application.runtime_actor_authority import authenticated_message_context, valid_actor_binding

PREFIX = '/api/v1/runtime-management'


def keyless(setup):
    deps, app, *_ = setup
    app.state.local_open = True
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET api_key_hash=NULL WHERE agent_id='operator'")


def resolve(setup, binding, intent_id, intent='runtime.start', **options):
    return setup[2].post(PREFIX + '/runtime/intents:resolve', json={
        'client_intent_id': intent_id, 'agent_id': 'subject', 'intent': intent,
        'binding_id': binding['binding_id'], 'workspace_binding_id': binding['workspace_binding_id'], **options})


def submit(setup, resolution):
    return setup[2].post(PREFIX + '/runtime/operations', json={key: resolution[key] for key in
        ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')})


def test_keyless_operator_start_turn_close_preserves_provenance(connected_local):
    setup, binding, native = connected_local
    keyless(setup)
    response = resolve(setup, binding, 'local-open', new_session=True, text='Hello')
    assert response.status_code == 200, response.text
    opened = response.json()
    accepted = submit(setup, opened)
    assert accepted.status_code == 202, accepted.text
    wait_receipt(setup, opened)
    child, = accepted.json()['follow_up_operation_ids']
    wait_receipt(setup, {'operation_id': child})
    closed = resolve(setup, binding, 'local-close', 'runtime.close', session_id=opened['session_id']).json()
    assert submit(setup, closed).status_code == 202
    wait_receipt(setup, closed, stages=('SUCCEEDED',))
    assert native.opens == 1 and native.native.stopped
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT api_key_hash FROM agents WHERE agent_id='operator'").fetchone()[0] is None
        assert all(row[0].startswith('local-operator:sha256:') for row in
                   uow.connection.execute('SELECT actor_guard_digest FROM execution_client_intents'))
        assert all(tuple(row) == ('operator', 'subject') for row in
                   uow.connection.execute('SELECT actor_agent_id,subject_agent_id FROM execution_operations'))


@pytest.mark.parametrize('mutation', [
    "UPDATE agents SET is_active=0 WHERE agent_id='operator'",
    "UPDATE agents SET permissions='{}' WHERE agent_id='operator'",
])
def test_local_authority_and_subject_grant_revalidated(connected_local, mutation):
    setup, binding, native = connected_local
    keyless(setup)
    resolved = resolve(setup, binding, 'review-before-change', new_session=True).json()
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute(mutation)
    refused = submit(setup, resolved)
    assert refused.status_code in (403, 409), refused.text
    assert native.opens == 0


def test_local_subject_grant_revocation_refuses_native_dispatch(connected_local):
    from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
    setup, binding, native = connected_local
    keyless(setup)
    pump = setup[1].state.embedded_dispatch_owner.pump
    setup[2].portal.call(pump.stop)
    resolved = resolve(setup, binding, 'revoked-before-send', new_session=True).json()
    assert submit(setup, resolved).status_code == 202
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE runtime_execution_grants SET revoked_at='2000-01-01T00:00:00Z'")
    reservation = reserve_execution_dispatch(setup[0].connection_factory,
        server_id=pump.channel.server_id, executor_id=binding['executor_id'],
        remote_ready=True, channel=pump.channel)
    assert reservation is not None
    with pytest.raises(OktoNexusError):
        begin_execution_send(setup[0].connection_factory, reservation=reservation,
            remote_ready=True, channel=pump.channel, access=pump.access,
            fresh_publications=setup[1].state.inventory_fresh_publications)
    assert native.opens == 0


def test_meta_harness_policy_opt_in_reaches_core_and_publishes_reply(connected_local):
    setup, binding, native = connected_local
    deps, _, client, headers, *_ = setup
    keyless(setup)
    path = f"/api/v1/harness/endpoints/{binding['endpoint_id']}/conversation-policy"
    policy = client.get(path).json()['data']
    assert not policy['enabled']
    body = {'expected_revision': policy['revision'], 'enabled': True}
    assert client.put(path, json=body, headers=headers['subject']).status_code == 403
    configured = client.put(path, json=body)
    assert configured.status_code == 200, configured.text
    assert client.put(path, json=body).status_code == 409
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT revoked_at FROM runtime_execution_grants').fetchone()[0]
        row = uow.connection.execute('SELECT public_config FROM agent_endpoints').fetchone()[0]
        assert 'automatic-local' in row
    grant = client.post('/api/v1/harness/grants', json={
        'actor_agent_id': 'subject', 'endpoint_id': binding['endpoint_id'],
        'actions': ['open','send','interrupt','close'], 'max_executions': 10,
        'expires_at': iso_plus(deps.clock.now_iso(), 600)})
    assert grant.status_code == 200, grant.text
    message = client.post('/api/v1/meta-harness/send', json={
        'workspace': policy['workspace_id'], 'kind':'message', 'audience':'private',
        'to_agent_id':'subject', 'subject':'Local UI turn', 'body':'Reply TEST_OK', 'artifact_ids':[]})
    assert message.status_code == 200, message.text
    turn = current_turn(setup)
    wait_receipt(setup, turn)
    assert native.opens == 1
    emit(setup, native, turn, 'TEST_OK')
    result = wait_result(setup, 'PUBLISHED')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        reply = uow.connection.execute('SELECT body,parent_message_id FROM messages WHERE message_id=?',
                                       (result['publication_message_id'],)).fetchone()
        assert tuple(reply) == ('TEST_OK', message.json()['data']['message_id'])
        binding_proof = uow.connection.execute('SELECT credential_binding FROM delivery_outbox').fetchone()[0]
        actor = deps.repos.agents.get(uow, 'operator')
        assert valid_actor_binding(uow, actor, binding_proof)
        # A stored local provenance marker cannot authenticate an API client.
        with pytest.raises(OktoNexusError, match='Authenticated delivery actor'):
            authenticated_message_context(uow, RuntimeRequestContext('operator', 'agent_key', credential_binding=binding_proof), deps.repos.agents)
    wait_receipt(setup, admit(setup,binding,'local-result-close','runtime.close',session_id=turn['session_id']), stages=('SUCCEEDED',))
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET permissions='{}' WHERE agent_id='operator'")
        assert not valid_actor_binding(uow, deps.repos.agents.get(uow, 'operator'), binding_proof)


@pytest.mark.parametrize('headers', [{'Origin':'https://untrusted.example'}, {'Host':'rebound.example', 'Sec-Fetch-Site':'same-origin'}, {'Authorization':'Bearer bad'}])
def test_keyless_execution_rejects_untrusted_request(connected_local, headers):
    setup, binding, native = connected_local
    keyless(setup)
    response = setup[2].post(PREFIX+'/runtime/intents:resolve', headers=headers, json={
        'client_intent_id':'untrusted','agent_id':'subject','intent':'runtime.start',
        'binding_id':binding['binding_id'],'workspace_binding_id':binding['workspace_binding_id']})
    assert response.status_code in (401,403), response.text
    assert native.opens == 0
