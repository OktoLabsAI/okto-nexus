"""Approved alternatives never transfer authority or ambiguous native effects."""
import json

import pytest
from nexus_connector_core.models import EffectNotSent
from test_harness_canonical import qualified_bridge
from test_embedded_dispatch import local_setup, qualified_contract, admit, wait_receipt
from test_canonical_delivery import connected_local, enable, send
from test_canonical_identity_lifecycle import second_binding
from test_canonical_delivery_retry import wait_delivery
from test_canonical_handoff import prepare
from test_vertical_inventory import _Native


def pair(connected, monkeypatch):
    setup, first, native = connected
    second = second_binding(setup, monkeypatch)
    for binding in (first, second):
        enable(setup, binding)
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET selection_group='approved-alternatives',priority=1")
        uow.connection.execute('UPDATE agent_endpoints SET priority=10 WHERE endpoint_id=?', (first['endpoint_id'],))
    clock = [setup[0].clock.now_iso()]
    monkeypatch.setattr(setup[0].clock, 'now_iso', lambda: clock[0])
    calls = []
    original = _Native.send
    async def refuse_once(peer, verb, payload, operation_id, **kwargs):
        calls.append((operation_id, payload))
        if len(calls) == 1:
            raise EffectNotSent('No bytes written', code='CAPACITY_EXCEEDED')
        return await original(peer, verb, payload, operation_id, **kwargs)
    monkeypatch.setattr(_Native, 'send', refuse_once)
    return setup, first, second, native, clock, calls


@pytest.mark.parametrize('change', ['group', 'disabled', 'profile', 'workspace', 'agent'])
def test_fallback_excludes_unapproved_or_foreign_target(connected_local, monkeypatch, change):
    setup, first, second, native, clock, calls = pair(connected_local, monkeypatch)
    with setup[0].connection_factory.unit_of_work() as uow:
        conn = uow.connection
        if change == 'group':
            conn.execute("UPDATE agent_endpoints SET selection_group='unrelated' WHERE endpoint_id=?", (second['endpoint_id'],))
        elif change == 'disabled':
            conn.execute('UPDATE agent_endpoints SET enabled=0 WHERE endpoint_id=?', (second['endpoint_id'],))
        elif change == 'profile':
            conn.execute('UPDATE runtime_profiles SET enabled=0 WHERE profile_id=(SELECT profile_id FROM agent_endpoints WHERE endpoint_id=?)', (second['endpoint_id'],))
        elif change == 'workspace':
            conn.execute("INSERT INTO workspaces(workspace_id,created_at) VALUES('other-workspace',?)", (clock[0],))
            conn.execute("UPDATE agent_endpoints SET workspace_id='other-workspace' WHERE endpoint_id=?", (second['endpoint_id'],))
        else:
            conn.execute("UPDATE agent_endpoints SET agent_id='operator' WHERE endpoint_id=?", (second['endpoint_id'],))
    assert send(setup, monkeypatch)['ok']
    pending = wait_delivery(setup, lambda row: row['status'] == 'RETRY_WAIT' and row['reason'] == 'native_write_not_started')
    assert pending['next_binding'] is None and pending['endpoint_id'] == first['endpoint_id']
    clock[0] = pending['next_attempt_at']
    setup[0].runtime_dispatcher.wake()
    accepted = wait_delivery(setup, lambda row: row['status'] == 'ACCEPTED')
    assert accepted['endpoint_id'] == first['endpoint_id']
    assert native.opens == 1 and len(calls) == 2 and len(native.native.sent) == 1


@pytest.mark.parametrize('opened_target', [False, True])
def test_fallback_preserves_envelope_and_exposes_both_attempts(connected_local, monkeypatch, opened_target):
    setup, first, second, native, clock, calls = pair(connected_local, monkeypatch)
    if opened_target:
        # Shared sessions make the pre-opened target available to this sender.
        with setup[0].connection_factory.unit_of_work() as uow:
            uow.connection.execute("UPDATE runtime_policy_defaults SET session_policy='shared'")
        opened = admit(setup, second, 'fallback-ready-target', 'runtime.start', new_session=True)
        wait_receipt(setup, opened)
        source = admit(setup, first, 'fallback-ready-source', 'runtime.start', new_session=True)
        wait_receipt(setup, source)
    created = send(setup, monkeypatch)
    assert created['ok'], created
    pending = wait_delivery(setup, lambda row: row['status'] == 'RETRY_WAIT' and row['next_binding'] is not None)
    assert json.loads(pending['next_binding'])['endpoint_id'] == second['endpoint_id']
    clock[0] = pending['next_attempt_at']
    setup[0].runtime_dispatcher.wake()
    accepted = wait_delivery(setup, lambda row: row['status'] == 'ACCEPTED')
    assert accepted['endpoint_id'] == second['endpoint_id']
    for field in ('operation_id', 'message_id', 'delivery_id', 'envelope', 'request_hash'):
        assert accepted[field] == pending[field]
    assert len(calls) == 2 and calls[0][0] != calls[1][0]
    wire = calls[1][1]
    text = wire if isinstance(wire, str) else wire['text']
    lines = text.splitlines()
    expected = json.loads(pending['envelope'])
    # Trust classification remains in durable storage, outside native context.
    expected.pop('trust')
    assert json.loads(lines[1]) == expected
    binding = json.loads(lines[3])
    assert binding['endpoint_id'] == second['endpoint_id']
    assert binding['canonical_envelope_hash'] == pending['request_hash']
    inspected = setup[2].get('/api/v1/harness/outbox', headers=setup[3]['operator'],
                            params={'operation_id': pending['operation_id']})
    assert inspected.status_code == 200, inspected.text
    history = inspected.json()['data']['items'][0]['attempt_history']
    assert {entry['endpoint_id'] for entry in history} == {first['endpoint_id'], second['endpoint_id']}
    assert any(entry['state'] == 'RETRY_WAIT' for entry in history)
    assert accepted['attempt_id'] != pending['attempt_id']
    assert any(entry['state'] == 'ACCEPTED' and entry['attempt_id'] == accepted['attempt_id'] for entry in history)
    from test_pr34_remediation import tool
    queried = tool(setup[2], setup[3]['operator']['Authorization'].removeprefix('Bearer '),
                   'harness_list', {'view': 'outbox', 'maintenance': {'operation_id': pending['operation_id']}})
    assert queried['ok'] and queried['data'] == inspected.json()['data']
    assert native.opens == 2
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        turn = uow.connection.execute("SELECT p.operation_id FROM execution_domain_deliveries d JOIN execution_operations p "
            "USING(server_id,executor_id,operation_id) WHERE d.domain_operation_id=? AND p.action='turn.submit'",
            (pending['operation_id'],)).fetchone()
        assert turn[0] == accepted['attempt_id']
        assert uow.connection.execute('SELECT count(*) FROM message_deliveries').fetchone()[0] == 1
        assert uow.connection.execute('SELECT count(*) FROM delivery_outbox').fetchone()[0] == 1


