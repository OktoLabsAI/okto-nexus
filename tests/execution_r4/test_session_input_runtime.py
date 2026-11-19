"""Exercise the serve-owned queue against real R4/Core with a synthetic peer."""

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from functools import partial

import pytest
import test_local_realization as local_realization
from nexus_connector_core import RuntimeEvent
from test_agent_recovery_isolation import eventually
from test_embedded_dispatch import admit, connect_local, wait_receipt

from okto_nexus.application.execution_native_session_mapping import (
    read_managed_native_session,
)
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
CODEX_THREAD = 'bdfe5b81-54cf-43cf-8001-5de670d3dd69'


def emit_codex_configuration(client, native, server, executor, session, epoch):
    client.portal.call(native.native.queue.put, RuntimeEvent(
        server, executor, session, epoch, 0, 'lifecycle', 'core/codex_thread_configuration',
        {'schema_version': 1, 'adapter_id': 'codex_app_server', 'thread_id': CODEX_THREAD,
         'source': 'thread/start/response', 'fields': {}}))


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


@pytest.mark.parametrize('local_setup', ['claude_stream'], indirect=True)
def test_embedded_dispatch_publishes_the_exact_uncertain_claude_terminal_receipt(
        interactive_runtime, local_setup, monkeypatch):
    from urllib.request import Request, urlopen
    from uuid import uuid4

    from nexus_connector_core.native.claude_terminal_prompt import ClaudeTerminalPromptGate
    from nexus_connector_core.native.claude_terminal_submission import ClaudeTerminalSession
    from nexus_connector_core.native.redaction import NativeSecretRedactor

    setup, binding, native = interactive_runtime
    deps, app, client, headers, *_, workspace_root = setup
    native_session = str(uuid4())
    cwd = str(workspace_root.resolve())
    replies = []
    idle_since = None
    finished_text_hash = hashlib.sha256(b'Result fixture-secret').hexdigest()

    with ClaudeTerminalPromptGate(native_session, cwd, 'plan', lambda _operation: True, observe_results=True) as gate:
        settings, env = gate.launch_settings()
        hook = settings['hooks']['UserPromptSubmit'][0]['hooks'][0]
        completion = settings['hooks']['Stop'][0]['hooks'][0]
        token = next(iter(env.values()))

        def send_hook(url, kind, **fields):
            body = {'hook_event_name': kind, 'session_id': native_session, 'cwd': cwd,
                    'permission_mode': 'plan', 'prompt_id': 'fixture-prompt', **fields}
            request = Request(url, data=json.dumps(body).encode(), headers={
                'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token,
            })
            with urlopen(request, timeout=4) as response:
                return json.load(response)

        class LostTerminalReply:
            birth = None
            stopped = False

            def write(self, data):
                replies.append(send_hook(hook['url'], 'UserPromptSubmit', prompt=data[6:-7].decode()))
                raise OSError('Synthetic loss after the native terminal received the hook reply.')

            def poll(self):
                return 0 if self.stopped else None

            def close(self):
                self.stopped = True

        async def open_owned_terminal(_prepared, session_id, context, *, stream_epoch):
            native.native = ClaudeTerminalSession(
                LostTerminalReply(), gate, native_id='fixture-owned-terminal', session_id=session_id,
                stream_epoch=stream_epoch, context=context, redactor=NativeSecretRedactor(('fixture-secret',)),
                observe_finished=lambda digest: idle_since if digest == finished_text_hash else None)
            return native.native

        monkeypatch.setattr(native, 'open', open_owned_terminal)
        opened = admit(setup, binding, 'terminal-source', 'runtime.start', new_session=True)
        wait_receipt(setup, opened)
        session = opened['scope']['session_id']
        driver = native.native.terminal_submission
        operation = admit(setup, binding, 'terminal-uncertain', 'turn.submit', session_id=session, text='Exact input.')
        observed = wait_receipt(setup, operation, stages=('OUTCOME_UNKNOWN',))
        assert observed['operation_id'] == operation['operation_id']
        assert replies == [{}] and driver.active_turn()
        assert app.state.embedded_dispatch_owner.failure is None
        request = {key: operation[key] for key in ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')}
        replayed = client.post('/v1/runtime/operations', headers=headers['subject'], json=request)
        assert replayed.status_code == 200 and replayed.json()['operation_id'] == operation['operation_id']
        assert wait_receipt(setup, operation, stages=('OUTCOME_UNKNOWN',)) == observed

        send_hook(completion['url'], 'Stop', stop_hook_active=False, background_tasks=[], session_crons=[],
                  last_assistant_message='Intermediate text')
        assert wait_receipt(setup, operation, stages=('OUTCOME_UNKNOWN',)) == observed
        send_hook(completion['url'], 'Stop', stop_hook_active=True, background_tasks=[], session_crons=[],
                  last_assistant_message='Result fixture-secret')
        assert wait_receipt(setup, operation, stages=('OUTCOME_UNKNOWN',)) == observed
        time.sleep(.01)
        idle_since = time.time_ns() // 1_000_000
        wait_receipt(setup, operation, stages=('SUCCEEDED',))
        assert replies == [{}] and not driver.active_turn()

        def result():
            with deps.connection_factory.unit_of_work(write=False) as uow:
                return uow.connection.execute(
                    'SELECT output_text FROM execution_results WHERE operation_id=? AND terminal_sequence IS NOT NULL',
                    (operation['operation_id'],)).fetchone()

        eventually(result)
        assert result()['output_text'] == 'Result [REDACTED]'


@pytest.mark.parametrize('local_setup', ['claude_stream'], indirect=True)
@pytest.mark.parametrize('condition', ['normal_close', 'replaced_history', 'changed_build', 'later_unverified_result'])
def test_managed_claude_history_uses_latest_scoped_terminal_fact(interactive_runtime, local_setup, condition, monkeypatch):
    import re

    from nexus_connector_core import OperationKey, ProcessBirthEvidence
    from nexus_connector_core.native import process
    from nexus_connector_core.native.claude_saved_history import observe_claude_saved_history

    setup, binding, native = interactive_runtime
    deps, app, client, *_, workspace_root = setup
    opened = admit(setup, binding, 'claude-history-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    selected = opened['scope']
    scope = InputScope(SessionKey(selected['server_id'], selected['executor_id'], selected['session_id']),
        SessionOwnerGeneration(selected['session_owner_generation']), selected['binding_id'],
        selected['workspace_id'], selected['workspace_binding_id'], selected['agent_id'])
    session = scope.session.session_id
    factory = deps.connection_factory
    history_uuid = 'cb41c871-35f9-480f-90c2-f2aa920caf65'

    def mapping():
        with factory.unit_of_work(write=False) as uow:
            return read_managed_native_session(uow, scope)

    eventually(mapping)
    observed = mapping()
    assert observed.claude_history is None
    with factory.unit_of_work(write=False) as uow:
        stream = uow.connection.execute('SELECT stream_epoch FROM execution_local_streams WHERE session_id=?',
                                       (session,)).fetchone()[0]

    def turn(label, identity):
        work = admit(setup, binding, 'claude-history-' + label, 'turn.submit', session_id=session, text=label)
        wait_receipt(setup, work)
        payload = {'delivery_phase': 'terminal', 'delivery_outcome': 'success', 'session_id': history_uuid}
        if identity:
            payload['claude_history_identity'] = {'schema_version': 1, 'session_id': history_uuid}
        client.portal.call(native.native.queue.put, RuntimeEvent(
            scope.session.server_id, scope.session.executor_id, session, stream, 0, 'turn_state',
            'result:success', payload, operation_id=work['operation_id']))
        wait_receipt(setup, work, stages=('SUCCEEDED',))

        def committed_result():
            with factory.unit_of_work(write=False) as uow:
                return uow.connection.execute("""
                    SELECT 1 FROM execution_results r
                    JOIN execution_event_watermarks w USING(server_id,executor_id,session_id,stream_epoch)
                    WHERE r.server_id=? AND r.executor_id=? AND r.operation_id=?
                      AND w.gap_state='none' AND r.terminal_sequence<=w.committed_contiguous
                """, (scope.session.server_id, scope.session.executor_id, work['operation_id'])).fetchone()

        eventually(committed_result)
        return work['operation_id']

    operation = turn('confirmed', True)
    eventually(lambda: mapping().claude_history)
    proof = mapping().claude_history
    assert proof.session_uuid == history_uuid and proof.operation_id == operation
    assert proof.event_hash.startswith('sha256:') and mapping().native_session_id != history_uuid
    with factory.unit_of_work(write=False) as uow:
        assert read_managed_native_session(uow, replace(scope, generation=SessionOwnerGeneration(
            scope.generation.value + 1))) is None
    if condition == 'later_unverified_result':
        turn('legacy-without-proof', False)
        assert mapping().claude_history is None
        return

    reviewed = replace(mapping().launch_build, version='2.1.328', platform='win32',
        content_fingerprint='sha256:551d573567b46ce78aba1b20beb20ac2494f5f8adffd1b41dfd269a96e1d9839')
    with factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE execution_sessions SET native_launch_build_json=? WHERE session_id=?',
                               (json.dumps(asdict(reviewed)), session))
    owner = app.state.embedded_dispatch_owner
    server, executor = scope.session.server_id, scope.session.executor_id
    _, journal = owner.host._runtime_tasks[(executor, session)].result()
    birth = ProcessBirthEvidence('win32', 1234, 'filetime:12345678', 'windows_job')
    client.portal.call(journal.record_process_birth,
                       OperationKey(server, executor, opened['operation_id']), session, birth)
    native.native.owned_process_birth = birth
    monkeypatch.setattr(process, 'observe_recorded_process_birth',
                        lambda evidence: 'MATCHING_LIVE' if evidence == birth else 'DIFFERENT_BIRTH')

    root = str(workspace_root.resolve())
    home = workspace_root.parent / 'private-claude-fixture'
    folder = re.sub(r'[^A-Za-z0-9]', '-', root)
    history = home / 'projects' / folder / f'{history_uuid}.jsonl'
    history.parent.mkdir(parents=True)
    payload = ''.join(json.dumps({
        'type': kind, 'sessionId': history_uuid, 'cwd': root, 'isSidechain': False,
        'message': {'role': kind, 'content': 'private content'},
    }) + '\n' for kind in ('user', 'assistant'))
    history.write_bytes(payload.encode())

    async def read_claude(session_uuid, operation_id):
        assert (session_uuid, operation_id) == (history_uuid, operation) and not native.native.stopped
        return observe_claude_saved_history(str(home), session_uuid, root)

    monkeypatch.setattr(native.native, 'read_owned_claude_history', read_claude, raising=False)

    def stored():
        with factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute('SELECT * FROM embedded_saved_contexts WHERE session_id=?',
                                         (session,)).fetchone()
            return dict(row) if row else None

    original_close = native.native.close
    captured = []

    async def close_source():
        witness = stored()
        assert witness['adapter_id'] == 'claude_stream' and witness['status'] == 'CAPTURED'
        captured.append(witness)
        await owner.saved_contexts.reconcile(witness['close_operation_id'])
        assert stored() == witness
        if condition == 'replaced_history':
            history.write_bytes(payload.replace('private content', 'unreviewed').encode())
        if condition == 'changed_build':
            with factory.unit_of_work() as uow:
                changed = replace(reviewed, build_identity='sha256:' + 'a' * 64)
                uow.connection.execute('UPDATE execution_sessions SET native_launch_build_json=? WHERE session_id=?',
                                       (json.dumps(asdict(changed)), session))
        return await original_close()

    monkeypatch.setattr(native.native, 'close', close_source)
    close = admit(setup, binding, 'claude-history-close', 'runtime.close', session_id=session)
    wait_receipt(setup, close, stages=('SUCCEEDED',))
    status = 'VERIFIED' if condition == 'normal_close' else 'FILE_CHANGED'
    eventually(lambda: stored() and stored()['status'] == status)
    witness = stored()
    assert len(captured) == 1 and native.native.stopped and mapping().claude_history == proof
    assert witness['close_operation_id'] == close['operation_id']
    assert 'private content' not in witness['witness_json']
    retained = json.loads(witness['witness_json'])
    assert retained['terminal'] == asdict(proof)
    assert retained['opening_profile']['profile_fingerprint'].startswith('sha256:')
    assert retained['opening_profile']['root_fingerprint'].startswith(root + '|')
    assert retained['opening_binding_digest'].startswith('sha256:')
    assert bool(witness['release_digest']) == (status == 'VERIFIED')


@pytest.mark.parametrize('local_setup', ['claude_stream'], indirect=True)
@pytest.mark.parametrize('case', ['submitted', 'not_sent', 'write_unknown', 'question'])
def test_dashboard_reviews_and_recovers_exact_claude_reorientation(interactive_runtime, local_setup, case):
    from nexus_connector_core.native.adapter_types import (
        ErrorCode,
        NativeAdapterError,
        ReplacementNotSentAfterInterrupt,
    )

    setup, binding, native = interactive_runtime
    deps, app, client, headers, *_ = setup
    replacement = 'submitted' if case == 'question' else case
    if case == 'question':
        deps.config.feature_hitl = True
    opened = admit(setup, binding, 'claude-review-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    generation = opened['scope']['session_owner_generation']
    exact = {key: opened['scope'][key] for key in ('server_id', 'executor_id', 'binding_id', 'workspace_id',
                                                  'workspace_binding_id', 'agent_id', 'session_id')}
    session = exact['session_id']
    path = f'/api/v1/runtime-management/runtime/sessions/{session}'
    query = {key: value for key, value in exact.items() if key != 'session_id'}
    query['expected_session_generation'] = generation
    ui = {'x-nexus-ui': '1'}
    auth = app.state.operator_auth
    assert auth.configure('claude-review-fixture', 'fixture-password-long', local=True)
    client.cookies.set('nexus_operator_session', auth.login('claude-review-fixture', 'fixture-password-long'))

    def preview():
        response = client.get(path + '/steer', params=query)
        assert response.status_code == 200, response.text
        return response.json()['control']

    assert preview() is None
    active = admit(setup, binding, 'claude-active-turn', 'turn.submit', session_id=session, text='Synthetic turn')
    wait_receipt(setup, active)
    active_id = active['operation_id']
    assert preview() is None
    with deps.connection_factory.unit_of_work(write=False) as uow:
        epoch = uow.connection.execute('SELECT stream_epoch FROM execution_local_streams WHERE session_id=?',
                                       (session,)).fetchone()[0]

    def event(kind, native_type, payload, operation_id):
        return RuntimeEvent(exact['server_id'], exact['executor_id'], session, epoch, 0,
                            kind, native_type, payload, operation_id=operation_id)

    client.portal.call(native.native.queue.put,
                       event('tool_activity', 'nexus_claude_generating', {'schema_version': 1}, active_id))
    eventually(preview)
    control = preview()
    assert control['effect'] == 'interrupt_then_send'
    assert control['target'] == {'kind': 'claude_operation', 'operation_id': active_id}
    interaction = client.get(path + '/interaction', params=query).json()
    assert interaction['steer_review_supported'] is True
    base = {'scope': exact, 'expected_session_generation': generation}
    selector = {'client_intent_id': 'claude-review-send'}
    content = {'content': [{'type': 'text', 'text': 'Synthetic replacement'}]}
    route = path + '/steer'
    action = selector | content
    if replacement == 'not_sent':
        queued = client.post(path + '/inputs', headers=ui, json=base | action | {
            'capability_revision': interaction['next_turn']['capability_revision'],
        })
        assert queued.status_code == 202, queued.text
        entry = queued.json()
        route = f"{path}/inputs/{entry['input_id']}/promote"
        selector = {'input_id': entry['input_id']}
        response = client.get(path + '/steer', params=query | selector)
        assert response.status_code == 200, response.text
        queued_review = response.json()
        control = queued_review['control']
        assert control['target']['operation_id'] == active_id
        assert queued_review['queued_input']['text_preview'] == 'Synthetic replacement'
        action = {'expected_input_revision': queued_review['queued_input']['input_revision']}

    effects = []
    original_send = native.native.send

    async def record_send(verb, payload, operation_id, *, expected_turn_id=None):
        if verb == 'steer':
            effects.append((operation_id, payload['expected_claude_operation_id']))
            stages = ['interrupt_submitted']
            if replacement != 'not_sent':
                stages.append('interrupt_confirmed')
            stages.append('replacement_' + replacement)
            for stage in stages:
                await native.native.queue.put(event('tool_activity', 'nexus_claude_steer', {
                    'stage': stage, 'interrupt_request_id': 'fixture-interrupt', 'turn_operation_id': active_id,
                }, operation_id))
            if replacement == 'not_sent':
                raise ReplacementNotSentAfterInterrupt()
            if replacement == 'write_unknown':
                raise NativeAdapterError(ErrorCode.INTERNAL_ERROR, 'Synthetic replacement write failure')
        return await original_send(verb, payload, operation_id, expected_turn_id=expected_turn_id)

    native.native.send = record_send
    body = base | {'capability_revision': control['capability_revision'],
            'target': control['target'], 'expected_queue_revision': control['queue_revision'],
            'confirmed_effect_revision': control['effect_revision']} | action

    def confirm(document):
        return client.post(route, headers=ui, json=document)

    assert confirm(body | {'target': {'kind': 'claude_operation', 'operation_id': 'op_' + '0' * 32}}).status_code == 409
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(confirm, (body, body)))
    assert first.status_code == second.status_code == 202, (first.text, second.text)
    operation_id = first.json()['operation_id']
    assert second.json()['operation_id'] == operation_id

    def receipt():
        response = client.get(path + '/inputs/receipt', params=query | selector)
        assert response.status_code == 200, response.text
        assert 'Synthetic replacement' not in response.text and 'fixture-interrupt' not in response.text
        return response.json()

    expected = {'interruption': 'submitted' if replacement == 'not_sent' else 'confirmed', 'replacement': replacement}
    eventually(lambda: receipt().get('steer_compound') == expected)
    retained = receipt()
    assert retained['possible_effect'] and retained['operation_id'] == operation_id
    if replacement != 'submitted':
        eventually(lambda: receipt()['status'] == 'DELIVERY_UNKNOWN')
        assert preview() is None
        assert receipt()['steer_compound'] == expected
        replay = confirm(body)
        assert replay.status_code == 202 and replay.json()['operation_id'] == operation_id
    if replacement == 'submitted':
        assert retained['status'] == 'DISPATCHING'
    if case == 'question':
        client.portal.call(native.native.queue.put, event('turn_state', 'fixture.claude.interrupted',
            {'delivery_phase': 'terminal', 'delivery_outcome': 'interrupted'}, active_id))
        wait_receipt(setup, active, stages=('CANCELLED',))
        _exercise_claude_replacement_question(deps, client, headers, native.native, exact, generation, epoch,
                                             operation_id, event)
    if replacement != 'not_sent':
        client.portal.call(native.native.queue.put, event('turn_state', 'fixture.claude.replacement_finished',
                                {'delivery_phase': 'terminal', 'delivery_outcome': 'success'}, operation_id))
        eventually(lambda: receipt()['status'] == 'ACCEPTED_NATIVE')
    assert effects == [(operation_id, active_id)]


def _exercise_claude_replacement_question(deps, client, headers, native, scope, generation, epoch, operation_id, event):
    from okto_nexus.adapters.outbound.sqlite.execution_native_sources import (
        read_native_turn_source,
    )

    request = {
        'schema_version': 1, 'request_id': 'fixture-claude-question', 'request_hash': 'c' * 64,
        'method': 'control_request:can_use_tool', 'local_generation': 2, 'params': {
            'tool_name': 'AskUserQuestion', 'tool_use_id': 'fixture-tool', 'input': {'questions': [{
                'question': 'Which fixture marker?', 'header': 'Marker', 'multiSelect': False,
                'options': [{'label': 'Blue', 'description': 'Blue marker'},
                            {'label': 'Green', 'description': 'Green marker'}],
            }]},
        },
    }
    replies = []

    async def reply(native_request, decision, response):
        replies.append((native_request['request_id'], native_request['local_generation'], decision, dict(response)))

    native.reply_native_approval = reply
    client.portal.call(native.queue.put, event('input_request', request['method'],
        {'native_approval': request, 'native_approval_display': request}, operation_id))

    def pending_for(actor):
        response = client.get('/v1/runtime/input-requests', headers=headers[actor])
        assert response.status_code == 200, response.text
        return response.json()['items']

    eventually(lambda: pending_for('operator'))
    item, = pending_for('operator')
    details = item['request_payload']['kwargs']
    assert details['recipient_agent_id'] == 'operator' and pending_for('subject') == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        source = {key: scope[key] for key in ('server_id', 'executor_id', 'session_id')} | {'operation_id': operation_id}
        conn = uow.connection
        row = conn.execute('SELECT source_operation_id FROM execution_native_requests WHERE canonical_request_id=?',
                           (details['approval_key']['canonical_request_id'],)).fetchone()
        assert row['source_operation_id'] == operation_id
        assert read_native_turn_source(conn, **source, owner_generation=generation, stream_epoch=epoch)
        assert read_native_turn_source(conn, **source, owner_generation=generation + 1, stream_epoch=epoch) is None
        assert read_native_turn_source(conn, **source, owner_generation=generation, stream_epoch='foreign') is None

    attention = client.get('/api/v1/attention', params={
        'workspace_id': scope['workspace_id'], 'kind': 'native_question_pending',
    }, headers={'x-api-key': headers['operator']['Authorization'].removeprefix('Bearer ')})
    assert attention.status_code == 200, attention.text
    question, = attention.json()['data']['items']
    assert question['allowed_actions'] == ['inspect_approval', 'respond_native']

    answer = {'answers': {'Which fixture marker?': 'Blue'}}
    decision = {key: details[key] for key in ('approval_key', 'expected_revision', 'request_hash', 'cas_token')}
    decision.update(client_intent_id='claude-replacement-answer', decision='approve', response=answer)
    decision_path = '/v1/runtime/approval-decisions'
    assert client.post(decision_path, headers=headers['subject'], json=decision).status_code == 403
    response = client.post(decision_path, headers=headers['operator'], json=decision)
    assert response.status_code == 202, response.text
    recovered = client.post(decision_path, headers=headers['operator'], json=decision)
    assert recovered.status_code == 200 and recovered.json()['decision_id'] == response.json()['decision_id']
    eventually(lambda: bool(replies))
    assert replies == [(request['request_id'], request['local_generation'], 'accept', answer)]


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
    client.cookies.set('nexus_operator_session', token)
    path = f'/api/v1/runtime-management/runtime/sessions/{scope.session.session_id}'
    query = {name: original[name] for name in (
        'server_id', 'executor_id', 'binding_id', 'workspace_id', 'workspace_binding_id', 'agent_id')}
    query['expected_session_generation'] = scope.generation.value

    def affordance():
        response = client.get(path + '/interaction', params=query)
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
        return response.json()['next_turn']

    assert affordance()['turn_state'] == 'unknown'
    with factory.unit_of_work(write=False) as uow:
        epoch = uow.connection.execute(
            'SELECT stream_epoch FROM execution_local_streams WHERE server_id=? AND executor_id=? AND session_id=?',
            (scope.session.server_id, scope.session.executor_id, scope.session.session_id),
        ).fetchone()['stream_epoch']
    emit_codex_configuration(client, native, scope.session.server_id, scope.session.executor_id,
                             scope.session.session_id, epoch)
    eventually(lambda: affordance()['turn_state'] == 'idle')
    assert affordance()['capability_revision'] == capability_revision
    ordinary = admit(setup, binding, 'busy-turn', 'turn.submit',
                     session_id=scope.session.session_id, text='Ordinary synthetic turn')
    wait_receipt(setup, ordinary)
    eventually(lambda: affordance()['turn_state'] == 'busy')
    assert affordance()['capability_revision'] == capability_revision

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
    assert capability['human_login_required'] and capability['turn_state'] == 'unknown'
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
    stream_url = path + '/conversation/stream'
    assert client.get(stream_url, params=query | {'workspace_id': 'another-workspace'}).status_code == 404
    assert client.get(stream_url, params=query | {'expected_session_generation': generation + 1}).status_code == 404
    assert client.get(stream_url, params=query | {'offset': '50'}).status_code == 422
    assert client.post(path + '/inputs', json=body, headers=ui | {'origin': 'https://foreign.invalid'}).status_code == 403
    invalid = client.post(path + '/inputs', json=body | {'actor_agent_id': 'fixture-uncopied'}, headers=ui)
    assert invalid.status_code == 422 and 'fixture-uncopied' not in invalid.text
    for text in ('  /unknown', '!fixture'):
        command = client.post(path + '/inputs', json=body | {'content': [{'type': 'text', 'text': text}]}, headers=ui)
        assert command.status_code == 422 and text not in command.text
    assert client.post(path + '/inputs', json=body | {'capability_revision': 'stale'}, headers=ui).status_code == 409
    catalog = client.get(path + '/commands', params=query).json()
    command = body | {'command': 'send', 'catalog_revision': catalog['capability_revision'], 'confirmed': True}
    assert client.post(path + '/commands:execute', json=command | {'confirmed': False}, headers=ui).status_code == 422
    stale_command = client.post(path + '/commands:execute', json=command | {'catalog_revision': 'stale'}, headers=ui)
    assert stale_command.status_code == 409 and 'Session commands changed.' in stale_command.text
    first = client.post(path + '/commands:execute', json=command, headers=ui)
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


def test_exact_control_target_requires_current_canonical_start_of_the_active_codex_turn(interactive_runtime, monkeypatch):
    from nexus_connector_core import (
        CoreError,
        NativeSessionTarget,
        OperationKey,
        ProcessBirthEvidence,
    )
    from nexus_connector_core.native import process

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
    thread = CODEX_THREAD

    def emit(kind, fields, operation_id=operation):
        client.portal.call(native.native.queue.put, RuntimeEvent(
            server, executor, session, epoch, 0, 'turn_state', kind,
            fields, operation_id=operation_id))

    emit('turn/started', {'thread_id': thread, 'threadId': thread, 'turn_id': native_turn,
         'turn': {'id': native_turn, 'status': 'inProgress'}, 'delivery_phase': 'started'})
    assert active() is None
    assert native.native.native_id != thread
    emit_codex_configuration(client, native, server, executor, session, epoch)
    eventually(active)
    proven = active()
    assert proven.operation_id == operation and proven.native_id == native_turn
    with factory.unit_of_work(write=False) as uow:
        mapping = read_managed_native_session(uow, scope)
        assert mapping is not None and mapping.scope == scope
        assert mapping.opening_operation_id == opened['operation_id']
        assert mapping.native_session_id == native.native.native_id and mapping.codex_thread_id == thread
        assert mapping.codex_configuration_hash.startswith('sha256:')
        assert mapping.stream_epoch == epoch and mapping.adapter_id == 'codex_app_server'
        assert mapping.launch_inventory_revision and mapping.launch_candidate_ref and mapping.launch_profile_revision > 0
        assert mapping.launch_build is not None and mapping.launch_build.version == '0.159.0'
        assert mapping.launch_build.architecture == 'x86_64' and mapping.launch_build.qualification == 'qualified'
        assert mapping.launch_build.content_fingerprint.startswith('sha256:')
        assert mapping.receipt_connection_id and mapping.receipt_connection_generation > 0
        for field in ('binding_id', 'workspace_id', 'workspace_binding_id', 'agent_id'):
            assert read_managed_native_session(uow, replace(scope, **{field: 'other-' + field})) is None
        assert interrupt_revision(uow, scope, native_turn, current_next_turn_revision=next_turn)
        assert interrupt_revision(uow, scope, 'different-turn', current_next_turn_revision=next_turn) is None
        replaced = replace(scope, generation=SessionOwnerGeneration(scope.generation.value + 1))
        assert read_managed_native_session(uow, replaced) is None
        assert active_native_turn(uow, replaced, current_next_turn_revision=next_turn) is None
    assert active() == proven
    owner = app.state.embedded_dispatch_owner
    host = owner.host
    runtime, journal = host._runtime_tasks[(executor, session)].result()
    birth = ProcessBirthEvidence('win32', 1234, 'filetime:12345678', 'windows_job')
    client.portal.call(journal.record_process_birth, OperationKey(server, executor, opened['operation_id']), session, birth)
    native.native.owned_process_birth = birth
    monkeypatch.setattr(process, 'observe_recorded_process_birth',
                        lambda evidence: 'MATCHING_LIVE' if evidence == birth else 'DIFFERENT_BIRTH')
    target = NativeSessionTarget(mapping.opening_operation_id, mapping.adapter_id, mapping.native_session_id, epoch)
    scope_document = owner.sessions[session]['scope']

    async def prove(selected):
        return await host.prove_r4_native_session(selected, target, connection_id=owner.channel.connection_id,
                                                connection_generation=owner.channel.connection_generation)

    live = client.portal.call(prove, scope_document)
    assert live.target == target and live.key.session_id == session
    assert live.process.evidence == birth and live.boot_id == runtime.r4_boot_id
    assert client.portal.call(owner.prove_native_presentation_owner, scope) == (mapping, live)
    with pytest.raises(CoreError, match='CAPABILITY_UNSUPPORTED'):
        client.portal.call(owner.read_native_pi_presentation_state, scope)

    async def attach_pi():
        async with owner.open_native_pi_renderer(scope, columns=100, rows=36):
            pytest.fail('Codex exposed a Pi renderer')

    with pytest.raises(CoreError, match='CAPABILITY_UNSUPPORTED'):
        client.portal.call(attach_pi)

    presentation = {'thread_id': thread, 'status': 'active'}

    async def read_thread(thread_id):
        assert thread_id == thread and thread_id != native.native.native_id
        return presentation

    monkeypatch.setattr(native.native, 'read_owned_codex_thread', read_thread, raising=False)
    assert client.portal.call(owner.read_native_presentation_metadata, scope) == {
        'thread_id': thread, 'status': 'active'}
    assert client.portal.call(owner.read_native_presentation_context, scope) is None
    context = {**presentation, 'session_id': 'native-rollout', 'created_at': 1, 'updated_at': 2,
               'ephemeral': True, 'cwd': '/fixture', 'model': 'synthetic', 'model_provider': 'fixture',
               'cli_version': '0.170.0', 'source': 'cli', 'approval_policy': 'never', 'approvals_reviewer': 'user',
               'sandbox': {'type': 'readOnly', 'networkAccess': False}, 'reasoning_effort': 'medium'}
    presentation['viewer_context'] = context
    observed = client.portal.call(owner.read_native_presentation_context, scope)
    assert observed.model_dump() == context
    presentation['viewer_context'] = context | {'thread_id': 'sibling'}
    assert client.portal.call(owner.read_native_presentation_context, scope) is None

    auth = app.state.operator_auth
    user, password = 'presenter-fixture', 'fixture-viewer-password'
    assert auth.configure(user, password, local=True)
    token = auth.login(user, password)
    origin = 'http://127.0.0.1'
    headers = {'cookie': f'nexus_operator_session={token}', 'x-nexus-ui': '1', 'origin': origin}
    prefix = '/api/v1/runtime-management'
    url = origin + prefix + f'/sessions/{session}/attachments'
    scope_body = {name: original[name] for name in (
        'server_id', 'executor_id', 'binding_id', 'agent_id', 'workspace_id', 'workspace_binding_id', 'session_id')}
    body = {'scope': scope_body, 'expected_session_generation': scope.generation.value}
    assert app.state.local_codex_presentations is not None
    presentation['viewer_context'] = context
    assert client.post(url + ':review', headers=headers, json=body).status_code == 409

    def record_build(build):
        with factory.unit_of_work() as uow:
            uow.connection.execute("""
                UPDATE execution_sessions SET native_launch_build_json=?
                WHERE server_id=? AND executor_id=? AND session_id=?
            """, (json.dumps(asdict(build)), server, executor, session))

    reviewed = replace(mapping.launch_build, version='0.157.0', platform='win32',
        content_fingerprint='sha256:ed1c7b36e44536809c868864c833af8a857f56599a7a7fe23b908a1ba1093b1f')
    record_build(reviewed)
    assert client.post(url + ':review', headers=headers, json=body).status_code == 200
    idle = context | {'status': 'idle', 'cli_version': '0.157.0'}
    presentation['viewer_context'] = idle
    review = client.post(url + ':review', headers=headers, json=body)
    assert review.status_code == 200, review.text
    request = body | {'capability_revision': review.json()['capability_revision'],
                      'intent': 'attach_live', 'access': 'read', 'client_intent_id': 'embedded-read'}
    record_build(replace(reviewed, content_fingerprint='sha256:' + 'a' * 64))
    assert client.post(url + ':prepare', headers=headers, json=request).status_code == 409
    record_build(reviewed)
    response = client.post(url + ':prepare', headers=headers, json=request)
    assert response.status_code == 201, response.text
    offer = response.json()
    stream = 'ws://127.0.0.1' + prefix + f'/attachments/{offer["attachment_id"]}/stream'
    ws_headers = headers | {'authorization': 'Bearer ' + offer['ticket']}
    with client.websocket_connect(stream, headers=ws_headers, subprotocols=['nexus.presenter.v1']) as peer:
        peer.send_json({'kind': 'hello', 'version': 1, **body})
        challenge = peer.receive_json()
        peer.send_json({'kind': 'prove', 'challenge': challenge['challenge']})
        assert peer.receive_json()['kind'] == 'attached'
        peer.send_json({'kind': 'context', 'request_id': 1})
        assert peer.receive_json() == {'kind': 'context', 'request_id': 1, 'context': idle}
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT state FROM session_attachments').fetchone()[0] == 'DETACHED'

    presentation['viewer_context'] = context | {'cli_version': '0.157.0'}
    response = client.post(url + ':prepare', headers=headers, json=request | {'client_intent_id': 'busy-read'})
    assert response.status_code == 201 and response.json()['live_updates'] is True, response.text
    offer = response.json()
    stream = 'ws://127.0.0.1' + prefix + f'/attachments/{offer["attachment_id"]}/stream'
    ws_headers = headers | {'authorization': 'Bearer ' + offer['ticket']}
    with client.websocket_connect(stream, headers=ws_headers, subprotocols=['nexus.presenter.v1']) as peer:
        peer.send_json({'kind': 'hello', 'version': 1, **body})
        challenge = peer.receive_json()
        peer.send_json({'kind': 'prove', 'challenge': challenge['challenge']})
        assert peer.receive_json()['kind'] == 'attached'
        peer.send_json({'kind': 'context', 'request_id': 1, 'follow': True})
        assert peer.receive_json()['context']['status'] == 'active'
        peer.send_json({'kind': 'page', 'request_id': 2, 'method': 'thread/turns/list', 'params': {'threadId': thread}})
        assert peer.receive_json()['page']['data'] == [
            {'id': native_turn, 'status': 'inProgress', 'itemsView': 'notLoaded', 'items': []}]
        peer.send_json({'kind': 'updates', 'request_id': 3})
        assert peer.receive_json()['updates'] == {'notifications': [], 'has_more': False}
    assert active() == proven
    record_build(mapping.launch_build)

    for field in ('binding_id', 'workspace_id', 'workspace_binding_id', 'agent_id'):
        with pytest.raises(CoreError, match='SESSION_UNKNOWN'):
            client.portal.call(owner.prove_native_presentation_owner, replace(scope, **{field: 'other-' + field}))
    with pytest.raises(CoreError, match='SESSION_UNKNOWN'):
        client.portal.call(owner.prove_native_presentation_owner, replaced)
    with pytest.raises(CoreError, match='SESSION_UNKNOWN'):
        client.portal.call(prove, scope_document | {'server_id': 'sibling-server'})
    with pytest.raises(CoreError, match='STALE_GENERATION'):
        client.portal.call(prove, scope_document | {'session_owner_generation': scope.generation.value + 1})
    assert len(host._runtime_tasks) == 1

    original_proof = host.prove_r4_native_session

    async def evidence_changes_while_proving(*args, **kwargs):
        proof = await original_proof(*args, **kwargs)
        with factory.unit_of_work() as uow:
            uow.connection.execute("""
                UPDATE execution_sessions SET native_launch_build_json=NULL
                WHERE server_id=? AND executor_id=? AND session_id=?
            """, (server, executor, session))
        return proof

    with monkeypatch.context() as changes:
        changes.setattr(host, 'prove_r4_native_session', evidence_changes_while_proving)
        with pytest.raises(CoreError, match='SESSION_CONFLICT'):
            client.portal.call(owner.prove_native_presentation_owner, scope)
    emit('turn/completed', {'thread_id': thread, 'turn_id': native_turn,
                            'delivery_phase': 'terminal', 'delivery_outcome': 'success'})
    eventually(lambda: active() is None)
    assert native.native.sent == [('send_turn', operation)]


@pytest.mark.parametrize('condition,expected', [
    ('intact', 'VERIFIED'), ('changed', 'FILE_CHANGED'), ('interrupted_verification', 'VERIFIED'),
    ('no_live_evidence', None), ('unreleased_slot', 'CAPTURED'), ('legacy_witness', 'VERIFIED'),
])
def test_saved_codex_context_requires_retirement_and_same_history(
        interactive_runtime, tmp_path, monkeypatch, condition, expected):
    from nexus_connector_core import OperationKey, ProcessBirthEvidence
    from nexus_connector_core.native import process
    from nexus_connector_core.native.codex_rollout import observe_rollout

    from okto_nexus.bootstrap.embedded_saved_contexts import EmbeddedSavedContexts

    setup, binding, native = interactive_runtime
    deps, app, client, *_, workspace_root = setup
    opened = admit(setup, binding, 'saved-source-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    original = opened['scope']
    server, executor, session = (original[field] for field in ('server_id', 'executor_id', 'session_id'))
    scope = InputScope(SessionKey(server, executor, session),
        SessionOwnerGeneration(original['session_owner_generation']), original['binding_id'],
        original['workspace_id'], original['workspace_binding_id'], original['agent_id'])
    factory = deps.connection_factory
    owner = app.state.embedded_dispatch_owner

    def mapping():
        with factory.unit_of_work(write=False) as uow:
            return read_managed_native_session(uow, scope)

    eventually(mapping)
    source = mapping()
    with factory.unit_of_work(write=False) as uow:
        epoch = uow.connection.execute(
            'SELECT stream_epoch FROM execution_local_streams WHERE server_id=? AND executor_id=? AND session_id=?',
            (server, executor, session)).fetchone()[0]
    emit_codex_configuration(client, native, server, executor, session, epoch)
    eventually(lambda: mapping().codex_thread_id == CODEX_THREAD)
    reviewed = replace(source.launch_build, version='0.157.0', platform='win32',
        content_fingerprint='sha256:ed1c7b36e44536809c868864c833af8a857f56599a7a7fe23b908a1ba1093b1f')
    with factory.unit_of_work() as uow:
        migration = uow.connection.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
        assert migration >= 181
        uow.connection.execute('UPDATE execution_sessions SET native_launch_build_json=? WHERE session_id=?',
                               (json.dumps(asdict(reviewed)), session))

    _runtime, journal = owner.host._runtime_tasks[(executor, session)].result()
    birth = ProcessBirthEvidence('win32', 1234, 'filetime:12345678', 'windows_job')
    client.portal.call(journal.record_process_birth, OperationKey(server, executor, opened['operation_id']), session, birth)
    native.native.owned_process_birth = birth
    monkeypatch.setattr(process, 'observe_recorded_process_birth',
                        lambda evidence: 'MATCHING_LIVE' if evidence == birth else 'DIFFERENT_BIRTH')

    home = tmp_path / 'synthetic-codex-home'
    path = home / 'sessions' / 'rollout-fixture.jsonl'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'type': 'session_meta', 'payload': {
        'id': CODEX_THREAD, 'cwd': str(workspace_root.resolve())}})
        + '\n' + '{"type":"response_item","payload":{"text":"fixture-content"}}\n', encoding='utf-8')

    async def read_rollout(thread):
        assert thread == CODEX_THREAD and not native.native.stopped
        if condition == 'no_live_evidence':
            return None
        return observe_rollout(str(home), str(path), thread, str(workspace_root.resolve()))

    monkeypatch.setattr(native.native, 'read_owned_codex_rollout', read_rollout, raising=False)

    def stored():
        with factory.unit_of_work(write=False) as uow:
            rows = uow.connection.execute('SELECT * FROM embedded_saved_contexts WHERE session_id=?',
                                          (session,)).fetchall()
            assert len(rows) <= 1
            return dict(rows[0]) if rows else None

    original_close = native.native.close
    witnessed = []

    async def close():
        evidence = stored()
        witnessed.append(evidence['status'] if evidence else None)
        await owner.saved_contexts.reconcile(evidence['close_operation_id'] if evidence else None)
        assert stored() == evidence
        if condition == 'changed':
            with path.open('a', encoding='utf-8') as stream:
                stream.write('{"type":"response_item","payload":{"text":"different"}}\n')
        return await original_close()

    monkeypatch.setattr(native.native, 'close', close)
    if condition == 'interrupted_verification':
        def cannot_commit(*_args):
            raise OSError('Synthetic interruption before committing the verification.')
        monkeypatch.setattr(owner.saved_contexts, '_resolve', cannot_commit)
    if condition == 'unreleased_slot':
        ledger = client.portal.call(owner.host._ledger)
        current = ledger.owned_slot_state

        async def no_release_proof(key):
            slot = await current(key)
            return replace(slot, released=False) if slot is not None else None

        monkeypatch.setattr(ledger, 'owned_slot_state', no_release_proof)

    closed = admit(setup, binding, 'saved-source-close', 'runtime.close', session_id=session)
    wait_receipt(setup, closed, stages=('SUCCEEDED',))
    assert witnessed == ([None] if expected is None else ['CAPTURED'])
    assert native.opens == 1 and native.native.stopped and native.native.sent == []

    if condition == 'interrupted_verification':
        assert stored()['status'] == 'CAPTURED'
        # A new reconciler uses only the persisted candidate and exact receipts.
        client.portal.call(EmbeddedSavedContexts(owner).reconcile)
    if expected is None:
        assert stored() is None
    else:
        eventually(lambda: stored()['status'] == expected)
        witness = stored()
        assert witness['opening_operation_id'] == opened['operation_id']
        assert witness['close_operation_id'] == closed['operation_id']
        assert 'fixture-content' not in witness['witness_json']
        assert (witness['release_digest'] is not None) == (expected == 'VERIFIED')
        if expected == 'VERIFIED':
            assert witness['release_digest'].startswith('sha256:')
    if condition == 'unreleased_slot':
        # End the injected observation failure before the fixture drains its
        # independent Core stores at service shutdown.
        monkeypatch.setattr(ledger, 'owned_slot_state', current)
    if condition == 'legacy_witness':
        before_profile_attestation = json.loads(stored()['witness_json'])
        del before_profile_attestation['opening_profile']
        del before_profile_attestation['opening_binding_digest']
        with factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE embedded_saved_contexts SET witness_json=? WHERE session_id=?',
                                   (json.dumps(before_profile_attestation), session))
    if condition in ('intact', 'legacy_witness'):
        _exercise_saved_resume_admission(setup, binding, source.scope, native)


