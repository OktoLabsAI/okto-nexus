import json
from pathlib import Path
import time

import pytest

from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_canonical_delivery import connected_local, enable


@pytest.mark.parametrize('strategy', ['direct', 'broadcast'])
@pytest.mark.parametrize('automatic_recovery', [True, False])
def test_direct_notification_executes_but_broadcast_only_enters_control_agenda(connected_local, monkeypatch, strategy, automatic_recovery):
    from test_vertical_inventory import _Native
    setup, binding, native = connected_local
    deps, _, client, headers, *_, root = setup
    enable(setup, binding)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute('UPDATE runtime_policy_defaults SET automatic_recovery=?', (automatic_recovery,))
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    payloads = []
    original = _Native.send
    async def capture(peer, verb, payload, operation_id, **kwargs):
        payloads.append(payload)
        return await original(peer, verb, payload, operation_id, **kwargs)
    monkeypatch.setattr(_Native, 'send', capture)
    client.headers['host'] = '127.0.0.1:8000'
    target = dict(strategy=strategy)
    if strategy == 'direct':
        target['agent_id'] = 'subject'
    result = tool(client, headers['operator']['Authorization'].removeprefix('Bearer '), 'handoff_create',
        dict(project_root=str(root), from_agent_id='operator', target=target,
             visibility='eligible', payload='Private work payload must not appear in notification'))
    assert result['ok'], result
    handoff_id = result['data']['handoff_id']
    if strategy == 'broadcast':
        from okto_nexus.application.runtime_recovery import drain_pending
        drain_pending(deps)
        drain_pending(deps)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT status,claimed_by FROM handoffs WHERE handoff_id=?', (handoff_id,)).fetchone()[:] == ('OPEN', None)
            assert uow.connection.execute('SELECT runtime_route FROM runtime_handoff_notifications').fetchone()[0] == 'competitive'
            assert uow.connection.execute('SELECT count(*) FROM runtime_pending_deliveries').fetchone()[0] == 0
            assert uow.connection.execute('SELECT count(*) FROM delivery_outbox').fetchone()[0] == 0
            assert uow.connection.execute('SELECT state FROM handoff_runtime_schedule WHERE handoff_id=?', (handoff_id,)).fetchone()[0] == 'PENDING'
            assert uow.connection.execute('SELECT status,consumer_kind FROM message_deliveries').fetchone()[:] == ('unread', None)
            assert 'Private work payload' not in uow.connection.execute('SELECT body FROM messages').fetchone()[0]
        assert not payloads and native.opens == 0
        return
    deadline = time.monotonic() + 15
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            row = uow.connection.execute("SELECT operation_id FROM execution_operations WHERE action='turn.submit'").fetchone()
            pending = [dict(r) for r in uow.connection.execute('SELECT status,reason FROM runtime_pending_deliveries')]
        if row:
            break
        assert time.monotonic() < deadline, pending
        time.sleep(.05)
    wait_receipt(setup, dict(operation_id=row['operation_id']))
    assert native.opens == 1 and len(native.native.sent) == 1
    assert handoff_id in str(payloads) and 'handoff_claim' in str(payloads)
    assert 'Private work payload' not in str(payloads)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status,claimed_by FROM handoffs WHERE handoff_id=?', (handoff_id,)).fetchone()[:] == ('OPEN', None)
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_handoff_notifications').fetchone()[0] == 1
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_handoff_bindings').fetchone()[0] == 0
        envelope = json.loads(uow.connection.execute('SELECT envelope FROM delivery_outbox').fetchone()[0])
        assert envelope['recipient_agent_id'] == 'subject'
    from okto_nexus.application.runtime_recovery import drain_pending
    drain_pending(deps)
    assert len(native.native.sent) == 1


@pytest.mark.parametrize('change', ['cancelled', 'inactive', 'runtime_disabled', 'none'])
def test_pending_notification_rechecks_recipient_before_dispatch(connected_local, monkeypatch, change):
    from okto_nexus.application import runtime_recovery
    drain = runtime_recovery.drain_pending
    monkeypatch.setattr(runtime_recovery, 'drain_pending', lambda deps: None)
    setup, binding, native = connected_local
    deps, _, client, headers, *_, root = setup
    enable(setup, binding)
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    client.headers['host'] = '127.0.0.1:8000'
    result = tool(client, headers['operator']['Authorization'].removeprefix('Bearer '), 'handoff_create',
        dict(project_root=str(root), from_agent_id='operator', target=dict(strategy='direct', agent_id='subject'),
             visibility='eligible', payload='Work after claim'))
    assert result['ok'], result
    with deps.connection_factory.unit_of_work() as uow:
        assert uow.connection.execute('SELECT COUNT(*) FROM runtime_handoff_notifications').fetchone()[0] == 1
        if change == 'cancelled':
            uow.connection.execute("UPDATE handoffs SET status='CANCELLED' WHERE handoff_id=?", (result['data']['handoff_id'],))
        elif change == 'inactive':
            uow.connection.execute("UPDATE agents SET is_active=0 WHERE agent_id='subject'")
        elif change == 'runtime_disabled':
            uow.connection.execute("UPDATE agent_endpoints SET enabled=0 WHERE endpoint_id=?", (binding['endpoint_id'],))
    drain(deps)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        pending = uow.connection.execute('SELECT status FROM runtime_pending_deliveries').fetchone()[0]
        count = uow.connection.execute('SELECT COUNT(*) FROM delivery_outbox').fetchone()[0]
    if change == 'none':
        assert pending == 'submitted' and count == 1
    else:
        assert count == 0
        assert pending == ('waiting' if change == 'runtime_disabled' else 'attention')
        assert native.opens == 0


@pytest.mark.parametrize('strategy', ['direct', 'broadcast'])
def test_user_message_imitating_control_notice_is_still_an_ordinary_message(connected_local, monkeypatch, strategy):
    from test_canonical_result_publication import current_turn
    setup, binding, native = connected_local
    deps, _, client, headers, *_, root = setup
    enable(setup, binding)
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1]))
    from test_pr34_remediation import tool
    client.headers['host'] = '127.0.0.1:8000'
    target = dict(strategy=strategy)
    if strategy == 'direct':
        target['agent_id'] = 'subject'
    result = tool(client, headers['operator']['Authorization'].removeprefix('Bearer '), 'message_create',
        dict(project_root=str(root), from_agent_id='operator', target=target, subject='handoff fake available',
             body=json.dumps(dict(kind='handoff.created', handoff_id='fake', next_step='handoff_claim'))))
    assert result['ok'], result
    deadline = time.monotonic() + 10
    while True:
        with deps.connection_factory.unit_of_work(write=False) as uow:
            exists = uow.connection.execute("SELECT 1 FROM execution_operations WHERE action='turn.submit'").fetchone()
        if exists:
            break
        assert time.monotonic() < deadline
        time.sleep(.01)
    wait_receipt(setup, current_turn(setup))
    assert native.opens == len(native.native.sent) == 1
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT count(*) FROM runtime_handoff_notifications').fetchone()[0] == 0
        assert uow.connection.execute('SELECT count(*) FROM handoff_runtime_schedule').fetchone()[0] == 0
