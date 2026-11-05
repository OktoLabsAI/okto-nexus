"""Terminal facade over real operator HTTP, admission, dispatch and receipts."""
from copy import deepcopy
import json
from types import SimpleNamespace
import time

import pytest
from nexus_connector_core import RuntimeEvent

import test_embedded_dispatch
from test_canonical_result_publication import emit
from okto_nexus.application.terminal_connection import ConnectionError, document_revision
from okto_nexus.application.terminal_work import TerminalWork

local_setup = test_embedded_dispatch.local_setup
connected_local = test_embedded_dispatch.connected_local
qualified_contract = test_embedded_dispatch.qualified_contract
wait_receipt = test_embedded_dispatch.wait_receipt


@pytest.fixture
def work(connected_local):
    setup, binding, native = connected_local
    deps, app, client, *_ = setup
    saved, calls = [], []
    fault = SimpleNamespace(after=None, before=None)
    def call(method, path, body=None):
        calls.append((method, path))
        if fault.before and path.endswith(fault.before):
            fault.before = None
            raise ConnectionError('OUTCOME_UNKNOWN', 'Injected lost request', possible_effect=True)
        response = client.request(method, path, json=body, headers={'X-Nexus-UI': '1'})
        value = response.json()
        if response.status_code >= 400:
            error = value.get('error', {})
            raise ConnectionError(error.get('code', 'VALIDATION_ERROR'), error.get('message', response.text),
                                  stage=error.get('stage', 'http'))
        if fault.after and path.endswith(fault.after):
            fault.after = None
            raise ConnectionError('OUTCOME_UNKNOWN', 'Injected lost response', possible_effect=True)
        return value
    connection = dict(state='done', server_id=binding['server_id'], selection=dict(agent='subject', client='codex',
        project=str(setup[6].resolve()), workspace_id=None, candidate_ref=None, provider_home=None), result={'binding': binding})
    def save(document):
        saved.append(deepcopy(document))
    flow = TerminalWork(call, save, connection)
    return SimpleNamespace(setup=setup, binding=binding, native=native, deps=deps, app=app,
        flow=flow, connection=connection, save=save, saved=saved, calls=calls, call=call, fault=fault)


def complete(t, operation, text='Canonical project result'):
    turn = {'operation_id': operation['submission_turn_operation_id']} if operation.get('submission_turn_operation_id') else operation
    wait_receipt(t.setup, turn)
    emit(t.setup, t.native, turn, text)
    return turn


def test_send_result_reopen_continue_and_close_share_canonical_session(work):
    t = work
    operation = t.flow.submit('Private project request', client_intent_id='terminal-first')
    first = complete(t, operation)
    result = t.flow.observe()
    assert result['state'] == 'completed'
    assert result['operations'][-1]['result']['output_text'] == 'Canonical project result'
    assert 'Private project request' not in json.dumps(t.saved)
    assert 'Canonical project result' not in json.dumps(t.saved)
    reopened = TerminalWork(t.call, t.save, t.connection, t.saved[-1])
    assert reopened.observe()['operations'][-1]['operation_id'] == first['operation_id']
    assert reopened.submit('Private project request', client_intent_id='terminal-first')['operation_id'] == operation['operation_id']
    second = reopened.submit('Continue the conversation')
    assert second['scope']['session_id'] == operation['scope']['session_id']
    complete(t, second, 'Second result')
    assert reopened.observe()['operations'][-1]['result']['output_text'] == 'Second result'
    assert len(reopened.sessions()['sessions']) == 1 and t.native.opens == 1
    closed = reopened.submit(action='close')
    wait_receipt(t.setup, closed, stages=('SUCCEEDED',))
    assert reopened.observe()['session']['lifecycle_state'] == 'CLOSED'
    assert t.native.native.stopped


@pytest.mark.parametrize('lost', ['intents:resolve', '/runtime/operations'])
def test_lost_submission_response_recovers_same_work_without_duplicate_dispatch(work, lost):
    t = work
    t.fault.after = lost
    with pytest.raises(ConnectionError, match='Injected'):
        t.flow.submit('Exactly once')
    recovered = TerminalWork(t.call, t.save, t.connection, t.saved[-1])
    operation = recovered.resume()
    complete(t, operation)
    again = recovered.resume()
    assert again['operation_id'] == operation['operation_id']
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_operations').fetchone()[0] == 2
    assert t.native.opens == 1
    assert [item[0] for item in t.native.native.sent] == ['send_turn']


