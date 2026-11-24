"""Terminal facade over real operator HTTP, admission, dispatch and receipts."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from threading import Barrier
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
def drain_cli(work, tmp_path, monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli import work as cli
    from okto_nexus.adapters.outbound.service_manager.context import atomic_json
    from okto_nexus.application.service_lifecycle import project_server_readiness
    from dataclasses import asdict

    t = work
    home = tmp_path / 'terminal-home'
    profile = home / 'terminal/profiles/project.json'
    profile.parent.mkdir(parents=True)
    atomic_json(profile, t.connection)
    def inspect():
        return asdict(project_server_readiness(identity='fixture-owner', generation='fixture-generation',
            version='fixture', pid=1, owns_instance=True, startup_complete=True,
            admission_closed=t.deps.runtime_admission_fence.closed,
            shutdown_state=t.app.state.runtime_shutdown.status()['state']))
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=8202), inspect=inspect)
    monkeypatch.setattr(cli, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(cli, 'LocalOperatorHTTP', lambda **kwargs: t.call)
    def run(*args):
        code = cli.run_work([*args, '--home', str(home), '--profile', 'project', '--json'])
        return code, json.loads(capsys.readouterr().out)
    def stop():
        response = t.setup[2].post('/v1/runtime/shutdown', headers=t.setup[3]['operator'],
                                  json={'timeout_seconds': .02})
        assert response.status_code == 202 and response.json()['phase'] == 'waiting'
        assert inspect()['state'] == 'stopping' and inspect()['ready_for_queries'] is True
    return SimpleNamespace(work=t, home=home, run=run, stop=stop)


@pytest.mark.parametrize('action', ['interrupt', 'close'])
def test_cli_drain_observes_and_recovers_one_containment_operation(drain_cli, action):
    d, t = drain_cli, drain_cli.work
    code, operation = d.run('send', '--message', 'Synthetic admitted task')
    assert code == 0
    turn = {'operation_id': operation['submission_turn_operation_id']}
    wait_receipt(t.setup, turn)
    d.stop()
    t.calls.clear()
    for command in [('status',), ('events',), ('sessions',), ('watch', '--timeout', '.01')]:
        code, observed = d.run(*command)
        assert code == (3 if command[0] == 'watch' else 0), observed
        assert observed.get('state') != 'service_not_ready'
    assert all(method == 'GET' for method, _ in t.calls)
    t.fault.after = '/runtime/operations'
    options = ['--target-turn-id', 'turn-from-native'] if action == 'interrupt' else []
    code, failed = d.run(action, *options)
    assert code == 3 and failed['state'] == 'unconfirmed'
    code, recovered = d.run('resume', '--control')
    assert code == 0
    assert recovered['action'] == ('turn.interrupt' if action == 'interrupt' else 'runtime.close')
    wait_receipt(t.setup, recovered)
    assert sum(method == 'POST' and path.endswith('/runtime/operations') for method, path in t.calls) == 1
    assert sum(verb == action for verb, _ in t.native.native.sent) == (1 if action == 'interrupt' else 0)
    if action == 'close':
        # This peer closes without publishing the turn's terminal fact. A close
        # receipt must not manufacture completion or release that uncertainty.
        report = t.app.state.runtime_shutdown.status()
        assert report['state'] == 'DRAINING_PENDING' and not report['force_requested']
        assert t.native.native.stopped and t.native.opens == 1
        with t.deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT admission_state FROM execution_operations WHERE operation_id=?',
                (turn['operation_id'],)).fetchone()[0] != 'RESOLVED_TERMINAL'
        return
    complete(t, operation, 'Synthetic terminal after interrupt')
    deadline = time.monotonic() + 15
    while t.app.state.runtime_shutdown.status()['state'] != 'DRAINED':
        assert time.monotonic() < deadline, json.dumps(t.app.state.runtime_shutdown.status(), sort_keys=True)
        time.sleep(.03)
    assert t.native.native.stopped and t.native.opens == 1
    assert not t.app.state.runtime_shutdown.status()['force_requested']


def test_cli_drain_keeps_reviewed_native_decision_available(drain_cli):
    d, t = drain_cli, drain_cli.work
    t.deps.config.feature_hitl = True
    code, operation = d.run('send', '--message', 'Synthetic task needing approval')
    assert code == 0
    turn = {'operation_id': operation['submission_turn_operation_id']}
    wait_receipt(t.setup, turn)
    replies = []
    async def reply(request, decision, response):
        replies.append(decision)
    t.native.native.reply_native_approval = reply
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams').fetchone())
    request = dict(schema_version=1, request_id=7, request_hash='a' * 64,
        method='item/commandExecution/requestApproval',
        params={'threadId': 'native-thread', 'turnId': 'turn-from-native', 'itemId': 'item'})
    t.setup[2].portal.call(t.native.native.queue.put, RuntimeEvent(stream['server_id'], stream['executor_id'],
        stream['session_id'], stream['stream_epoch'], 0, 'approval_request', request['method'],
        {'native_approval': request, 'native_approval_display': dict(request)}, turn['operation_id']))
    deadline = time.monotonic() + 15
    while True:
        code, observed = d.run('status')
        assert code == 0
        if observed['requests']['items']:
            break
        assert time.monotonic() < deadline
        time.sleep(.03)
    approval_id = observed['requests']['items'][0]['approval_id']
    d.stop()
    code, review = d.run('answer', '--approval-id', approval_id)
    assert code == 0 and review['state'] == 'decision_review' and not replies
    code, decision = d.run('answer', '--approval-id', approval_id, '--decision', 'approve',
                           '--review', review['review_revision'])
    assert code == 0 and decision['canonical_state'] == 'CONFIRMED'
    while not replies:
        assert time.monotonic() < deadline
        time.sleep(.03)
    assert replies == ['accept']
    complete(t, operation)


@pytest.mark.parametrize('state,queries,command,control', [
    ('stopping', True, ['send', '--message', 'No new work'], None),
    ('stopping', True, ['steer', '--message', 'No steering'], None),
    ('stopping', True, ['authorize'], None),
    ('stopping', True, ['chat'], None),
    ('stopping', True, ['resume'], None),
    ('stopping', True, ['resume', '--control'], None),
    ('stopping', True, ['resume', '--control'], {'intent': 'turn.submit'}),
    ('stopping', False, ['status'], None),
    ('stopping', None, ['interrupt'], None),
    ('unknown', True, ['status'], None),
    ('degraded', True, ['interrupt'], None),
    ('failed', True, ['close'], None),
])
def test_cli_drain_refuses_productive_or_unverified_service_before_http(
        tmp_path, monkeypatch, capsys, state, queries, command, control):
    from okto_nexus.adapters.inbound.cli import work as cli
    from okto_nexus.adapters.outbound.service_manager.context import atomic_json

    home = tmp_path / 'terminal-home'
    profile = home / 'terminal/profiles/project.json'
    profile.parent.mkdir(parents=True)
    atomic_json(profile, {})
    if control is not None:
        checkpoint = home / 'terminal/work/project.json'
        checkpoint.parent.mkdir(parents=True)
        atomic_json(checkpoint, {'control': control})
    service = SimpleNamespace(adapter=SimpleNamespace(home=home),
        inspect=lambda: dict(state=state, ready_for_queries=queries))
    monkeypatch.setattr(cli, 'resolve_local_service', lambda args: service)
    monkeypatch.setattr(cli, 'open_work', lambda *args: pytest.fail('Refused action opened the HTTP/work client'))
    output_args = ['--json']
    if command == ['chat']:
        monkeypatch.setattr(cli.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
        output_args = []
    assert cli.run_work([*command, '--home', str(home), '--profile', 'project', *output_args]) == 3
    assert json.loads(capsys.readouterr().out)['state'] == 'service_not_ready'


def test_cli_drain_rechecks_control_checkpoint_after_profile_lock(tmp_path, monkeypatch, capsys):
    from okto_nexus.adapters.inbound.cli import work as cli
    from okto_nexus.adapters.outbound.service_manager.context import atomic_json

    home = tmp_path / 'terminal-home'
    profile = home / 'terminal/profiles/project.json'
    profile.parent.mkdir(parents=True)
    atomic_json(profile, {})
    checkpoint = home / 'terminal/work/project.json'
    checkpoint.parent.mkdir(parents=True)
    atomic_json(checkpoint, {'control': {'intent': 'turn.interrupt'}})
    service = SimpleNamespace(adapter=SimpleNamespace(home=home),
        inspect=lambda: dict(state='stopping', ready_for_queries=True))
    monkeypatch.setattr(cli, 'resolve_local_service', lambda args: service)
    lock = cli.ExclusiveFileLock
    class ChangedCheckpointLock:
        def __init__(self, path):
            self.guard = lock(path)
        def acquire(self):
            atomic_json(checkpoint, {'control': {'intent': 'turn.submit'}})
            self.guard.acquire()
        def release(self):
            self.guard.release()
    monkeypatch.setattr(cli, 'ExclusiveFileLock', ChangedCheckpointLock)
    def open_work(*args):
        return SimpleNamespace(document=json.loads(checkpoint.read_text(encoding='utf8')),
            resume=lambda *args: pytest.fail('Changed checkpoint attempted productive resume'))
    monkeypatch.setattr(cli, 'open_work', open_work)
    assert cli.run_work(['resume', '--control', '--home', str(home), '--profile', 'project', '--json']) == 3
    assert json.loads(capsys.readouterr().out)['state'] == 'service_not_ready'


@pytest.fixture
def work(connected_local):
    setup, binding, native = connected_local
    deps, app, client, *_ = setup
    saved, calls = [], []
    fault = SimpleNamespace(after=None, before=None, response=None)
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
        return fault.response(method, path, value) if fault.response else value
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


def test_interactive_session_choice_only_observes_exact_authorized_session(work, monkeypatch):
    from okto_nexus.adapters.inbound.cli import work as cli
    t = work
    operation = t.flow.submit('Synthetic retained conversation')
    complete(t, operation)
    rows = t.flow.sessions()['sessions']
    chosen = operation['scope']['session_id']
    position = next(i for i, row in enumerate(rows, 1) if row['scope']['session_id'] == chosen)
    before = deepcopy(t.flow.document), deepcopy(t.native.native.sent), t.native.opens
    t.calls.clear()
    values = iter([str(position), '/status', '/quit'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(values))
    assert cli.chat(t.flow) == 0
    assert (t.flow.document, t.native.native.sent, t.native.opens) == before
    assert t.calls and all(method == 'GET' for method, _ in t.calls)
    assert any('/runtime/sessions/' + chosen + '?' in path for _, path in t.calls)


def test_interactive_unknown_admission_recovers_original_before_session_choice(work, monkeypatch):
    from okto_nexus.adapters.inbound.cli import work as cli
    t = work
    t.fault.after = '/runtime/operations'
    with pytest.raises(ConnectionError):
        t.flow.submit('Synthetic original intent', client_intent_id='recover-original')
    wait_receipt(t.setup, {'operation_id': t.flow.document['work']['submission']['operation_id']})
    receipt = t.flow.api('GET', '/runtime/intents/recover-original')
    wait_receipt(t.setup, {'operation_id': receipt['initial_turn_operation_id']})
    before = deepcopy(t.native.native.sent), t.native.opens
    t.calls.clear()
    values = iter(['o', 'r', '1', '/quit'])
    monkeypatch.setattr('builtins.input', lambda prompt: next(values))
    assert cli.chat(t.flow) == 0
    assert t.flow.document['work']['client_intent_id'] == 'recover-original'
    assert t.flow.document['work']['state'] == 'admitted'
    assert (t.native.native.sent, t.native.opens) == before
    assert all(method == 'GET' for method, _ in t.calls)


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


def test_lost_initial_turn_lookup_keeps_the_confirmed_admission_pending(work):
    t = work
    intent = 'initial-turn-lookup-cut'
    path = '/runtime/intents/' + intent
    t.fault.before = path
    with pytest.raises(ConnectionError, match='Injected lost request') as lost:
        t.flow.submit('Recover this initial turn', client_intent_id=intent)
    assert lost.value.possible_effect is True
    checkpoint = deepcopy(t.saved[-1])
    assert checkpoint['work']['state'] == 'submit_submitted'
    assert checkpoint['work']['admission_confirmed'] is True
    assert 'initial_turn_operation_id' not in checkpoint['work']
    restarted = TerminalWork(t.call, t.save, t.connection, checkpoint)

    def missing_admission(_method, url, result):
        if url.endswith(path):
            result['operation'] = None
        return result

    t.fault.response = missing_admission
    t.calls.clear()
    with pytest.raises(ConnectionError) as missing:
        restarted.resume()
    assert missing.value.code == 'WORK_CORRELATION_UNAVAILABLE' and missing.value.possible_effect is True
    assert restarted.document == t.saved[-1] == checkpoint
    assert all(method == 'GET' for method, _ in t.calls)

    def missing_receipt(_method, url, result):
        if url.endswith(path):
            raise ConnectionError('NOT_FOUND', 'Injected missing receipt')
        return result

    t.fault.response = missing_receipt
    t.calls.clear()
    with pytest.raises(ConnectionError) as missing:
        restarted.submit('Recover this initial turn', client_intent_id=intent)
    assert missing.value.code == 'WORK_CORRELATION_UNAVAILABLE' and missing.value.possible_effect is True
    assert restarted.document == t.saved[-1] == checkpoint
    assert all(method == 'GET' for method, _ in t.calls)

    t.fault.response = None
    t.calls.clear()
    recovered = restarted.resume()
    assert restarted.document['work']['state'] == 'admitted'
    assert restarted.document['work']['initial_turn_operation_id'] == recovered['submission_turn_operation_id']
    complete(t, recovered)
    assert all(method == 'GET' for method, _ in t.calls)
    assert t.native.opens == 1 and [verb for verb, _ in t.native.native.sent] == ['send_turn']


def test_confirmed_initial_turn_cannot_switch_to_another_turn_in_the_same_session(work):
    t = work
    initial = t.flow.submit('First request', client_intent_id='first-turn-anchor')
    complete(t, initial)
    fresh = TerminalWork(t.call, t.save, t.connection)
    other = fresh.submit('Second request in the same session', client_intent_id='second-turn-anchor')
    complete(t, other)
    assert other['scope']['session_id'] == initial['scope']['session_id']
    assert other['submission_turn_operation_id'] != initial['submission_turn_operation_id']
    checkpoint = deepcopy(t.flow.document)

    def substitute(_method, path, value):
        if path.endswith('/runtime/intents/first-turn-anchor'):
            value['initial_turn_operation_id'] = other['submission_turn_operation_id']
        return value

    t.fault.response = substitute
    for read in (t.flow.resume, t.flow.observe):
        t.calls.clear()
        with pytest.raises(ConnectionError) as refused:
            read()
        assert refused.value.code == 'WORK_RECEIPT_MISMATCH' and refused.value.possible_effect is True
        assert t.flow.document == checkpoint
        assert all(method == 'GET' and not path.endswith(other['submission_turn_operation_id']) for method, path in t.calls)
    assert t.native.opens == 1 and [verb for verb, _ in t.native.native.sent] == ['send_turn', 'send_turn']


@pytest.mark.parametrize('stage', ['submit', 'resume', 'observe'])
def test_work_refuses_a_resolution_for_a_sibling_session(work, stage):
    t = work
    selected = test_embedded_dispatch.admit(t.setup, t.binding, 'prepare-original', 'runtime.start', new_session=True)
    wait_receipt(t.setup, selected)
    selected_peer = t.native.native
    sibling = test_embedded_dispatch.admit(t.setup, t.binding, 'prepare-sibling', 'runtime.start', new_session=True)
    wait_receipt(t.setup, sibling)
    sibling_peer = t.native.native
    selected_id, sibling_id = (item['scope']['session_id'] for item in (selected, sibling))
    assert selected_id != sibling_id
    options = {'session_id': selected_id, 'client_intent_id': 'exact-session-work'}
    receipt_path = '/runtime/intents/' + options['client_intent_id']

    if stage != 'submit':
        t.fault.after = '/runtime/intents:resolve'
        with pytest.raises(ConnectionError, match='Injected lost response'):
            t.flow.submit('Continue only the original', **options)

    def substitute(_method, path, value):
        if stage == 'submit' and path.endswith('/runtime/intents:resolve'):
            resolution = value
        elif stage != 'submit' and path.endswith(receipt_path):
            resolution = value['resolution']
        else:
            return value
        resolution['session_id'] = resolution['scope']['session_id'] = sibling_id
        resolution['semantic_intent']['session_id'] = sibling_id
        return value

    t.fault.response = substitute
    t.calls.clear()
    saved = len(t.saved)
    with pytest.raises(ConnectionError) as refused:
        if stage == 'submit':
            t.flow.submit('Continue only the original', **options)
        else:
            getattr(t.flow, stage)()
    assert refused.value.code == 'WORK_RECEIPT_MISMATCH'
    assert t.flow.document['work']['state'] == 'resolve_submitted'
    assert t.flow.document['work']['request_context']['session_id'] == selected_id
    assert len(t.saved) == saved + (stage == 'submit')
    assert not any(method == 'POST' and path.endswith('/runtime/operations') for method, path in t.calls)
    assert t.native.opens == 2 and selected_peer is not sibling_peer
    assert not selected_peer.sent and not sibling_peer.sent


@pytest.mark.parametrize('changed', ['operation_id', 'intent_hash'])
def test_resume_keeps_the_last_confirmed_receipt_when_the_resolution_changes(work, changed):
    t = work
    operation = t.flow.submit('Keep the original receipt', client_intent_id='original-receipt')
    complete(t, operation)
    original = deepcopy(t.flow.document)

    def substitute(_method, path, value):
        if path.endswith('/runtime/intents/original-receipt'):
            value['resolution'][changed] = 'different'
        return value

    t.fault.response = substitute
    t.calls.clear()
    with pytest.raises(ConnectionError) as refused:
        t.flow.resume()
    assert refused.value.code == 'WORK_RECEIPT_MISMATCH'
    assert t.flow.document == t.saved[-1] == original
    assert all(method == 'GET' for method, _ in t.calls)


@pytest.fixture
def terminal_event_page(monkeypatch):
    session_scope = dict(server_id='server', executor_id='executor', binding_id='binding', agent_id='subject',
                         workspace_id='workspace', workspace_binding_id='workspace-binding',
                         session_id='selected', session_owner_generation=3)
    epoch = 'reviewed-epoch'
    event_scope = {key: session_scope[key] for key in ('server_id', 'executor_id', 'session_id')}
    page = dict(scope=dict(session_scope), stream_epoch=epoch,
                events=[dict(event_scope, stream_epoch=epoch, sequence=sequence) for sequence in (12, 13)],
                count=2, next_after_sequence=13, committed_contiguous=16, gap_pending=False, has_more=True)

    def call(method, path, body=None):
        assert method == 'GET' and body is None
        assert path.endswith('/runtime/sessions/selected/events?executor_id=executor&after_sequence=11'
                             '&limit=200&stream_epoch=reviewed-epoch')
        return page

    flow = TerminalWork(call, lambda _document: pytest.fail('Observation changed the checkpoint'), {})
    monkeypatch.setattr(flow, 'binding', lambda: session_scope)
    monkeypatch.setattr(flow, 'session', lambda _binding, session_id:
                        dict(scope=dict(session_scope, session_id=session_id), lifecycle_state='READY'))
    monkeypatch.setattr(flow, 'pending', lambda _binding, _session_id: dict(items=[], has_more=False))
    return flow, page


@pytest.mark.parametrize(('target', 'field', 'value', 'code'), [
    ('scope', 'workspace_binding_id', 'other-binding', 'WORK_SCOPE_CHANGED'),
    ('scope', 'session_id', 'sibling', 'WORK_EVENT_PAGE_MISMATCH'),
    ('scope', 'session_owner_generation', 4, 'WORK_EVENT_PAGE_MISMATCH'),
    ('page', 'stream_epoch', 'old-epoch', 'WORK_EVENT_PAGE_MISMATCH'),
    ('page', 'next_after_sequence', 15, 'WORK_EVENT_PAGE_MISMATCH'),
    ('event', 'session_id', 'sibling', 'WORK_EVENT_PAGE_MISMATCH'),
    ('event', 'stream_epoch', 'old-epoch', 'WORK_EVENT_PAGE_MISMATCH'),
    ('event', 'sequence', 15, 'WORK_EVENT_PAGE_MISMATCH'),
])
def test_terminal_events_refuse_a_mismatched_page(terminal_event_page, target, field, value, code):
    flow, page = terminal_event_page
    {'page': page, 'scope': page['scope'], 'event': page['events'][-1]}[target][field] = value
    with pytest.raises(ConnectionError) as refused:
        flow.observe(session_id='selected', after_sequence=11, stream_epoch='reviewed-epoch')
    assert refused.value.code == code


def test_terminal_event_continuation_names_the_session_epoch_and_sequence(terminal_event_page, capsys):
    from okto_nexus.adapters.inbound.cli.work import display

    flow, page = terminal_event_page
    result = flow.observe(session_id='selected', after_sequence=11, stream_epoch='reviewed-epoch')
    assert result['events'] == page
    display(result)
    output = capsys.readouterr().out
    assert '--session-id for selected' in output
    assert '--stream-epoch for reviewed-epoch' in output
    assert '--after-sequence 13' in output


@pytest.fixture
def terminal_decision_receipt(terminal_event_page, monkeypatch):
    flow, page = terminal_event_page
    key = dict(page['scope'], canonical_request_id='approval-id', kind='native_approval')
    proposal = dict(approval_key=key, request_hash='request-hash', recipient_agent_id='operator')
    detail = dict(request_payload={'kwargs': proposal}, executed_result={'decision_id': 'decision-id'})
    receipt = dict(decision_id='decision-id', approval_key=key, request_hash=proposal['request_hash'],
                   native_stage='REFUSED_BEFORE_EFFECT', native_operation_id='native-operation')
    operation = dict(operation_id='native-operation', scope=dict(page['scope']), action='approval.decide',
                     error={'message': 'Canonical refusal'})
    event_read = flow.call

    def call(method, path, body=None):
        assert method == 'GET' and body is None
        if path.endswith('/approvals/approval-id'):
            return {'data': detail}
        if path.endswith('/connections/me'):
            return {'agent_id': 'operator'}
        if path.endswith('/runtime/approval-decisions/decision-id'):
            return receipt
        if path.endswith('/runtime/operations/native-operation'):
            return operation
        return event_read(method, path, body)

    flow.document['decision'] = deepcopy(proposal)
    flow.document['session_id'] = key['session_id']
    monkeypatch.setattr(flow, 'call', call)
    return flow, receipt, operation


@pytest.mark.parametrize(('surface', 'target', 'field', 'value', 'code'), [
    ('answer', 'receipt', 'decision_id', 'other-decision', 'DECISION_RECEIPT_MISMATCH'),
    ('observe', 'receipt', 'decision_id', 'other-decision', 'DECISION_RECEIPT_MISMATCH'),
    ('observe', 'receipt', 'request_hash', 'other-request-hash', 'DECISION_RECEIPT_MISMATCH'),
    ('observe', 'scope', 'session_id', 'sibling', 'DECISION_RECEIPT_MISMATCH'),
    ('observe', 'scope', 'session_owner_generation', 4, 'DECISION_RECEIPT_MISMATCH'),
    ('observe', 'scope', 'workspace_binding_id', 'other-binding', 'WORK_SCOPE_CHANGED'),
    ('observe', 'operation', 'action', 'turn.submit', 'DECISION_RECEIPT_MISMATCH'),
])
def test_terminal_decision_checks_the_exact_recorded_receipt(
        terminal_decision_receipt, surface, target, field, value, code):
    flow, receipt, operation = terminal_decision_receipt
    {'receipt': receipt, 'operation': operation, 'scope': operation['scope']}[target][field] = value
    checkpoint = deepcopy(flow.document)
    with pytest.raises(ConnectionError) as refused:
        if surface == 'answer':
            flow.decide('approval-id', 'approve')
        else:
            flow.observe(session_id='selected', after_sequence=11, stream_epoch='reviewed-epoch')
    assert refused.value.code == code
    assert flow.document == checkpoint


@pytest.fixture
def terminal_watch(monkeypatch):
    from okto_nexus.adapters.inbound.cli import work as cli

    reads, delays = [], []
    monkeypatch.setattr(cli, 'time', SimpleNamespace(monotonic=lambda: 0, sleep=delays.append))

    def page(state, *, cursor, sequences=(), has_more=False, session_id='chosen', requests=()):
        scope = dict(server_id='server', executor_id='executor', binding_id='binding',
                     workspace_binding_id='workspace-binding', session_id=session_id, session_owner_generation=3)
        events = dict(scope=scope, stream_epoch='exact-epoch', events=[dict(sequence=seq) for seq in sequences],
                      count=len(sequences), next_after_sequence=cursor, committed_contiguous=2,
                      has_more=has_more, gap_pending=False)
        return dict(state=state, events=events, requests=dict(items=list(requests)))

    def watch(*observations, **options):
        stream = iter(observations)

        def observe(**query):
            reads.append(query)
            return next(stream)

        return cli.watch(SimpleNamespace(observe=observe), as_json=True, **options)

    return SimpleNamespace(cli=cli, page=page, watch=watch, reads=reads, delays=delays)


def test_work_watch_drains_committed_pages_after_completion(terminal_watch, capsys):
    t = terminal_watch
    assert t.watch(t.page('completed', cursor=1, sequences=[1], has_more=True),
                   t.page('completed', cursor=2, sequences=[2])) == 0
    assert [(read['after_sequence'], read['stream_epoch']) for read in t.reads] == [(0, None), (1, 'exact-epoch')]
    pages = [json.loads(line)['events'] for line in capsys.readouterr().out.splitlines()]
    assert [event['sequence'] for page in pages for event in page['events']] == [1, 2]
    assert t.delays == []


def test_work_watch_keeps_the_epoch_and_suppresses_an_empty_poll(terminal_watch, capsys):
    t = terminal_watch
    assert t.watch(t.page('observing', cursor=1, sequences=[1]), t.page('observing', cursor=1),
                   t.page('completed', cursor=2, sequences=[2])) == 0
    assert [(read['after_sequence'], read['stream_epoch']) for read in t.reads] == [
        (0, None), (1, 'exact-epoch'), (1, 'exact-epoch')]
    assert len(capsys.readouterr().out.splitlines()) == 2
    assert len(t.delays) == 2


def test_work_watch_refuses_a_changed_session(terminal_watch, capsys):
    t = terminal_watch
    with pytest.raises(ConnectionError, match='The observed session changed'):
        t.watch(t.page('observing', cursor=1, sequences=[1]),
                t.page('completed', cursor=2, sequences=[2], session_id='sibling'))
    assert 'sibling' not in capsys.readouterr().out


def test_work_watch_addresses_pending_question_in_the_observed_session(terminal_watch, monkeypatch):
    t = terminal_watch
    answers = []

    def decide(_flow, approval_id, *, session_id):
        answers.append((approval_id, session_id, len(t.reads)))
        return True

    monkeypatch.setattr(t.cli, 'decide_interactively', decide)
    assert t.watch(t.page('needs_input', cursor=1, sequences=[1], has_more=True,
                          requests=[dict(approval_id='question')]),
                   t.page('completed', cursor=2, sequences=[2]), interactive=True) == 0
    assert answers == [('question', 'chosen', 1)]


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


def prepare_terminal_native_request(t, kind, enabled):
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
    return turn, detail, proposal, replies


@pytest.mark.parametrize('kind,enabled', [('input', True), ('approval', True), ('approval', False)])
def test_native_decision_response_loss_recovers_canonical_result_and_keeps_answers_out_of_profile(work, kind, enabled):
    t = work
    turn, detail, proposal, replies = prepare_terminal_native_request(t, kind, enabled)
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


def test_dashboard_and_terminal_share_one_native_question_decision(work):
    t = work
    turn, detail, proposal, replies = prepare_terminal_native_request(t, 'input', True)
    approval_id = detail['approval_id']
    decision_url = '/api/v1/runtime-management/runtime/approval-decisions'
    ui_intent = {key: proposal[key] for key in ('approval_key', 'expected_revision', 'request_hash', 'cas_token')}
    ui_intent.update(client_intent_id='dashboard-question-decision', decision='deny')
    answer = {'answers': {'question': {'answers': ['Terminal fixture answer']}}}
    gate = Barrier(2, timeout=10)

    def terminal_http(method, path, body=None):
        if method == 'POST' and path.endswith('/runtime/approval-decisions'):
            gate.wait()
        return t.call(method, path, body)

    def terminal_decision():
        try:
            return terminal.decide(approval_id, 'approve', response=answer, reviewed_revision=document_revision(proposal))
        except ConnectionError as error:
            assert error.code == 'CONFLICT' and 'already has a decision' in str(error)
            return None

    terminal = TerminalWork(terminal_http, t.save, t.connection, t.flow.document)
    with ThreadPoolExecutor(max_workers=1) as attempts:
        from_terminal = attempts.submit(terminal_decision)
        gate.wait()
        from_dashboard = t.setup[2].post(decision_url, headers={'X-Nexus-UI': '1'}, json=ui_intent)
        terminal_result = from_terminal.result(timeout=15)
    if terminal_result is None:
        assert from_dashboard.status_code == 202, from_dashboard.text
        decision = from_dashboard.json()
        expected_choice = 'DENIED'
    else:
        assert from_dashboard.status_code == 409 and 'already has a decision' in from_dashboard.text
        decision = terminal_result
        expected_choice = 'CONFIRMED'
    assert decision['canonical_state'] == expected_choice
    assert decision['approval_key'] == proposal['approval_key']

    resolved = t.call('GET', f'/api/v1/approvals/{approval_id}')['data']
    assert resolved['executed_result']['decision_id'] == decision['decision_id']
    replay = terminal.decide(approval_id, 'approve')
    assert replay['decision_id'] == decision['decision_id']
    assert replay['native_operation_id'] == decision['native_operation_id']
    assert sum(method == 'POST' and path.endswith('/runtime/approval-decisions') for method, path in t.calls) == 1
    deadline = time.monotonic() + 15
    while True:
        recorded = terminal.api('GET', '/runtime/approval-decisions/' + decision['decision_id'])
        if recorded['native_stage'] == 'SUBMITTED':
            break
        assert time.monotonic() < deadline, recorded
        time.sleep(.03)
    assert replies == ([('accept', answer)] if terminal_result is not None else [('cancel', None)])
    with t.deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_decisions').fetchone()[0] == 1
        assert uow.connection.execute(
            "SELECT COUNT(*) FROM execution_operations WHERE action='input.provide'",
        ).fetchone()[0] == 1
    complete(t, turn)


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


@pytest.mark.parametrize(('fault', 'path', 'admitted', 'legacy'), [
    ('after', '/runtime/intents:resolve', False, False),
    ('before', '/runtime/operations', False, False),
    ('after', '/runtime/operations', True, False),
    ('after', '/runtime/intents:resolve', False, True),
])
def test_recover_reused_opening_admits_only_the_original_pending_turn(work, fault, path, admitted, legacy):
    from okto_nexus.application.terminal_work import SUBMISSION

    t = work
    opening = test_embedded_dispatch.admit(t.setup, t.binding, 'existing-opening', 'runtime.start')
    wait_receipt(t.setup, opening)

    setattr(t.fault, fault, path)
    with pytest.raises(ConnectionError, match='Injected'):
        t.flow.submit('One request for the existing session', client_intent_id='reuse-request')
    reopened = TerminalWork(t.call, t.save, t.connection, t.saved[-1])
    receipt = reopened.api('GET', '/runtime/intents/reuse-request')
    assert receipt['resolution']['reuse'] is True
    assert (receipt['operation'] is not None) is admitted
    if legacy:
        # Older CLI builds could record "admitted" from the reused opening
        # before this request's admission or initial turn was confirmed.
        reopened.document['work'].update(state='admitted',
            submission={key: receipt['resolution'][key] for key in SUBMISSION})
        reopened.document['session_id'] = opening['session_id']
    if not admitted:
        assert reopened.observe()['state'] == 'submission_unconfirmed'
        assert not t.native.native.sent

    t.calls.clear()
    recovered = reopened.resume()
    assert recovered['operation_id'] == opening['operation_id']
    assert recovered['scope']['session_id'] == opening['session_id']
    assert recovered['submission_turn_operation_id'] == receipt['initial_turn_operation_id']
    assert sum(method == 'POST' and url.endswith('/runtime/operations')
               for method, url in t.calls) == (0 if admitted else 1)

    complete(t, recovered)
    t.calls.clear()
    assert reopened.resume()['submission_turn_operation_id'] == recovered['submission_turn_operation_id']
    assert reopened.observe()['state'] == 'completed'
    assert all(method == 'GET' for method, _ in t.calls)
    assert t.native.opens == 1
    assert [verb for verb, _ in t.native.native.sent] == ['send_turn']


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
