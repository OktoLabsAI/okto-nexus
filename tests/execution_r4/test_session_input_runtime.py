"""Exercise the serve-owned queue against real R4/Core with a synthetic peer."""

from dataclasses import replace

import pytest
import test_local_realization as local_realization
from nexus_connector_core import RuntimeEvent
from test_agent_recovery_isolation import eventually
from test_embedded_dispatch import admit, connect_local, wait_receipt

from okto_nexus.application.session_interaction_authority import enqueue_human_input
from okto_nexus.application.session_interaction_capability import next_turn_revision
from okto_nexus.bootstrap.execution_authority import build_execution_access
from okto_nexus.domain.execution.keys import SessionKey, SessionOwnerGeneration
from okto_nexus.domain.session_interaction import InputAuthor, InputScope

local_setup = local_realization.local_setup


@pytest.fixture
def interactive_runtime(monkeypatch, request):
    from nexus_connector_core import availability

    app_for = local_realization.app_for
    candidate = local_realization.InstallationCandidate

    def configure(home):
        deps, app = app_for(home)
        deps.config.runtime_session_interaction_enabled = True
        return deps, app

    def qualified_candidate(*args):
        return replace(candidate(*args), version='0.159.0', architecture='x86_64')

    monkeypatch.setattr(local_realization, 'app_for', configure)
    monkeypatch.setattr(local_realization, 'InstallationCandidate', qualified_candidate)
    monkeypatch.setattr(availability, 'qualified_build', lambda *_args, **_kwargs: True)
    return connect_local(request.getfixturevalue('local_setup'))


def test_server_dispatches_queue_after_busy_boundary_without_handoff_acquisition(interactive_runtime):
    setup, binding, native = interactive_runtime
    deps, app, client, *_ = setup
    assert not deps.config.runtime_handoff_auto_claim_enabled
    assert app.state.handoff_runtime_service.scheduler is None
    assert app.state.embedded_core_host.capacity_enabled
    opened = admit(setup, binding, 'interactive-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    original = opened['scope']
    scope = InputScope(SessionKey(original['server_id'], original['executor_id'], original['session_id']),
        SessionOwnerGeneration(original['session_owner_generation']), original['binding_id'], original['workspace_id'],
        original['workspace_binding_id'], original['agent_id'])
    factory = deps.connection_factory
    options = app.state.session_input_dispatch_options
    capability = options['session_input_capability_revision']

    def revision():
        with factory.unit_of_work(write=False) as uow:
            return capability(uow, scope)

    eventually(revision)
    capability_revision = revision()
    with factory.unit_of_work(write=False) as uow:
        assert next_turn_revision(uow, scope, availability=deps.runtime_availability, fresh_publications={}) is None
        replaced = replace(scope, generation=SessionOwnerGeneration(scope.generation.value + 1))
        assert capability(uow, replaced) is None
    auth = app.state.operator_auth
    assert auth.configure('queue-fixture', 'fixture-password-long', local=True)
    token = auth.login('queue-fixture', 'fixture-password-long')
    author = InputAuthor(auth.authority_reference(token), 'web')
    ordinary = admit(setup, binding, 'busy-turn', 'turn.submit',
                     session_id=scope.session.session_id, text='Ordinary synthetic turn')
    wait_receipt(setup, ordinary)

    def enqueue(text):
        return enqueue_human_input(factory=factory, access=build_execution_access(deps),
            authority_fence=auth.authority_fence, scope=scope, author=author, client_intent_id=text, text=text,
            current_capability_revision=capability, capability_revision=capability_revision)

    first, second = enqueue('first synthetic input'), enqueue('second synthetic input')

    def inputs():
        with factory.unit_of_work(write=False) as uow:
            return [dict(row) for row in uow.connection.execute(
                'SELECT input_id,status,operation_id,capacity_state FROM session_interaction_inputs '
                'ORDER BY enqueue_sequence')]

    assert [row['operation_id'] for row in inputs()] == [None, None]
    assert native.native.sent == [('send_turn', ordinary['operation_id'])]
    assert first.sequence < second.sequence

    def settled(operation_id):
        with factory.unit_of_work(write=False) as uow:
            stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams WHERE session_id=?',
                                                (scope.session.session_id,)).fetchone())
        client.portal.call(native.native.queue.put, RuntimeEvent(
            stream['server_id'], stream['executor_id'], stream['session_id'], stream['stream_epoch'], 0,
            'turn_state', 'fixture.interactive.complete',
            {'delivery_phase': 'terminal', 'delivery_outcome': 'success', 'output_text': 'Completed fixture turn'},
            operation_id=operation_id))

    settled(ordinary['operation_id'])
    eventually(lambda: len(native.native.sent) == 2)
    after_first = inputs()
    assert after_first[0]['capacity_state'] == 'CONSUMED' and after_first[1]['operation_id'] is None
    assert native.native.sent[-1] == ('send_turn', after_first[0]['operation_id'])
    settled(after_first[0]['operation_id'])
    eventually(lambda: len(native.native.sent) == 3)
    after_second = inputs()
    assert after_second[1]['capacity_state'] == 'CONSUMED'
    assert native.native.sent[-1] == ('send_turn', after_second[1]['operation_id'])
    assert after_first[0]['operation_id'] != after_second[1]['operation_id']
    assert enqueue('first synthetic input').operation_id == after_first[0]['operation_id']
    pending = enqueue('revoked synthetic input')
    auth.logout(token)
    settled(after_second[1]['operation_id'])
    eventually(lambda: inputs()[-1]['status'] == 'BLOCKED_AUTH')
    assert inputs()[-1] == {'input_id': pending.input_id, 'status': 'BLOCKED_AUTH',
                           'operation_id': None, 'capacity_state': None}
    assert len(native.native.sent) == 3