def test_unconfirmed_resolution_requires_exact_original_request(work):
    t = work
    t.fault.before = 'intents:resolve'
    with pytest.raises(ConnectionError):
        t.flow.submit('Original text')
    with pytest.raises(ConnectionError) as missing:
        t.flow.resume()
    assert missing.value.code == 'INTENT_NOT_FOUND'
    with pytest.raises(ConnectionError) as conflict:
        t.flow.submit('Changed text')
    assert conflict.value.code == 'WORK_REQUEST_CONFLICT'
    assert t.native.opens == 0
    operation = t.flow.submit('Original text')
    complete(t, operation)
    assert t.native.opens == 1


@pytest.mark.parametrize('kind,enabled', [('input', True), ('approval', True), ('approval', False)])
def test_native_decision_response_loss_recovers_canonical_result_and_keeps_answers_out_of_profile(work, kind, enabled):
    t = work
    t.deps.config.feature_hitl = enabled  # Qualify the existing native-decision policy explicitly.
    operation = t.flow.submit('Ask before proceeding')
    turn = {'operation_id': operation['follow_up_operation_ids'][0]}
    wait_receipt(t.setup, turn)
    replies = []
    async def reply(request, decision, response):
        replies.append((decision, response))
    t.native.native.reply_native_approval = reply
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    request = dict(schema_version=1, request_id=7, request_hash='a' * 64,
        method='item/tool/requestUserInput' if kind == 'input' else 'item/commandExecution/requestApproval',
        params={'threadId': 'native-thread', 'turnId': 'turn-from-native', 'itemId': 'item'})
    if kind == 'input':
        request['params'].update(isBlocking=True, questions=[dict(id='question', header='Response',
            question='Select an answer.', isOther=True)])
    t.setup[2].portal.call(t.native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
        stream['session_id'], stream['stream_epoch'], 0, 'input_request' if kind == 'input' else 'approval_request',
        request['method'], {'native_approval': request, 'native_approval_display': dict(request)}, turn['operation_id']))
    deadline = time.monotonic() + 15
    while True:
        observed = t.flow.observe()
        if observed['requests']['items']:
            break
        assert time.monotonic() < deadline
        time.sleep(.03)
    assert observed['state'] == 'needs_input'
    detail = observed['requests']['items'][0]
    proposal = detail['request_payload']['kwargs']
    assert proposal.get('recipient_agent_id', 'operator') == 'operator'
    response = {'answers': {'question': {'answers': ['Private answer marker']}}} if kind == 'input' else None
    if kind == 'input':
        with pytest.raises(ConnectionError) as invalid:
            t.flow.decide(detail['approval_id'], 'approve', response={'answers': {}},
                          reviewed_revision=document_revision(proposal))
        assert invalid.value.code == 'VALIDATION_ERROR'
        assert 'decision' not in t.flow.document
        assert replies == []
        t.calls.clear()
    t.fault.after = '/runtime/approval-decisions'
    with pytest.raises(ConnectionError, match='Injected'):
        t.flow.decide(detail['approval_id'], 'approve', response=response, reviewed_revision=document_revision(proposal))
    resumed = TerminalWork(t.call, t.save, t.connection, t.saved[-1])
    decision = resumed.decide(detail['approval_id'], 'approve', response=response,
                              reviewed_revision=document_revision(proposal))
    assert decision['canonical_state'] == 'CONFIRMED'
    assert sum(path.endswith('/runtime/approval-decisions') for _, path in t.calls) == 1
    assert 'Private answer marker' not in json.dumps(t.saved)
    deadline = time.monotonic() + 15
    if not enabled:
        while True:
            observed = resumed.observe()
            if observed['state'] == 'decision_refused':
                break
            assert time.monotonic() < deadline
            time.sleep(.03)
        assert observed['decision']['native_stage'] == 'REFUSED_BEFORE_EFFECT'
        assert observed['decision']['operation']['error'] is not None
        assert replies == []
        return
    while not replies:
        assert time.monotonic() < deadline, t.flow.api('GET', '/runtime/approval-decisions/' + decision['decision_id'])
        time.sleep(.03)
    assert len(replies) == 1
    complete(t, turn)
    assert resumed.observe()['state'] == 'completed'


