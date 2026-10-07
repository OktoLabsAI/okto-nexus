"""Result relays keep their original actor and durable budgets through Core."""
import json
import time
from pathlib import Path

import pytest
from nexus_connector_core import RuntimeEvent

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, connect_local
from test_canonical_delivery import connected_local
from test_agent_recovery_isolation import create_agent
from test_vertical_inventory import _Native


@pytest.fixture
def relay_pair(connected_local):
    setup, first, _ = connected_local
    deps, app, client, headers, body, candidate, root = setup
    second_setup = create_agent(setup, 'caller')
    headers['caller'] = second_setup[3]['subject']
    _, second, _ = connect_local(second_setup, agent_id='caller')
    for binding in (first, second):
        # Current canonical resources, no historical native endpoint or opener.
        with deps.connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE agent_endpoints SET consumption='exclusive',response_policy='conversation',public_config=? WHERE endpoint_id=?",
                (json.dumps(dict(relay_results=True)), binding['endpoint_id']))
    peers = []
    class Factory:
        outcome = 'success'
        async def open(self, prepared, session_id, context, *, stream_epoch):
            factory = self
            class Peer(_Native):
                async def send(self, verb, payload, operation_id, **kwargs):
                    await super().send(verb, payload, operation_id, **kwargs)
                    if verb == 'send_turn':
                        await self.queue.put(RuntimeEvent(context.server_id, context.executor_id, session_id,
                            stream_epoch, 0, 'turn_state', 'fixture.relay-result',
                            dict(delivery_phase='terminal', delivery_outcome=factory.outcome,
                                 output_text='Bounded reply'), operation_id=operation_id))
            peer = Peer()
            peers.append(peer)
            return peer
    factory = Factory()
    app.state.embedded_dispatch_owner.native_factory = factory
    deps.config.max_relay_depth = 2
    deps.runtime_dispatcher.recovery_seconds = .2
    deps.runtime_dispatcher.wake()
    return setup, first, second, peers, factory


def send(setup, monkeypatch, *, target='subject'):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    setup[2].headers['host'] = '127.0.0.1:8000'
    return tool(setup[2], setup[3]['caller']['Authorization'].removeprefix('Bearer '), 'message_create',
        dict(project_root=str(setup[-1]), from_agent_id='caller', subject='Bounded relay',
             body='Start an authorized exchange', target=dict(strategy='direct', agent_id=target)))


def results(setup, count):
    deadline = time.monotonic() + 15
    while True:
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            rows = [dict(r) for r in uow.connection.execute('SELECT * FROM runtime_results ORDER BY captured_at,result_id')]
        if len(rows) == count and rows[-1]['relay_state'] == 'BLOCKED':
            return rows
        if time.monotonic() >= deadline:
            with setup[0].connection_factory.unit_of_work(write=False) as uow:
                diagnostic = {table: [dict(r) for r in uow.connection.execute('SELECT ' + columns + ' FROM ' + table)]
                    for table, columns in (
                        ('delivery_outbox', 'recipient_agent_id,status,reason,source_result_id'),
                        ('runtime_results', 'publication_state,relay_state,relay_reason,publication_reason'),
                        ('execution_operations', 'operation_id,action'),
                        ('execution_dispatch_outbox', 'operation_id,dispatch_state,last_error'))}
            pytest.fail(str(diagnostic))
        time.sleep(.02)


@pytest.mark.parametrize('limit', ['depth', 'executions'])
def test_relay_stops_at_persistent_budget_without_losing_output(relay_pair, monkeypatch, limit):
    setup, _, _, peers, _ = relay_pair
    deps = setup[0]
    if limit == 'executions':
        deps.config.max_relay_depth = 4
        deps.config.max_executions_per_root = 2
    expected = 2 if limit == 'executions' else 3
    sent = send(setup, monkeypatch)
    assert sent['ok'], sent
    rows = results(setup, expected)
    assert all(r['publication_state'] == 'PUBLISHED' and r['publication_message_id'] for r in rows)
    assert [r['relay_state'] for r in rows] == ['ENQUEUED'] * (expected - 1) + ['BLOCKED']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        operations = list(uow.connection.execute('SELECT * FROM delivery_outbox ORDER BY created_at,operation_id'))
        assert len(operations) == expected
        assert [r['recipient_agent_id'] for r in operations] == ['subject', 'caller', 'subject'][:expected]
        assert {r['actor_agent_id'] for r in operations} == {'caller'}
        assert len({r['root_operation_id'] for r in operations}) == 1
        root = uow.connection.execute('SELECT generated_messages,admitted_executions FROM runtime_causal_roots').fetchone()
        assert root[:] == (expected - 1, expected)
        assert uow.connection.execute('SELECT COUNT(*) FROM harness_sessions').fetchone()[0] == 0
        assert uow.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    assert sum(len(peer.sent) for peer in peers) == expected


@pytest.mark.parametrize('outcome', ['failed', 'interrupted'])
def test_unsuccessful_result_cannot_admit_a_relay(relay_pair, monkeypatch, outcome):
    setup, _, _, peers, factory = relay_pair
    factory.outcome = outcome
    assert send(setup, monkeypatch)['ok']
    row, = results(setup, 1)
    assert row['publication_state'] == 'PUBLISHED'
    assert row['delivery_outcome'] == outcome
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
    assert len(peers) == 1 and len(peers[0].sent) == 1