def test_dashboard_admits_exact_input_once_under_the_original_human_login(interactive_runtime):
    setup, binding, native = interactive_runtime
    deps, app, client, headers, *_ = setup
    opened = admit(setup, binding, 'dashboard-input-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    scope = opened['scope']
    fields = ('server_id', 'executor_id', 'binding_id', 'workspace_id', 'workspace_binding_id', 'agent_id')
    exact = {key: scope[key] for key in fields}
    generation = scope['session_owner_generation']
    session = scope['session_id']
    path = f'/api/v1/runtime-management/runtime/sessions/{session}'
    query = {**exact, 'expected_session_generation': generation}

    def interaction():
        response = client.get(path + '/interaction', params=query)
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
        return response.json()['next_turn']

    eventually(lambda: interaction()['supported'])
    capability = interaction()
    assert capability['human_login_required']
    body = {'scope': {**exact, 'session_id': session}, 'expected_session_generation': generation,
            'capability_revision': capability['capability_revision'], 'client_intent_id': 'dashboard-input',
            'content': [{'type': 'text', 'text': 'Synthetic dashboard message'}]}
    ui = {'x-nexus-ui': '1'}
    assert client.post(path + '/inputs', json=body, headers=ui).status_code == 401
    assert client.post(path + '/inputs', json=body, headers=ui | headers['operator']).status_code == 401

    auth = app.state.operator_auth
    assert auth.configure('dashboard-fixture', 'fixture-password-long', local=True)
    token = auth.login('dashboard-fixture', 'fixture-password-long')
    client.cookies.set('nexus_operator_session', token)
    assert interaction()['human_login_required'] is False
    stale = client.get(path + '/interaction', params=query | {'expected_session_generation': generation + 1})
    assert stale.status_code == 404
    assert client.post(path + '/inputs', json=body, headers=ui | {'origin': 'https://foreign.invalid'}).status_code == 403
    invalid = client.post(path + '/inputs', json=body | {'actor_agent_id': 'fixture-uncopied'}, headers=ui)
    assert invalid.status_code == 422 and 'fixture-uncopied' not in invalid.text
    for text in ('  /unknown', '!fixture'):
        command = client.post(path + '/inputs', json=body | {'content': [{'type': 'text', 'text': text}]}, headers=ui)
        assert command.status_code == 422 and text not in command.text
    assert client.post(path + '/inputs', json=body | {'capability_revision': 'stale'}, headers=ui).status_code == 409
    first = client.post(path + '/inputs', json=body, headers=ui)
    assert first.status_code == 202, first.text
    assert first.headers['cache-control'] == 'no-store'
    retained = first.json()
    assert retained['scope'] == body['scope'] and retained['status'] == 'QUEUED'
    assert retained['operation_id'] is None and not retained['possible_effect']
    eventually(lambda: len(native.native.sent) == 1)
    receipt_query = query | {'client_intent_id': body['client_intent_id']}
    receipt = client.get(path + '/inputs/receipt', params=receipt_query)
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()['input_id'] == retained['input_id']
    assert receipt.json()['operation_id'] == native.native.sent[0][1]
    retry = client.post(path + '/inputs', json=body, headers=ui)
    assert retry.status_code == 202 and retry.json()['input_id'] == retained['input_id']
    assert retry.json()['operation_id'] == native.native.sent[0][1]
    other_login = auth.login('dashboard-fixture', 'fixture-password-long')
    client.cookies.set('nexus_operator_session', other_login)
    assert client.get(path + '/inputs/receipt', params=receipt_query).status_code == 404
    assert auth.authority_reference(other_login, create=False) is None
    client.cookies.set('nexus_operator_session', token)
    auth.logout(token)
    assert client.post(path + '/inputs', json=body, headers=ui).status_code == 401
    assert client.get(path + '/inputs/receipt', params=receipt_query).status_code == 401
    client.cookies.clear()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM session_interaction_inputs').fetchone()[0] == 1


def test_dashboard_queue_pages_and_cancels_only_the_original_human_input(interactive_runtime):
    setup, binding, native = interactive_runtime
    deps, app, client, *_ = setup
    opened = admit(setup, binding, 'dashboard-queue-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    scope = opened['scope']
    exact = {key: scope[key] for key in ('server_id', 'executor_id', 'binding_id', 'workspace_id',
                                        'workspace_binding_id', 'agent_id', 'session_id')}
    generation = scope['session_owner_generation']
    session = exact['session_id']
    path = f'/api/v1/runtime-management/runtime/sessions/{session}'
    query = {key: value for key, value in exact.items() if key != 'session_id'}
    query['expected_session_generation'] = generation
    ui = {'x-nexus-ui': '1'}
    assert client.get(path + '/inputs', params=query).status_code == 401

    auth = app.state.operator_auth
    assert auth.configure('queue-fixture', 'fixture-password-long', local=True)
    token = auth.login('queue-fixture', 'fixture-password-long')
    client.cookies.set('nexus_operator_session', token)
    queue = client.get(path + '/inputs', params=query)
    assert queue.status_code == 200 and queue.headers['cache-control'] == 'no-store'
    assert queue.json()['items'] == [] and queue.json()['queue_revision'] == 0
    assert auth.authority_reference(token, create=False) is None
    assert client.get(path + '/inputs', params=query | {'limit': 51}).status_code == 422
    assert client.get(path + '/inputs', params=query | {'expected_session_generation': generation + 1}).status_code == 404

    def capability():
        metadata = client.get(path + '/interaction', params=query)
        assert metadata.status_code == 200
        return metadata.json()['next_turn']['capability_revision']

    eventually(capability)
    body = {'scope': exact, 'expected_session_generation': generation, 'capability_revision': capability()}
    busy = admit(setup, binding, 'dashboard-queue-busy', 'turn.submit', session_id=session, text='Busy synthetic turn')
    wait_receipt(setup, busy)

    def enqueue(intent):
        response = client.post(path + '/inputs', headers=ui, json=body | {
            'client_intent_id': intent, 'content': [{'type': 'text', 'text': 'Private synthetic input ' + intent}],
        })
        assert response.status_code == 202, response.text
        return response.json()['input_id']

    first, second = enqueue('first'), enqueue('second')
    page = client.get(path + '/inputs', params=query | {'limit': 1})
    assert page.status_code == 200 and 'Private synthetic input' not in page.text
    data = page.json()
    assert not data['paused'] and data['scope'] == exact
    assert data['items'][0]['input_id'] == first and data['items'][0]['can_cancel']
    cursor = data['next_cursor']
    following = client.get(path + '/inputs', params=query | {'cursor': cursor}).json()
    assert [item['input_id'] for item in following['items']] == [second] and following['next_cursor'] is None
    assert client.get(path + '/inputs', params=query | {'cursor': cursor, 'agent_id': 'another'}).status_code == 422

    cancel_path = path + f'/inputs/{first}/cancel'
    cancellation = body | {'expected_queue_revision': data['queue_revision'],
        'expected_input_revision': data['items'][0]['input_revision'],
        'capability_revision': data['cancel_capability_revision']}
    assert client.post(cancel_path, headers=ui | {'origin': 'https://foreign.invalid'}, json=cancellation).status_code == 403
    other_login = auth.login('queue-fixture', 'fixture-password-long')
    client.cookies.set('nexus_operator_session', other_login)
    foreign = client.get(path + '/inputs', params=query)
    assert foreign.status_code == 200 and not any(item['can_cancel'] for item in foreign.json()['items'])
    assert client.post(cancel_path, headers=ui, json=cancellation).status_code == 404
    assert auth.authority_reference(other_login, create=False) is None

    client.cookies.set('nexus_operator_session', token)
    third = enqueue('third')
    assert client.post(cancel_path, headers=ui, json=cancellation).status_code == 409
    current = client.get(path + '/inputs', params=query).json()
    removed = client.post(cancel_path, headers=ui, json=cancellation | {
        'expected_queue_revision': current['queue_revision'],
    })
    assert removed.status_code == 200, removed.text
    assert removed.json()['status'] == 'CANCELLED' and removed.json()['operation_id'] is None
    visible = client.get(path + '/inputs', params=query).json()['items']
    assert [(item['input_id'], item['status'], item['can_cancel']) for item in visible] == [
        (first, 'CANCELLED', False), (second, 'QUEUED', True), (third, 'QUEUED', True),
    ]
    pending = client.get(path + '/inputs', params=query | {'pending_only': 'true', 'limit': 1}).json()
    assert [item['input_id'] for item in pending['items']] == [second]
    assert pending['next_cursor']
    assert client.get(path + '/inputs', params=query | {'cursor': pending['next_cursor']}).status_code == 422
    remaining = client.get(path + '/inputs', params=query | {
        'pending_only': 'true', 'cursor': pending['next_cursor'],
    }).json()
    assert [item['input_id'] for item in remaining['items']] == [third] and remaining['next_cursor'] is None
    assert native.native.sent == [('send_turn', busy['operation_id'])]
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM session_interaction_inputs').fetchone()[0] == 3
    auth.logout(token)
    assert client.post(cancel_path, headers=ui, json=cancellation).status_code == 401
    assert client.get(path + '/inputs', params=query).status_code == 401
    client.cookies.clear()