def test_cli_submission_resume_watch_and_project_mismatch(work, tmp_path, monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli import work as cli
    from okto_nexus.adapters.outbound.service_manager.context import atomic_json

    t = work
    home = tmp_path / 'terminal-home'
    profile = home / 'terminal/profiles/project.json'
    profile.parent.mkdir(parents=True)
    atomic_json(profile, t.connection)
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=8202),
                               inspect=lambda: {'state': 'ready'})
    monkeypatch.setattr(cli, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(cli, 'LocalOperatorHTTP', lambda **kwargs: t.call)
    t.fault.after = '/runtime/operations'
    base = ['--profile', 'project', '--json']
    assert cli.run_work(['send', '--message', 'CLI private request', *base]) == 3
    assert json.loads(capsys.readouterr().out)['state'] == 'unconfirmed'
    assert cli.run_work(['resume', *base]) == 0
    admitted = json.loads(capsys.readouterr().out)
    complete(t, admitted, 'CLI result')
    assert cli.run_work(['watch', '--timeout', '.1', *base]) == 0
    assert json.loads(capsys.readouterr().out)['operations'][-1]['result']['output_text'] == 'CLI result'
    checkpoint = (home / 'terminal/work/project.json').read_text(encoding='utf-8')
    assert 'CLI private request' not in checkpoint and 'CLI result' not in checkpoint
    assert cli.run_work(['send', '--message', 'Wrong directory', '--project', str(tmp_path), *base]) == 3
    assert json.loads(capsys.readouterr().out)['code'] == 'PROFILE_CONFLICT'
    assert t.native.opens == 1 and len(t.native.native.sent) == 1


def test_scope_change_and_explicit_request_conflict_do_not_dispatch(work):
    t = work
    operation = t.flow.submit('Original', client_intent_id='stable-work')
    complete(t, operation)
    with pytest.raises(ConnectionError) as conflict:
        t.flow.submit('Changed', client_intent_id='stable-work')
    assert conflict.value.code == 'WORK_REQUEST_CONFLICT'
    t.flow.connection['selection']['project'] += '-another'
    with pytest.raises(ConnectionError) as changed:
        t.flow.submit('Must not run')
    assert changed.value.code == 'PROFILE_DRIFT'
    assert len(t.native.native.sent) == 1


def test_profile_without_work_checkpoint_reuses_session_but_observes_only_its_own_initial_turn(work):
    t = work
    original = t.flow.submit('Earlier request')
    earlier = complete(t, original, 'Earlier answer')
    fresh_profile = TerminalWork(t.call, t.save, t.connection)
    reused = fresh_profile.submit('New request through the existing connection')
    assert reused['operation_id'] == original['operation_id']
    assert reused['submission_turn_operation_id'] != earlier['operation_id']
    assert len(reused['follow_up_operation_ids']) == 2
    complete(t, reused, 'Only the new answer')
    observed = fresh_profile.observe()
    assert observed['state'] == 'completed'
    assert len(observed['operations']) == 2
    assert observed['operations'][-1]['result']['output_text'] == 'Only the new answer'
    assert earlier['operation_id'] not in [item['operation_id'] for item in observed['operations']]
    assert t.native.opens == 1


@pytest.mark.parametrize('interruption', [KeyboardInterrupt, EOFError])
def test_leaving_interactive_cli_does_not_interrupt_or_close_service_owned_work(work, tmp_path, monkeypatch, capsys, interruption):
    from okto_nexus.adapters.inbound.cli import work as cli
    from okto_nexus.adapters.outbound.service_manager.context import atomic_json

    t = work
    admitted = t.flow.submit('Continue after the terminal exits')
    wait_receipt(t.setup, {'operation_id': admitted['submission_turn_operation_id']})
    home = tmp_path / 'terminal-home'
    for directory, value in [('profiles', t.connection), ('work', t.flow.document)]:
        target = home / 'terminal' / directory / 'project.json'
        target.parent.mkdir(parents=True)
        atomic_json(target, value)
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=8202),
                               inspect=lambda: {'state': 'ready'})
    monkeypatch.setattr(cli, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(cli, 'LocalOperatorHTTP', lambda **kwargs: t.call)
    monkeypatch.setattr(cli.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    def leave(prompt):
        raise interruption()
    monkeypatch.setattr('builtins.input', leave)
    assert cli.run_work(['chat', '--profile', 'project']) == (130 if interruption is KeyboardInterrupt else 0)
    assert not t.native.native.stopped
    assert [item[0] for item in t.native.native.sent] == ['send_turn']
    assert t.flow.observe()['session']['control_available']


@pytest.mark.parametrize('interruption', [KeyboardInterrupt, EOFError])
def test_leaving_standalone_question_preserves_pending_request(work, tmp_path, monkeypatch, capsys, interruption):
    from okto_nexus.adapters.inbound.cli import work as cli
    from okto_nexus.adapters.outbound.service_manager.context import atomic_json, read_json

    t = work
    operation = t.flow.submit('Wait for the explicit decision')
    turn = {'operation_id': operation['submission_turn_operation_id']}
    wait_receipt(t.setup, turn)
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    request = dict(schema_version=1, request_id=8, request_hash='b' * 64,
        method='item/commandExecution/requestApproval',
        params={'threadId': 'native-thread', 'turnId': 'turn-from-native', 'itemId': 'item'})
    t.setup[2].portal.call(t.native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
        stream['session_id'], stream['stream_epoch'], 0, 'approval_request', request['method'],
        {'native_approval': request, 'native_approval_display': dict(request)}, turn['operation_id']))
    deadline = time.monotonic() + 15
    while not (pending := t.flow.observe()['requests']['items']):
        assert time.monotonic() < deadline
        time.sleep(.03)
    approval_id = pending[0]['approval_id']
    home = tmp_path / 'terminal-home'
    for directory, value in [('profiles', t.connection), ('work', t.flow.document)]:
        target = home / 'terminal' / directory / 'project.json'
        target.parent.mkdir(parents=True)
        atomic_json(target, value)
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=8202),
                               inspect=lambda: {'state': 'ready'})
    monkeypatch.setattr(cli, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(cli, 'LocalOperatorHTTP', lambda **kwargs: t.call)
    monkeypatch.setattr(cli.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    def leave(prompt):
        raise interruption()
    monkeypatch.setattr('builtins.input', leave)
    for action in [['watch'], ['answer', '--approval-id', approval_id]]:
        assert cli.run_work([*action, '--profile', 'project', '--timeout', '5']) == (
            130 if interruption is KeyboardInterrupt else 0)
        assert t.flow.decision_detail(approval_id)['status'] == 'pending'
        assert 'decision' not in read_json(home / 'terminal/work/project.json')
        assert not t.native.native.stopped
    assert not any(method == 'POST' and path.endswith('/approval-decisions') for method, path in t.calls)
    assert [item[0] for item in t.native.native.sent] == ['send_turn']
    assert t.flow.observe()['session']['control_available']


def test_interactive_cli_request_question_answer_result_and_return(work, tmp_path, monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli import work as cli
    from okto_nexus.adapters.outbound.service_manager.context import atomic_json, read_json

    t = work
    t.deps.config.feature_hitl = True
    original_open = t.native.open
    replies = []
    async def open_with_question(prepared, session_id, context, *, stream_epoch):
        native = await original_open(prepared, session_id, context, stream_epoch=stream_epoch)
        original_send = native.send
        turns = []
        async def send(verb, payload, operation_id, **kwargs):
            await original_send(verb, payload, operation_id, **kwargs)
            if verb != 'send_turn':
                return
            turns.append(operation_id)
            request = dict(schema_version=1, request_id=7, request_hash='a' * 64,
                method='item/tool/requestUserInput', params=dict(threadId='native-thread', turnId='turn-from-native',
                    itemId='item', isBlocking=True, questions=[dict(id='question', header='Choice',
                        question='Which change should be made?', isOther=True)]))
            await native.queue.put(RuntimeEvent(context.server_id, context.executor_id, session_id, stream_epoch, 0,
                'input_request', request['method'], {'native_approval': request, 'native_approval_display': dict(request)}, operation_id))
        async def reply(request, decision, response):
            replies.append((decision, response))
            await native.queue.put(RuntimeEvent(context.server_id, context.executor_id, session_id, stream_epoch, 0,
                'turn_state', 'fixture.completed', dict(delivery_phase='terminal', delivery_outcome='success',
                    output_text='Interactive terminal work completed.'), turns[-1]))
        native.send, native.reply_native_approval = send, reply
        return native
    monkeypatch.setattr(t.native, 'open', open_with_question)
    home = tmp_path / 'terminal-home'
    profile = home / 'terminal/profiles/project.json'
    profile.parent.mkdir(parents=True)
    atomic_json(profile, t.connection)
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=8202),
                               inspect=lambda: {'state': 'ready'})
    monkeypatch.setattr(cli, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(cli, 'LocalOperatorHTTP', lambda **kwargs: t.call)
    monkeypatch.setattr(cli.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    inputs = iter(['Implement the requested project change', 'yes', 'Use the reviewed option', '/quit'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(inputs))
    assert cli.run_work(['chat', '--profile', 'project', '--timeout', '30']) == 0
    output = capsys.readouterr().out
    assert 'Which change should be made?' in output
    assert 'Interactive terminal work completed.' in output
    assert replies == [('accept', {'answers': {'question': {'answers': ['Use the reviewed option']}}})]
    checkpoint = read_json(home / 'terminal/work/project.json')
    assert 'Use the reviewed option' not in json.dumps(checkpoint)
    assert 'Implement the requested project change' not in json.dumps(checkpoint)
    assert not t.native.native.stopped
    assert cli.run_work(['status', '--profile', 'project', '--json']) == 0
    returned = json.loads(capsys.readouterr().out)
    assert returned['state'] == 'completed'
    assert returned['operations'][-1]['result']['output_text'] == 'Interactive terminal work completed.'
    assert t.native.opens == 1 and len(t.native.native.sent) == 1
