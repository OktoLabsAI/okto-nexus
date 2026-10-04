"""Sender affinity is durable; parallel conversations retain reply provenance."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import time

import pytest
from nexus_connector_core import RuntimeEvent

from test_embedded_dispatch import local_setup, connected_local, qualified_contract, admit, wait_receipt
from test_vertical_inventory import _Native
from okto_nexus.domain.base import iso_plus
from okto_nexus.application.execution_domain_delivery import select_delivery_session
from okto_nexus.errors import OktoNexusError


def configure(setup, binding, mode):
    deps, _, client, headers, *_ = setup
    path = f"/api/v1/harness/endpoints/{binding['endpoint_id']}/conversation-policy"
    policy = client.get(path, headers=headers['operator']).json()['data']
    result = client.put(path, headers=headers['operator'], json=dict(
        expected_revision=policy['revision'], enabled=True, session_policy=mode))
    assert result.status_code == 200, result.text
    grant = client.post('/api/v1/harness/grants', headers=headers['operator'], json=dict(
        actor_agent_id='subject', endpoint_id=binding['endpoint_id'], actions=['open', 'send', 'interrupt', 'close'],
        max_executions=30, expires_at=iso_plus(deps.clock.now_iso(), 600)))
    assert grant.status_code == 200, grant.text
    return path, result.json()['data']


class Peers:
    def __init__(self):
        self.sessions = {}

    async def open(self, prepared, session_id, context, *, stream_epoch):
        peer = _Native()
        self.sessions[session_id] = peer
        return peer


def turn_for(setup, message_id):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        return dict(uow.connection.execute(
            "SELECT o.operation_id,o.session_id FROM execution_operations o "
            "JOIN execution_domain_deliveries m USING(server_id,executor_id,operation_id) "
            "JOIN delivery_outbox d ON d.operation_id=m.domain_operation_id "
            "WHERE d.message_id=? AND o.action='turn.submit'", (message_id,)).fetchone())


def complete(setup, peers, turn, text):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        stream = dict(uow.connection.execute('SELECT * FROM execution_local_streams WHERE session_id=?',
                                             (turn['session_id'],)).fetchone())
    setup[2].portal.call(peers.sessions[turn['session_id']].queue.put, RuntimeEvent(
        stream['server_id'], stream['executor_id'], stream['session_id'], stream['stream_epoch'], 0,
        'turn_state', 'fixture.result', dict(delivery_phase='terminal', delivery_outcome='success', output_text=text),
        operation_id=turn['operation_id']))
    wait_receipt(setup, turn, stages=('SUCCEEDED',))


def sender(setup, monkeypatch):
    deps, app, client, headers, *_ = setup
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    client.headers['host'] = '127.0.0.1:8000'
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('INSERT INTO agents(agent_id,created_at) VALUES (?,?)', ('sender-b', deps.clock.now_iso()))
        token = app.state.auth.issue_key(uow, agent_id='sender-b')
        workspace = uow.connection.execute('SELECT workspace_id FROM workspaces').fetchone()[0]
    tokens = dict(operator=headers['operator']['Authorization'].removeprefix('Bearer '), **{'sender-b': token})
    def send(actor, text='hello', **changes):
        response = tool(client, tokens[actor], 'message_create', dict(from_agent_id=actor, workspace_id=workspace,
            target=dict(strategy='direct', agent_id='subject'), subject='Sender isolation', body=text) | changes)
        assert response['ok'], response
        return response['data']['message_id']
    return send


@pytest.mark.parametrize('local_setup', ['codex_app_server', 'claude_stream', 'pi_rpc'], indirect=True)
@pytest.mark.parametrize('mode', ['per_sender_session', 'per_sender'])
def test_same_agent_source_sessions_are_isolated_only_in_new_mode(connected_local, monkeypatch, mode):
    setup, binding, _ = connected_local
    peers = Peers()
    setup[1].state.embedded_dispatch_owner.native_factory = peers
    configure(setup, binding, mode)
    send = sender(setup, monkeypatch)
    from test_pr34_remediation import tool
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        workspace = uow.connection.execute('SELECT workspace_id FROM workspaces').fetchone()[0]
    token = setup[3]['operator']['Authorization'].removeprefix('Bearer ')
    def open_source():
        result = tool(setup[2], token, 'session_open', dict(agent_id='operator', workspace_id=workspace))
        assert result['ok'], result
        return {k: result['data'][k] for k in ('session_id', 'session_secret')}
    a, b = open_source(), open_source()
    def from_session(source):
        return send('operator', from_session_id=source['session_id'], session_secret=source['session_secret'])
    first = turn_for(setup, from_session(a))
    wait_receipt(setup, first)
    second = turn_for(setup, from_session(b))
    assert (first['session_id'] != second['session_id']) == (mode == 'per_sender_session')
    if mode == 'per_sender_session':
        # B must dispatch while A is still running, not just get a different ID.
        wait_receipt(setup, second)
        complete(setup, peers, second, 'B')
    complete(setup, peers, first, 'A')
    if mode == 'per_sender':
        wait_receipt(setup, second)
        complete(setup, peers, second, 'B')
    again = turn_for(setup, from_session(a))
    assert again['session_id'] == first['session_id']
    wait_receipt(setup, again)
    complete(setup, peers, again, 'A again')
    sessionless = turn_for(setup, send('operator'))
    assert (sessionless['session_id'] not in {first['session_id'], second['session_id']}) == (mode == 'per_sender_session')
    wait_receipt(setup, sessionless)
    complete(setup, peers, sessionless, 'No source')
    repeated = turn_for(setup, send('operator', from_session_id='unverified-attribution'))
    assert repeated['session_id'] == sessionless['session_id']
    wait_receipt(setup, repeated)
    complete(setup, peers, repeated, 'No verified source')
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        from okto_nexus.application.message_session_origin import for_message, runtime_key
        for row in uow.connection.execute('SELECT r.publication_message_id,e.server_id,e.executor_id,e.session_id '
                'FROM runtime_results r JOIN execution_results e ON e.server_id=r.canonical_server_id '
                'AND e.executor_id=r.canonical_executor_id AND e.operation_id=r.canonical_operation_id '
                'WHERE r.publication_message_id IS NOT NULL'):
            assert for_message(uow.connection, row['publication_message_id']) == runtime_key(row)
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()
    for index, sid in enumerate({first['session_id'], second['session_id'], sessionless['session_id']}):
        wait_receipt(setup, admit(setup, binding, f'close-origin-{index}', 'runtime.close', session_id=sid), stages=('SUCCEEDED',))


@pytest.mark.parametrize('local_setup', ['codex_app_server', 'claude_stream', 'pi_rpc'], indirect=True)
def test_parallel_senders_separate_sessions_reuse_and_correct_replies(connected_local, monkeypatch):
    setup, binding, _ = connected_local
    deps, app, client, headers, *_ = setup
    peers = Peers()
    app.state.embedded_dispatch_owner.native_factory = peers
    path, policy = configure(setup, binding, 'per_sender')
    send = sender(setup, monkeypatch)
    barrier = threading.Barrier(2)
    def parallel(actor):
        barrier.wait(timeout=5)
        return send(actor, 'private for ' + actor)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(parallel, ['operator', 'sender-b']))
    first, second = [turn_for(setup, mid) for mid in results]
    assert first['session_id'] != second['session_id']
    for turn in (first, second):
        try:
            wait_receipt(setup, turn)
        except AssertionError:
            with deps.connection_factory.unit_of_work(write=False) as uow:
                operations = [dict(r) for r in uow.connection.execute(
                    'SELECT operation_id FROM execution_operations')]
            pytest.fail(json.dumps([client.get('/v1/runtime/operations/' + op['operation_id'],
                headers=headers['subject']).json() for op in operations], indent=2))
    assert len(peers.sessions) == 2  # both dispatched before either completed
    follow_up = turn_for(setup, send('operator', 'continue A'))
    assert follow_up['session_id'] == first['session_id']
    queued = client.get('/v1/runtime/operations/' + follow_up['operation_id'], headers=headers['subject']).json()
    assert queued['executor_stage'] is None  # preserve order within A's conversation
    refused = client.put(path, headers=headers['operator'], json=dict(
        expected_revision=policy['revision'], enabled=True, session_policy='shared'))
    assert refused.status_code == 409, refused.text
    # Reversed completion order must not swap recipients.
    complete(setup, peers, second, 'answer B')
    complete(setup, peers, first, 'answer A')
    deadline = time.monotonic() + 10
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            replies = [tuple(r) for r in uow.connection.execute(
                "SELECT m.parent_message_id,m.body,d.recipient_agent_id FROM runtime_results r "
                "JOIN messages m ON m.message_id=r.publication_message_id "
                "JOIN message_deliveries d ON d.message_id=m.message_id WHERE r.publication_state='PUBLISHED'")]
        if len(replies) == 2:
            break
        assert time.monotonic() < deadline, replies
        time.sleep(.02)
    assert set(replies) == {(results[0], 'answer A', 'operator'), (results[1], 'answer B', 'sender-b')}
    wait_receipt(setup, follow_up)
    complete(setup, peers, follow_up, 'continued A')
    assert len(peers.sessions) == 2
    # A fresh database connection resolves durable affinity, independent of caches.
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert select_delivery_session(uow, binding['endpoint_id'], sender_agent_id='sender-b')[1] == second['session_id']
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()
    for index, turn in enumerate((first, second)):
        wait_receipt(setup, admit(setup, binding, f'close-{index}', 'runtime.close', session_id=turn['session_id']), stages=('SUCCEEDED',))
    reopened = turn_for(setup, send('operator', 'new A after close'))
    assert reopened['session_id'] not in (first['session_id'], second['session_id'])
    wait_receipt(setup, reopened)
    complete(setup, peers, reopened, 'new A')
    wait_receipt(setup, admit(setup, binding, 'close-reopened', 'runtime.close', session_id=reopened['session_id']), stages=('SUCCEEDED',))


def test_shared_default_reuses_session_across_senders(connected_local, monkeypatch):
    setup, binding, _ = connected_local
    peers = Peers()
    setup[1].state.embedded_dispatch_owner.native_factory = peers
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT session_policy FROM agent_endpoints').fetchone()[0] == 'shared'
    configure(setup, binding, 'shared')
    send = sender(setup, monkeypatch)
    first = turn_for(setup, send('operator'))
    wait_receipt(setup, first)
    complete(setup, peers, first, 'A')
    second = turn_for(setup, send('sender-b'))
    assert second['session_id'] == first['session_id']
    wait_receipt(setup, second)
    complete(setup, peers, second, 'B')
    wait_receipt(setup, admit(setup, binding, 'shared-close', 'runtime.close', session_id=first['session_id']), stages=('SUCCEEDED',))


def test_invalid_session_policy_and_missing_sender_fail_closed(connected_local):
    setup, binding, _ = connected_local
    path, policy = configure(setup, binding, 'per_sender')
    for mode in ('unknown', None, {}, True):
        result = setup[2].put(path, headers=setup[3]['operator'], json=dict(
            expected_revision=policy['revision'], enabled=True, session_policy=mode))
        assert result.status_code == 422, result.text
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        with pytest.raises(OktoNexusError, match='Sender identity'):
            select_delivery_session(uow, binding['endpoint_id'])
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_sessions').fetchone()[0] == 0


@pytest.mark.parametrize('mode', ['per_sender', 'per_sender_session'])
def test_opening_sender_is_not_duplicated_and_manual_session_is_not_adopted(connected_local, monkeypatch, mode):
    setup, binding, _ = connected_local
    configure(setup, binding, mode)
    manual = admit(setup, binding, 'manual', 'runtime.start', new_session=True)
    wait_receipt(setup, manual)
    setup[2].portal.call(setup[1].state.embedded_dispatch_owner.pump.stop)
    send = sender(setup, monkeypatch)
    turn = turn_for(setup, send('operator'))
    assert turn['session_id'] != manual['session_id']
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        with pytest.raises(OktoNexusError, match='reconciliation'):
            select_delivery_session(uow, binding['endpoint_id'], sender_agent_id='operator')
        assert select_delivery_session(uow, binding['endpoint_id'], sender_agent_id='sender-b')[1] is None
        assert uow.connection.execute('SELECT COUNT(*) FROM execution_sender_sessions').fetchone()[0] == 1