def _exercise_saved_resume_admission(setup, binding, scope, native):
    from pathlib import Path

    from jsonschema import Draft202012Validator

    deps, app, client, headers, *_ = setup
    request = {'client_intent_id': 'saved-resume', 'intent': 'runtime.resume_saved',
               'agent_id': binding['agent_id'], 'binding_id': scope.binding_id,
               'workspace_binding_id': scope.workspace_binding_id, 'session_id': scope.session.session_id,
               'source_session_generation': scope.generation.value}
    assert client.post('/v1/runtime/intents:resolve', headers=headers['subject'], json=request).status_code == 403
    auth = app.state.operator_auth
    assert auth.configure('resume-fixture', 'fixture-resume-password', local=True)
    token = auth.login('resume-fixture', 'fixture-resume-password')
    human = {'cookie': f'nexus_operator_session={token}', 'x-nexus-ui': '1', 'origin': 'http://127.0.0.1'}
    prefix = 'http://127.0.0.1/api/v1/runtime-management/runtime'
    wrong = client.post(prefix + '/intents:resolve', headers=human,
                        json=request | {'source_session_generation': scope.generation.value + 1})
    assert wrong.status_code == 409, wrong.text
    reviewed = client.post(prefix + '/intents:resolve', headers=human, json=request)
    another = client.post(prefix + '/intents:resolve', headers=human, json=request | {'client_intent_id': 'another-resume'})
    assert reviewed.status_code == another.status_code == 200, (reviewed.text, another.text)
    schemas = json.loads((Path(__file__).resolve().parents[2] / 'plans/contratos/http-target.schema.json').read_text('utf-8'))
    resolution = reviewed.json()
    Draft202012Validator({'$defs': schemas['$defs'], '$ref': '#/$defs/ResolveIntentRequest'}).validate(request)
    Draft202012Validator({'$defs': schemas['$defs'], '$ref': '#/$defs/IntentResolution'}).validate(resolution)
    assert resolution['session_id'] != request['session_id'] and resolution['reuse'] is False
    assert resolution['saved_resume']['source_session_id'] == request['session_id']
    assert all(private not in reviewed.text for private in (CODEX_THREAD, 'rollout-fixture.jsonl', token))

    def submit(resolved):
        return client.post(prefix + '/operations', headers=human, json={
            name: resolved[name] for name in ('client_intent_id', 'operation_id', 'resolution_revision', 'intent_hash')
        })

    admission = submit(resolution)
    assert admission.status_code == 202, admission.text
    assert submit(resolution).status_code == 200
    assert submit(another.json()).status_code == 409
    recovered = client.get(prefix + '/intents/saved-resume', headers=human)
    assert recovered.status_code == 200 and recovered.json()['resolution'] == resolution
    with deps.connection_factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        successor, retained = conn.execute("""
            SELECT session_id, saved_resume_json FROM execution_sessions WHERE saved_resume_json IS NOT NULL
        """).fetchone()
        assert successor == resolution['session_id'] and json.loads(retained) == resolution['saved_resume']
        assert conn.execute("SELECT count(*) FROM execution_operations WHERE session_id=? AND action<>'runtime.open'",
                            (successor,)).fetchone()[0] == 0
    # This source is a fake Core native and its declared build differs from the
    # reviewed source metadata. Dispatch must contain it before a fresh open.
    assert native.opens == 1


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
    thread = CODEX_THREAD
    emit_codex_configuration(client, native, server, executor, session, epoch)
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

    catalog = client.get(path + '/commands', params=query).json()
    command = body | {'command': 'interrupt', 'catalog_revision': catalog['capability_revision'], 'confirmed': True}
    assert client.post(path + '/commands:execute', json=command | {'catalog_revision': 'stale'}, headers=ui).status_code == 409
    assert client.get(path + '/inputs', params=query).json()['paused'] is False
    stopped = client.post(path + '/commands:execute', json=command, headers=ui)
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
    assert client.get(path + '/commands', params=query).status_code == 401
    auth = app.state.operator_auth
    assert auth.configure('steer-fixture', 'fixture-password-long', local=True)
    token = auth.login('steer-fixture', 'fixture-password-long')
    client.cookies.set('nexus_operator_session', token)

    def preview():
        response = client.get(path + '/steer', params=query)
        assert response.status_code == 200, response.text
        return response.json()['control']

    def catalog():
        response = client.get(path + '/commands', params=query)
        assert response.status_code == 200, response.text
        assert response.headers['cache-control'] == 'no-store'
        result = response.json()
        assert result['scope'] == exact and result['session_owner_generation'] == generation
        assert result['version'] == 1 and result['adapter_id'] == 'codex_app_server'
        assert result['literal_text_supported'] is False
        return result['capability_revision'], {item['command_id']: item for item in result['items']}

    assert preview() is None
    idle_revision, idle_commands = catalog()
    assert catalog()[0] == idle_revision
    assert idle_commands['help']['source'] == 'nexus' and idle_commands['status']['handler'] == 'session_status'
    assert idle_commands['send']['state'] == 'supported' and idle_commands['send']['arguments'] == ['message']
    assert idle_commands['steer']['state'] == idle_commands['interrupt']['state'] == 'disabled_for_state'
    assert idle_commands['resume']['state'] == 'native_only' and idle_commands['resume']['handler'] is None
    assert idle_commands['compact']['state'] == 'unqualified' and idle_commands['compact']['handler'] is None
    assert not {'shell', 'install', 'login', 'extension'} & idle_commands.keys()
    assert client.get(path + '/commands', params=query | {'command': 'shell'}).status_code == 422
    assert client.get(path + '/commands', params=query | {'expected_session_generation': generation + 1}).status_code == 404
    assert client.post(path + '/commands', headers=ui, json={'command': 'shell'}).status_code == 405
    for name in ('shell', 'resume', 'model', '/tmp/file', 'extension'):
        blocked = client.post(path + '/commands:execute', headers=ui, json=base | {
            'command': name, 'catalog_revision': idle_revision, 'argv': ['private-fixture-argument'],
        })
        assert blocked.status_code == 422 and 'private-fixture-argument' not in blocked.text
    help_view = client.post(path + '/commands:execute', headers=ui,
                            json=base | {'command': 'help', 'catalog_revision': idle_revision})
    assert help_view.status_code == 200 and help_view.json()['capability_revision'] == idle_revision
    status_view = client.post(path + '/commands:execute', headers=ui,
                              json=base | {'command': 'status', 'catalog_revision': idle_revision})
    assert status_view.status_code == 200 and status_view.json()['lifecycle_state'] == 'READY'
    assert auth.authority_reference(token, create=False) is None
    assert native.native.sent == []
    active = admit(setup, binding, 'steer-active', 'turn.submit', session_id=session, text='Synthetic turn for steering')
    wait_receipt(setup, active)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        epoch = uow.connection.execute('SELECT stream_epoch FROM execution_local_streams WHERE session_id=?',
                                       (session,)).fetchone()[0]
    thread, turn = CODEX_THREAD, native.native.active_turn_id
    emit_codex_configuration(client, native, server, executor, session, epoch)
    client.portal.call(native.native.queue.put, RuntimeEvent(server, executor, session, epoch, 0,
        'turn_state', 'turn/started', {'turn_id': turn, 'thread_id': thread, 'threadId': thread,
            'turn': {'id': turn, 'status': 'inProgress'}, 'delivery_phase': 'started'}, operation_id=active['operation_id']))
    eventually(preview)
    active_revision, active_commands = catalog()
    assert active_revision != idle_revision
    assert active_commands['steer']['state'] == active_commands['interrupt']['state'] == 'supported'
    assert active_commands['steer']['requires_confirmation'] and active_commands['interrupt']['requires_confirmation']
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
    command = body | {'command': 'steer', 'catalog_revision': active_revision, 'confirmed': True}
    stale_command = client.post(path + '/commands:execute', headers=ui, json=command | {'catalog_revision': idle_revision})
    assert stale_command.status_code == 409 and 'Session commands changed.' in stale_command.text
    direct = client.post(path + '/commands:execute', headers=ui, json=command)
    assert direct.status_code == 202, direct.text
    first = direct.json()
    assert first['reorientation'] is True
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
    assert receipt(input_id=to_promote['input_id'])['reorientation'] is False
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
    assert second['input_id'] == to_promote['input_id'] and second['reorientation'] is True
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
    settled_revision, settled_commands = catalog()
    assert settled_revision != active_revision
    assert settled_commands['steer']['state'] == settled_commands['interrupt']['state'] == 'disabled_for_state'
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agents SET metadata=json_set(COALESCE(metadata, '{}'), '$.fixture', 1) WHERE agent_id=?",
                               (scope['agent_id'],))
    updated_revision, _ = catalog()
    assert updated_revision != settled_revision
    assert catalog()[0] == updated_revision
    client.cookies.clear()