def test_conversation_continuation_retries_only_its_original_binding(connected_local, monkeypatch):
    from test_pr34_remediation import tool
    setup, first, second, native, clock, calls = pair(connected_local, monkeypatch)
    parent = send(setup, monkeypatch, target=dict(strategy='direct', agent_id='operator'))
    assert parent['ok'], parent
    created = tool(setup[2], setup[3]['operator']['Authorization'].removeprefix('Bearer '),
        'message_create', dict(project_root=str(setup[-1]), from_agent_id='operator',
        subject='Continuation', body='Retain original context', parent_message_id=parent['data']['message_id'],
        target=dict(strategy='direct', agent_id='subject')))
    assert created['ok'], created
    pending = wait_delivery(setup, lambda row: row['status'] == 'RETRY_WAIT')
    assert pending['endpoint_id'] == first['endpoint_id'] and pending['next_binding'] is None
    clock[0] = pending['next_attempt_at']
    setup[0].runtime_dispatcher.wake()
    accepted = wait_delivery(setup, lambda row: row['status'] == 'ACCEPTED')
    assert accepted['endpoint_id'] == first['endpoint_id']
    assert accepted['operation_id'] == pending['operation_id']
    assert native.opens == 1 and len(calls) == 2 and len(native.native.sent) == 1
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert not uow.connection.execute('SELECT 1 FROM execution_sessions WHERE binding_id=?', (second['binding_id'],)).fetchone()


def test_post_write_exception_cannot_use_approved_alternative(connected_local, monkeypatch):
    setup, first, second, native, _, calls = pair(connected_local, monkeypatch)
    async def ambiguous(peer, verb, payload, operation_id, **kwargs):
        calls.append((operation_id, payload))
        peer.sent.append((verb, payload))
        raise OSError('Runtime delivery lane is occupied; retry_safe=true')
    monkeypatch.setattr(_Native, 'send', ambiguous)
    assert send(setup, monkeypatch)['ok']
    row = wait_delivery(setup, lambda row: row['status'] == 'OUTCOME_UNKNOWN')
    for _ in range(3):
        setup[0].runtime_dispatcher.scan_once()
    assert row['next_binding'] is None and row['next_attempt_at'] is None
    assert native.opens == 1 and len(calls) == 1
    assert row['endpoint_id'] == first['endpoint_id']


def test_work_grant_cannot_authorize_fallback_to_another_binding(connected_local, monkeypatch):
    setup, first, second, native, _, calls = pair(connected_local, monkeypatch)
    # Preparing the handoff must not dispatch its separate creation notice
    # through the alternative before the governed work has been claimed.
    # prepare() gives the primary a work-only response policy as well.
    with setup[0].connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE agent_endpoints SET response_policy='none' WHERE endpoint_id=?",
                               (second['endpoint_id'],))
    handoff, grant, claim, _ = prepare(setup, first, monkeypatch)
    enable(setup, second)
    created = claim()
    assert created['ok'], created
    row = wait_delivery(setup, lambda row: row['status'] == 'FAILED_FINAL')
    assert json.loads(row['envelope'])['handoff_id'] == handoff
    for _ in range(3):
        setup[0].runtime_dispatcher.scan_once()
    assert row['next_binding'] is None and row['endpoint_id'] == first['endpoint_id']
    assert native.opens == 1 and len(calls) == 1 and native.native.sent == []
    with setup[0].connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs WHERE handoff_id=?', (handoff,)).fetchone()[0] == 'CLAIMED'
        assert uow.connection.execute('SELECT used_executions FROM runtime_execution_grants WHERE grant_id=?', (grant,)).fetchone()[0] == 1
