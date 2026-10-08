"""Logical delivery and Core admission share bounded transactional capacity."""
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_result_publication import current_turn
from test_canonical_handoff_regressions import runtime, call, grant, claim
from test_canonical_grant_regressions import mcp_helpers


def pause(setup, binding):
    opened = admit(setup, binding, 'backlog-open', 'runtime.start', new_session=True)
    wait_receipt(setup, opened)
    setup[2].portal.call(setup[1].state.embedded_dispatch_owner.pump.stop)
    setup[0].config.max_new_roots_per_agent_per_minute = 256
    enable(setup, binding)
    return opened


def counts(setup, expected):
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        for table in ('messages', 'message_deliveries', 'delivery_outbox'):
            assert uow.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] == expected
        assert uow.connection.execute("SELECT COUNT(*) FROM message_deliveries WHERE consumer_kind='push'").fetchone()[0] == expected


@pytest.mark.parametrize('legacy', [False, True])
def test_recipient_backlog_rolls_back_overflow_even_for_old_enqueue(connected_local, monkeypatch, legacy):
    setup, binding, native = connected_local
    pause(setup, binding)
    for _ in range(32):
        result = send(setup, monkeypatch)
        assert result['ok'], result
    if legacy:
        from test_runtime_capacity_writer_fence import legacy_enqueue
        from okto_nexus.adapters.outbound.sqlite.runtime_outbox_repo import SqliteRuntimeOutboxRepo
        monkeypatch.setattr(SqliteRuntimeOutboxRepo, 'enqueue', legacy_enqueue)
    overflow = send(setup, monkeypatch)
    assert not overflow['ok'], overflow
    if not legacy:
        assert overflow['error']['code'] == 'QUOTA_EXCEEDED', overflow
    counts(setup, 32)
    assert not native.native.sent
    if not legacy:
        from test_canonical_recovery import recover, snapshot
        released = recover(setup, snapshot(setup), 'cancel_pending')
        assert released.status_code == 200, released.text
        assert released.json()['data']['inbox_released']
        replacement = send(setup, monkeypatch)
        assert replacement['ok'], replacement
        from test_agent_recovery_isolation import create_agent
        create_agent(setup, 'passive')
        logical = send(setup, monkeypatch, target=dict(strategy='direct', agent_id='passive'))
        assert logical['ok'] and not logical['data'].get('runtime_operations'), logical


def test_concurrent_messages_compete_for_one_remaining_slot(connected_local, monkeypatch):
    setup, binding, native = connected_local
    pause(setup, binding)
    for _ in range(31):
        assert send(setup, monkeypatch)['ok']
    gate = threading.Barrier(2)
    def compete(_):
        gate.wait(5)
        return send(setup, monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(compete, range(2)))
    assert sum(r['ok'] for r in replies) == 1, replies
    assert next(r for r in replies if not r['ok'])['error']['code'] == 'QUOTA_EXCEEDED'
    counts(setup, 32)
    assert not native.native.sent


def test_full_backlog_rolls_back_managed_claim_and_grant(runtime, monkeypatch):
    setup, binding, native = runtime
    # Create the offer before enabling conversational notifications.
    offered = call(runtime, 'handoff_create', from_agent_id='caller', visibility='eligible',
        target=dict(strategy='direct', agent_id='subject'), payload='Work beyond capacity')
    assert offered['ok'], offered
    gid = grant(runtime)
    pause(setup, binding)
    for _ in range(32):
        assert send(setup, monkeypatch)['ok']
    refused = claim(runtime, offered['data']['handoff_id'], gid)
    assert not refused['ok'] and refused['error']['code'] == 'QUOTA_EXCEEDED', refused
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs').fetchone()[0] == 'OPEN'
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (gid,)).fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_handoff_bindings').fetchone()[0] == 0
        assert uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0] == 32
    assert not native.native.sent


def test_native_acceptance_releases_only_pending_capacity(connected_local, monkeypatch):
    setup, binding, native = connected_local
    enable(setup, binding)
    assert send(setup, monkeypatch)['ok']
    first = current_turn(setup)
    wait_receipt(setup, first)
    setup[2].portal.call(setup[1].state.embedded_dispatch_owner.pump.stop)
    setup[0].config.max_new_roots_per_agent_per_minute = 256
    # Core has proved native acceptance, unlike the retired write-only ACK.
    # The running turn remains owned while up to 32 following turns can queue.
    for _ in range(32):
        assert send(setup, monkeypatch)['ok']
    refused = send(setup, monkeypatch)
    assert not refused['ok'] and refused['error']['code'] == 'QUOTA_EXCEEDED', refused
    counts(setup, 33)
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM message_deliveries WHERE status='delivered'").fetchone()[0] == 1
    assert len(native.native.sent) == 1


def test_byte_budget_refuses_without_partial_logical_delivery(connected_local, monkeypatch):
    from test_pr34_remediation import tool
    from okto_nexus.application import execution_capacity
    setup, binding, native = connected_local
    pause(setup, binding)
    # Smaller aggregate budget exercises bytes before the independent 32-item
    # cap, while each message remains within the native 64 KiB payload bound.
    monkeypatch.setattr(execution_capacity, 'REGULAR_BYTES', 128 * 1024)
    setup[2].headers['host'] = '127.0.0.1:8000'
    key = setup[3]['operator']['Authorization'].removeprefix('Bearer ')
    accepted = 0
    for _ in range(32):
        reply = tool(setup[2], key, 'message_create', dict(project_root=str(setup[-1]),
            from_agent_id='operator', subject='Accumulated byte budget', body='x' * (48 * 1024),
            target=dict(strategy='direct', agent_id='subject')))
        if not reply['ok']:
            break
        accepted += 1
    assert 0 < accepted < 32, reply
    assert not reply['ok'] and reply['error']['code'] == 'QUOTA_EXCEEDED', reply
    counts(setup, accepted)
    assert not native.native.sent
