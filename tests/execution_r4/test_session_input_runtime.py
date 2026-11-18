"""Exercise the serve-owned queue against real R4/Core with a synthetic peer."""

from dataclasses import replace
from functools import partial

import pytest
import test_local_realization as local_realization
from nexus_connector_core import RuntimeEvent
from test_agent_recovery_isolation import eventually
from test_embedded_dispatch import admit, connect_local, wait_receipt

from okto_nexus.application.session_interaction_authority import enqueue_human_input
from okto_nexus.application.session_interaction_capability import next_turn_revision
from okto_nexus.application.session_interaction_capacity import advance_input_capacity
from okto_nexus.application.session_interaction_targets import (
    active_native_turn,
    interrupt_revision,
)
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


def test_dashboard_pauses_an_empty_queue_and_resumes_retained_inputs_in_order(interactive_runtime):
    setup, binding, native = interactive_runtime
    deps, app, client, *_ = setup
    opened = admit(setup, binding, 'dashboard-pause-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    original = opened['scope']
    fields = ('server_id', 'executor_id', 'binding_id', 'workspace_id', 'workspace_binding_id', 'agent_id', 'session_id')
    exact = {field: original[field] for field in fields}
    generation = original['session_owner_generation']
    session = exact['session_id']
    scope = InputScope(SessionKey(exact['server_id'], exact['executor_id'], session),
        SessionOwnerGeneration(generation), exact['binding_id'], exact['workspace_id'],
        exact['workspace_binding_id'], exact['agent_id'])
    path = f'/api/v1/runtime-management/runtime/sessions/{session}'
    query = {field: exact[field] for field in fields if field != 'session_id'}
    base = {'scope': exact, 'expected_session_generation': generation}
    query['expected_session_generation'] = generation
    ui = {'x-nexus-ui': '1'}
    auth = app.state.operator_auth
    assert auth.configure('pause-fixture', 'fixture-password-long', local=True)
    token = auth.login('pause-fixture', 'fixture-password-long')

    def queue():
        response = client.get(path + '/inputs', params=query)
        assert response.status_code == 200, response.text
        return response.json()

    def change(page, paused, *, headers=ui, **overrides):
        return client.post(path + '/inputs/queue-state', headers=headers, json=base | {
            'capability_revision': page['pause_capability_revision'], 'expected_queue_revision': page['queue_revision'],
            'paused': paused,
        } | overrides)

    client.cookies.set('nexus_operator_session', token)
    empty = queue()
    assert empty['pause_capability_revision'] and not empty['paused'] and not empty['items']
    assert change(empty, True, headers=ui | {'origin': 'https://foreign.invalid'}).status_code == 403
    assert change(empty, True, expected_session_generation=generation + 1).status_code == 409
    assert change(empty, 'true').status_code == 422
    paused = change(empty, True)
    assert paused.status_code == 200, paused.text
    assert paused.headers['cache-control'] == 'no-store'
    assert paused.json() == {'scope': exact, 'session_owner_generation': generation, 'paused': True, 'queue_revision': 1}
    assert change(empty, True).status_code == 409

    def capability():
        response = client.get(path + '/interaction', params=query)
        assert response.status_code == 200
        return response.json()['next_turn']['capability_revision']

    eventually(capability)
    send_revision = capability()
    retained = []
    for intent in ('first-paused', 'second-paused'):
        response = client.post(path + '/inputs', headers=ui, json=base | {
            'capability_revision': send_revision, 'client_intent_id': intent,
            'content': [{'type': 'text', 'text': intent}],
        })
        assert response.status_code == 202, response.text
        retained.append(response.json()['input_id'])

    ready = queue()
    assert ready['paused'] and ready['queue_revision'] == 3
    assert [item['input_id'] for item in ready['items']] == retained
    assert change(ready, False, capability_revision=empty['pause_capability_revision']).status_code == 409
    scheduler, = app.state.handoff_runtime_service._schedulers
    client.portal.call(partial(advance_input_capacity, scope=scope, remote_ready=scheduler.execution_ready,
                               **scheduler.options))
    assert not native.native.sent and all(item['operation_id'] is None for item in queue()['items'])
    with deps.connection_factory.unit_of_work(write=False) as uow:
        grants = uow.connection.execute('SELECT grant_id, revision FROM runtime_execution_grants').fetchall()

    resumed = change(ready, False)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()['paused'] is False and resumed.json()['queue_revision'] == 4
    assert change(ready, False).status_code == 409
    eventually(lambda: len(native.native.sent) == 1)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        stream = uow.connection.execute('SELECT stream_epoch FROM execution_local_streams WHERE session_id=?',
                                        (session,)).fetchone()[0]
    first_operation = native.native.sent[0][1]
    client.portal.call(native.native.queue.put, RuntimeEvent(
        exact['server_id'], exact['executor_id'], session, stream, 0, 'turn_state', 'fixture.pause.complete',
        {'delivery_phase': 'terminal', 'delivery_outcome': 'success'}, operation_id=first_operation))
    eventually(lambda: len(native.native.sent) == 2)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT grant_id, revision FROM runtime_execution_grants').fetchall() == grants
        submitted = [tuple(row) for row in uow.connection.execute(
            'SELECT input_id,operation_id FROM session_interaction_inputs ORDER BY enqueue_sequence')]
    assert submitted == list(zip(retained, [operation for _action, operation in native.native.sent], strict=True))
    auth.logout(token)
    assert change(ready, True).status_code == 401
    client.cookies.clear()


def test_exact_control_target_requires_current_canonical_start_of_the_active_codex_turn(interactive_runtime):
    setup, binding, native = interactive_runtime
    deps, app, client, *_ = setup
    opened = admit(setup, binding, 'exact-target-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    original = opened['scope']
    server, executor, session = (original[key] for key in ('server_id', 'executor_id', 'session_id'))
    scope = InputScope(SessionKey(server, executor, session),
        SessionOwnerGeneration(original['session_owner_generation']), original['binding_id'], original['workspace_id'],
        original['workspace_binding_id'], original['agent_id'])
    factory = deps.connection_factory
    next_turn = app.state.session_input_dispatch_options['session_input_capability_revision']

    def active():
        with factory.unit_of_work(write=False) as uow:
            return active_native_turn(uow, scope, current_next_turn_revision=next_turn)

    def capability():
        with factory.unit_of_work(write=False) as uow:
            return next_turn(uow, scope)

    eventually(capability)
    assert active() is None
    submitted = admit(setup, binding, 'target-probe-work', 'turn.submit', session_id=session, text='Synthetic exact turn')
    wait_receipt(setup, submitted)
    assert active() is None
    with factory.unit_of_work(write=False) as uow:
        epoch = uow.connection.execute('SELECT stream_epoch FROM execution_local_streams WHERE session_id=?',
                                       (session,)).fetchone()[0]

    operation = submitted['operation_id']
    native_turn = 'fixture-canonical-turn'
    thread = native.native.native_id

    def emit(kind, fields, operation_id=operation):
        client.portal.call(native.native.queue.put, RuntimeEvent(
            server, executor, session, epoch, 0, 'turn_state', kind,
            fields, operation_id=operation_id))

    emit('turn/started', {'thread_id': thread, 'threadId': thread, 'turn_id': native_turn,
         'turn': {'id': native_turn, 'status': 'inProgress'}, 'delivery_phase': 'started'})
    eventually(active)
    proven = active()
    assert proven.operation_id == operation and proven.native_id == native_turn
    with factory.unit_of_work(write=False) as uow:
        assert interrupt_revision(uow, scope, native_turn, current_next_turn_revision=next_turn)
        assert interrupt_revision(uow, scope, 'different-turn', current_next_turn_revision=next_turn) is None
        replaced = replace(scope, generation=SessionOwnerGeneration(scope.generation.value + 1))
        assert active_native_turn(uow, replaced, current_next_turn_revision=next_turn) is None
    assert active() == proven
    emit('turn/completed', {'thread_id': thread, 'turn_id': native_turn,
                            'delivery_phase': 'terminal', 'delivery_outcome': 'success'})
    eventually(lambda: active() is None)
    assert native.native.sent == [('send_turn', operation)]


def test_dashboard_interrupt_admits_exact_target_and_recovers_its_receipt(interactive_runtime):
    setup, binding, native = interactive_runtime
    deps, app, client, *_ = setup
    opened = admit(setup, binding, 'dashboard-interrupt-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    scope = opened['scope']
    exact = {key: scope[key] for key in ('server_id', 'executor_id', 'binding_id', 'workspace_id',
                                        'workspace_binding_id', 'agent_id', 'session_id')}
    generation = scope['session_owner_generation']
    server, executor, session = (exact[key] for key in ('server_id', 'executor_id', 'session_id'))
    path = f'/api/v1/runtime-management/runtime/sessions/{session}'
    query = {key: value for key, value in exact.items() if key != 'session_id'}
    query['expected_session_generation'] = generation
    assert client.get(path + '/interrupt', params=query).status_code == 401
    auth = app.state.operator_auth
    assert auth.configure('control-fixture', 'fixture-password-long', local=True)
    token = auth.login('control-fixture', 'fixture-password-long')
    client.cookies.set('nexus_operator_session', token)
    receipt_query = query | {'client_intent_id': 'stop-this-turn'}
    assert client.get(path + '/interrupt/receipt', params=receipt_query).status_code == 404
    assert auth.authority_reference(token, create=False) is None

    def target():
        response = client.get(path + '/interrupt', params=query)
        assert response.status_code == 200, response.text
        return response.json()['control']

    assert target() is None
    submitted = admit(setup, binding, 'dashboard-interrupt-turn', 'turn.submit', session_id=session, text='Synthetic active turn')
    wait_receipt(setup, submitted)
    operation = submitted['operation_id']
    factory = deps.connection_factory
    with factory.unit_of_work(write=False) as uow:
        epoch = uow.connection.execute('SELECT stream_epoch FROM execution_local_streams WHERE session_id=?',
                                       (session,)).fetchone()[0]
    thread = native.native.native_id
    native_turn = native.native.active_turn_id
    client.portal.call(native.native.queue.put, RuntimeEvent(server, executor, session, epoch, 0,
        'turn_state', 'turn/started', {'turn_id': native_turn, 'thread_id': thread, 'threadId': thread,
            'turn': {'id': native_turn, 'status': 'inProgress'}, 'delivery_phase': 'started'}, operation_id=operation))
    eventually(target)
    send_capability = client.get(path + '/interaction', params=query).json()['next_turn']['capability_revision']
    queued = client.post(path + '/inputs', headers={'x-nexus-ui': '1'}, json={
        'scope': exact, 'expected_session_generation': generation, 'capability_revision': send_capability,
        'client_intent_id': 'queued-after-interrupt', 'content': [{'type': 'text', 'text': 'Stay queued after interrupt'}],
    })
    assert queued.status_code == 202, queued.text
    control = target()
    assert control['target'] == {'kind': 'native_turn', 'turn_id': native_turn}
    seen = []
    send = native.native.send

    async def observe_send(verb, payload, operation_id, *, expected_turn_id=None):
        if verb == 'interrupt':
            with factory.unit_of_work(write=False) as uow:
                barrier = uow.connection.execute('SELECT paused_owner_generation FROM session_interaction_queues '
                    'WHERE server_id=? AND executor_id=? AND session_id=?', (server, executor, session)).fetchone()[0]
            seen.append((expected_turn_id, barrier, operation_id))
        return await send(verb, payload, operation_id, expected_turn_id=expected_turn_id)

    native.native.send = observe_send
    ui = {'x-nexus-ui': '1'}
    body = {'scope': exact, 'expected_session_generation': generation,
        'capability_revision': control['capability_revision'], 'expected_queue_revision': control['queue_revision'],
        'client_intent_id': 'stop-this-turn', 'target': control['target']}
    response = client.post(path + '/interrupt', json=body | {'text': 'private-fixture-only'}, headers=ui)
    assert response.status_code == 422 and 'private-fixture-only' not in response.text
    assert client.post(path + '/interrupt', json=body, headers=ui | {'origin': 'https://foreign.invalid'}).status_code == 403
    wrong = body | {'target': {'kind': 'native_turn', 'turn_id': 'another-turn'}}
    assert client.post(path + '/interrupt', json=wrong, headers=ui).status_code == 409
    stale = {'expected_queue_revision': control['queue_revision'] + 1}
    assert client.post(path + '/interrupt', json=body | stale, headers=ui).status_code == 409
    no_effect = client.get(path + '/inputs', params=query).json()
    assert no_effect['paused'] is False and not seen

    stopped = client.post(path + '/interrupt', json=body, headers=ui)
    assert stopped.status_code == 202, stopped.text
    control_op = stopped.json()['operation_id']
    eventually(lambda: len(seen) == 1)
    assert seen == [(native_turn, generation, control_op)]
    retained = client.get(path + '/interrupt/receipt', params=receipt_query)
    assert retained.status_code == 200, retained.text
    assert retained.json()['operation_id'] == control_op
    assert retained.json()['interrupt'] == {'target_status': 'unconfirmed', 'queue_paused': True, 'pending_count': 1}
    assert client.get(path + '/inputs', params=query).json()['pause_capability_revision'] is None
    retry = client.post(path + '/interrupt', json=body, headers=ui)
    assert retry.status_code == 200 and retry.json()['operation_id'] == control_op
    assert client.get(path + '/inputs', params=query).json()['paused'] is True
    assert native.native.sent == [('send_turn', operation), ('interrupt', control_op)]
    with factory.unit_of_work(write=False) as uow:
        assert tuple(uow.connection.execute(
            'SELECT target_operation_id,target_stream_epoch FROM session_interaction_interrupt_targets WHERE operation_id=?',
            (control_op,)).fetchone()) == (operation, epoch)
    client.portal.call(native.native.queue.put, RuntimeEvent(server, executor, session, epoch, 0,
        'turn_state', 'turn/completed', {'turn_id': native_turn, 'thread_id': thread,
            'delivery_phase': 'terminal', 'delivery_outcome': 'interrupted'}, operation_id=operation))
    eventually(lambda: client.get(path + '/interrupt/receipt', params=receipt_query).json().get('interrupt', {}).get(
        'target_status') == 'interrupted')
    assert client.get(path + '/interrupt/receipt', params=receipt_query).json()['interrupt'] == {
        'target_status': 'interrupted', 'queue_paused': True, 'pending_count': 1,
    }
    assert native.native.sent == [('send_turn', operation), ('interrupt', control_op)]
    paused_queue = client.get(path + '/inputs', params=query).json()
    assert paused_queue['paused'] and paused_queue['pause_capability_revision']
    resumed = client.post(path + '/inputs/queue-state', headers=ui, json={
        'scope': exact, 'expected_session_generation': generation, 'paused': False,
        'capability_revision': paused_queue['pause_capability_revision'], 'expected_queue_revision': paused_queue['queue_revision'],
    })
    assert resumed.status_code == 200, resumed.text
    eventually(lambda: len(native.native.sent) == 3)
    assert native.native.sent[2][0] == 'send_turn'
    assert client.get(path + '/interrupt/receipt', params=receipt_query).json()['interrupt']['queue_paused'] is False
    other_login = auth.login('control-fixture', 'fixture-password-long')
    client.cookies.set('nexus_operator_session', other_login)
    assert client.get(path + '/interrupt/receipt', params=receipt_query).status_code == 404
    assert auth.authority_reference(other_login, create=False) is None
    client.cookies.set('nexus_operator_session', token)
    auth.logout(token)
    assert client.get(path + '/interrupt/receipt', params=receipt_query).status_code == 401
    client.cookies.clear()


def test_dashboard_steers_new_and_queued_text_once_and_releases_the_fifo(interactive_runtime):
    setup, binding, native = interactive_runtime
    deps, app, client, *_ = setup
    opened = admit(setup, binding, 'steer-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    scope = opened['scope']
    exact = {key: scope[key] for key in ('server_id', 'executor_id', 'binding_id', 'workspace_id',
                                        'workspace_binding_id', 'agent_id', 'session_id')}
    generation = scope['session_owner_generation']
    server, executor, session = (exact[key] for key in ('server_id', 'executor_id', 'session_id'))
    path = f'/api/v1/runtime-management/runtime/sessions/{session}'
    query = {key: value for key, value in exact.items() if key != 'session_id'}
    query['expected_session_generation'] = generation
    base = {'scope': exact, 'expected_session_generation': generation}
    ui = {'x-nexus-ui': '1'}
    assert client.get(path + '/steer', params=query).status_code == 401
    auth = app.state.operator_auth
    assert auth.configure('steer-fixture', 'fixture-password-long', local=True)
    token = auth.login('steer-fixture', 'fixture-password-long')
    client.cookies.set('nexus_operator_session', token)

    def preview():
        response = client.get(path + '/steer', params=query)
        assert response.status_code == 200, response.text
        return response.json()['control']

    assert preview() is None
    assert auth.authority_reference(token, create=False) is None
    active = admit(setup, binding, 'steer-active', 'turn.submit', session_id=session, text='Synthetic turn for steering')
    wait_receipt(setup, active)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        epoch = uow.connection.execute('SELECT stream_epoch FROM execution_local_streams WHERE session_id=?',
                                       (session,)).fetchone()[0]
    thread, turn = native.native.native_id, native.native.active_turn_id
    client.portal.call(native.native.queue.put, RuntimeEvent(server, executor, session, epoch, 0,
        'turn_state', 'turn/started', {'turn_id': turn, 'thread_id': thread, 'threadId': thread,
            'turn': {'id': turn, 'status': 'inProgress'}, 'delivery_phase': 'started'}, operation_id=active['operation_id']))
    eventually(preview)
    effects = []
    original_send = native.native.send

    async def record_send(verb, payload, operation_id, *, expected_turn_id=None):
        if verb == 'steer':
            effects.append((expected_turn_id, payload['text'], operation_id))
        return await original_send(verb, payload, operation_id, expected_turn_id=expected_turn_id)

    native.native.send = record_send

    def confirmation(control):
        assert control['effect'] == 'same_turn'
        return base | {'capability_revision': control['capability_revision'], 'target': control['target'],
                       'expected_queue_revision': control['queue_revision'],
                       'confirmed_effect_revision': control['effect_revision']}

    def receipt(**selector):
        response = client.get(path + '/inputs/receipt', params=query | selector)
        assert response.status_code == 200, response.text
        return response.json()

    body = confirmation(preview()) | {'client_intent_id': 'direct-steer',
        'content': [{'type': 'text', 'text': 'First reorientation'}]}
    stale = client.post(path + '/steer', headers=ui, json=body | {'confirmed_effect_revision': 'stale-effect'})
    assert stale.status_code == 409
    assert client.get(path + '/inputs/receipt', params=query | {'client_intent_id': 'direct-steer'}).status_code == 404
    assert client.post(path + '/steer', headers=ui, json=body | {
        'content': [{'type': 'text', 'text': '/private-fixture-command'}],
    }).status_code == 422
    direct = client.post(path + '/steer', headers=ui, json=body)
    assert direct.status_code == 202, direct.text
    first = direct.json()
    eventually(lambda: receipt(client_intent_id='direct-steer')['steer_submitted'])
    replay = client.post(path + '/steer', headers=ui, json=body)
    assert replay.status_code == 202 and replay.json()['operation_id'] == first['operation_id']
    assert replay.json()['steer_submitted'] and replay.json()['status'] == 'DISPATCHING'

    send_revision = client.get(path + '/interaction', params=query).json()['next_turn']['capability_revision']

    def next_turn(intent, text):
        return client.post(path + '/inputs', headers=ui, json=base | {
            'client_intent_id': intent, 'capability_revision': send_revision, 'content': [{'type': 'text', 'text': text}],
        })

    assert next_turn('direct-steer', 'First reorientation').status_code == 409
    to_promote = next_turn('promote-this', 'Second reorientation').json()
    following = next_turn('ordinary-following', 'Wait for the next turn').json()
    owned = client.get(path + '/steer', params=query | {'input_id': to_promote['input_id']})
    assert owned.status_code == 200 and owned.json()['queued_input'] == {
        'input_id': to_promote['input_id'], 'input_revision': to_promote['input_revision'],
        'text_preview': 'Second reorientation', 'truncated': False,
    }
    promotion = confirmation(owned.json()['control']) | {'expected_input_revision': to_promote['input_revision']}
    promote_path = path + f"/inputs/{to_promote['input_id']}/promote"
    assert client.post(promote_path, headers=ui | {'origin': 'https://foreign.invalid'}, json=promotion).status_code == 403
    other = auth.login('steer-fixture', 'fixture-password-long')
    client.cookies.set('nexus_operator_session', other)
    assert client.post(promote_path, headers=ui, json=promotion).status_code == 404
    foreign_review = client.get(path + '/steer', params=query | {'input_id': to_promote['input_id']})
    assert foreign_review.status_code == 404 and 'Second reorientation' not in foreign_review.text
    assert client.get(path + '/inputs/receipt', params=query | {'input_id': to_promote['input_id']}).status_code == 404
    assert auth.authority_reference(other, create=False) is None
    client.cookies.set('nexus_operator_session', token)
    assert client.post(promote_path, headers=ui, json=promotion | {'expected_input_revision': 1}).status_code == 409
    moved = client.post(promote_path, headers=ui, json=promotion)
    assert moved.status_code == 202, moved.text
    second = moved.json()
    assert second['input_id'] == to_promote['input_id']
    eventually(lambda: receipt(input_id=second['input_id'])['steer_submitted'])
    assert client.post(promote_path, headers=ui, json=promotion).json()['operation_id'] == second['operation_id']
    assert effects == [(turn, 'First reorientation', first['operation_id']),
                       (turn, 'Second reorientation', second['operation_id'])]
    pending = client.get(path + '/inputs', params=query | {'pending_only': 'true'}).json()['items']
    assert [item['input_id'] for item in pending] == [following['input_id']]
    client.portal.call(native.native.queue.put, RuntimeEvent(server, executor, session, epoch, 0,
        'turn_state', 'turn/completed', {'turn_id': turn, 'thread_id': thread,
            'delivery_phase': 'terminal', 'delivery_outcome': 'success'}, operation_id=active['operation_id']))
    eventually(lambda: len(native.native.sent) == 4)
    assert native.native.sent == [('send_turn', active['operation_id']), ('steer', first['operation_id']),
                                  ('steer', second['operation_id']), ('send_turn', receipt(input_id=following['input_id'])['operation_id'])]
    assert preview() is None
    finished_queue = client.get(path + '/inputs', params=query).json()
    finished = client.post(path + '/steer', headers=ui, json=body | {
        'client_intent_id': 'target-already-ended', 'expected_queue_revision': finished_queue['queue_revision'],
    })
    assert finished.status_code == 409
    assert client.get(path + '/inputs/receipt', params=query | {
        'client_intent_id': 'target-already-ended',
    }).status_code == 404
    assert len(effects) == 2
    client.cookies.clear()