def test_self_relay_is_blocked_without_another_native_turn(relay_pair, monkeypatch):
    from test_canonical_result_publication import wait_result
    setup, _, _, peers, _ = relay_pair
    assert send(setup, monkeypatch, target='caller')['ok']
    # The canonical message boundary rejects generated self-addressed output
    # before relay admission, retaining the private captured native result.
    row = wait_result(setup, 'BLOCKED')
    assert row['publication_reason'] == 'PERMISSION_DENIED'
    assert row['relay_state'] == 'NOT_REQUESTED' and row['output_text'] == 'Bounded reply'
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
    assert sum(len(peer.sent) for peer in peers) == 1


def test_repeated_publication_does_not_charge_or_dispatch_again(relay_pair, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from okto_nexus.adapters.inbound.mcp.tools.messages import build_service
    setup, _, _, peers, _ = relay_pair
    setup[0].config.max_relay_depth = 1
    assert send(setup, monkeypatch)['ok']
    rows = results(setup, 2)
    messages = build_service(setup[0])
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        bound = messages._runtime_results.row(uow, rows[0]['result_id'])
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(lambda _: messages.create_message(
            **messages._runtime_results.arguments(bound), _runtime_result_id=bound['result_id']), range(8)))
    assert {r['message_id'] for r in replies} == {bound['publication_message_id']}
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 2
        assert uow.connection.execute('SELECT generated_messages,admitted_executions FROM runtime_causal_roots').fetchone()[:] == (1, 2)
    assert sum(len(peer.sent) for peer in peers) == 2


def test_source_revocation_after_publication_prevents_child_native_dispatch(relay_pair, monkeypatch):
    from okto_nexus.application.runtime_results import RuntimeResultService
    setup, first, _, peers, _ = relay_pair
    finish = RuntimeResultService.finish
    def revoke(uow, **kwargs):
        finish(uow, **kwargs)
        uow.connection.execute('UPDATE agent_endpoints SET enabled=0,revision=revision+1 WHERE endpoint_id=?', (first['endpoint_id'],))
    monkeypatch.setattr(RuntimeResultService, 'finish', staticmethod(revoke))
    assert send(setup, monkeypatch)['ok']
    deadline = time.monotonic() + 15
    while True:
        with setup[0].connection_factory.unit_of_work(write=False) as uow:
            child = uow.connection.execute('SELECT * FROM delivery_outbox WHERE source_result_id IS NOT NULL').fetchone()
            if child and child['status'] == 'REJECTED':
                assert uow.connection.execute('SELECT COUNT(*) FROM runtime_results').fetchone()[0] == 1
                break
        assert time.monotonic() < deadline, dict(child) if child else None
        time.sleep(.02)
    assert sum(len(peer.sent) for peer in peers) == 1


def test_interleaved_roots_share_sessions_without_sharing_budgets(relay_pair, monkeypatch):
    setup, _, _, peers, _ = relay_pair
    setup[0].config.max_relay_depth = 1
    entries = [send(setup, monkeypatch), send(setup, monkeypatch)]
    assert all(e['ok'] for e in entries), entries
    rows = results(setup, 4)
    assert sum(r['relay_state'] == 'BLOCKED' for r in rows) == 2
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        roots = uow.connection.execute('SELECT generated_messages,admitted_executions FROM runtime_causal_roots').fetchall()
        assert [tuple(r) for r in roots] == [(1, 2), (1, 2)]
        assert uow.connection.execute("SELECT COUNT(DISTINCT session_id) FROM execution_operations WHERE action='turn.submit'").fetchone()[0] == 2
        for entry in entries:
            parent = uow.connection.execute('SELECT * FROM delivery_outbox WHERE message_id=?', (entry['data']['message_id'],)).fetchone()
            child = uow.connection.execute('SELECT c.*, r.publication_message_id FROM delivery_outbox c JOIN runtime_results r ON r.result_id=c.source_result_id WHERE r.operation_id=?', (parent['operation_id'],)).fetchone()
            assert child['root_operation_id'] == parent['root_operation_id']
            assert child['message_id'] == child['publication_message_id']
            assert uow.connection.execute('SELECT parent_message_id FROM messages WHERE message_id=?', (child['message_id'],)).fetchone()[0] == entry['data']['message_id']
    assert sum(len(peer.sent) for peer in peers) == 4


@pytest.mark.parametrize('decision', ['approve', 'reject'])
def test_relay_waits_for_canonical_human_approval(relay_pair, monkeypatch, decision):
    from test_governance import _attach, _rule
    from test_canonical_result_publication import wait_result
    setup, _, _, peers, _ = relay_pair
    deps, _, client, headers, *_ = setup
    deps.config.feature_hitl = True
    deps.config.max_relay_depth = 1
    _attach(deps, 'subject', governance=[_rule('message_create', 'require_approval')])
    assert send(setup, monkeypatch)['ok']
    pending = wait_result(setup, 'PENDING_APPROVAL')
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
    response = client.post(f"/api/v1/approvals/{pending['publication_approval_id']}/decision",
        headers=headers['operator'], json={'decision': decision})
    assert response.status_code == 200, response.text
    if decision == 'approve':
        assert results(setup, 2)[0]['relay_state'] == 'ENQUEUED'
        assert sum(len(peer.sent) for peer in peers) == 2
    else:
        wait_result(setup, 'BLOCKED')
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 1
        assert sum(len(peer.sent) for peer in peers) == 1
