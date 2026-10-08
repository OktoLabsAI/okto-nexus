"""Retained attach records keep their writer fences after feature removal."""
import hashlib
import json
import sqlite3

import pytest

from test_pr34_remediation import runtime, tool
from test_runtime_handoff_dispatch import work


def retained(runtime):
    deps, client, root, peers, operator, caller = runtime
    hid, worker = work(runtime)
    claimed = tool(client, worker, 'handoff_claim', dict(project_root=root, handoff_id=hid, agent_id='worker'))
    assert claimed['ok'], claimed
    epoch = claimed['data']['claim_epoch']
    with deps.connection_factory.unit_of_work(write=False) as uow:
        workspace = uow.connection.execute('SELECT workspace_id FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[0]
    opened = tool(client, worker, 'session_open', dict(agent_id='worker', workspace_id=workspace))
    assert opened['ok'], opened
    proof = {k: opened['data'][k] for k in ('session_id', 'session_secret')}
    sent = tool(client, caller, 'message_create', dict(project_root=root, from_agent_id='caller',
        subject='Retained external work', body='Historical work', target=dict(strategy='direct', agent_id='worker')))
    assert sent['ok'], sent
    message = sent['data']['message_id']
    now = deps.clock.now_iso()
    with deps.connection_factory.unit_of_work() as uow:
        conn = uow.connection
        credential = conn.execute("SELECT api_key_hash FROM agents WHERE agent_id='worker'").fetchone()[0]
        delivery = conn.execute("SELECT delivery_id FROM message_deliveries WHERE message_id=? AND recipient_agent_id='worker'", (message,)).fetchone()[0]
        def insert(table, **values):
            conn.execute('INSERT INTO ' + table + '(' + ','.join(values) + ') VALUES(' + ','.join('?' for _ in values) + ')', tuple(values.values()))
        insert('agent_endpoints', endpoint_id='retired-attach', agent_id='worker', workspace_id=workspace,
            adapter_id='claude_code.attach', protocol='legacy', enabled=0, activation_state='approved',
            public_config=json.dumps(dict(nexus_work_session_id=proof['session_id'])), created_at=now, updated_at=now)
        insert('runtime_execution_grants', grant_id='retained-grant', issuer_agent_id='operator', actor_agent_id='worker',
            credential_binding=credential, represented_agent_id='worker', workspace_id=workspace, endpoint_id='retired-attach',
            actions='["execute_work","read"]', expires_at='2099-01-01T00:00:00Z', max_executions=1, used_executions=1, created_at=now)
        insert('delivery_outbox', operation_id='retained-operation', delivery_id=delivery, message_id=message, workspace_id=workspace,
            actor_agent_id='worker', credential_binding=credential, recipient_agent_id='worker', endpoint_id='retired-attach',
            endpoint_revision=1, envelope='{}', request_hash='retained-hash', authorization_revision='retained-authority',
            root_operation_id='retained-operation', status='OUTCOME_UNKNOWN', ack_level='TRANSPORT_WRITE',
            owner_epoch=1, attempt_id='retained-attempt', attempt_count=1, created_at=now, updated_at=now)
        insert('runtime_handoff_bindings', handoff_id=hid, claim_epoch=epoch, operation_id='retained-operation',
            grant_id='retained-grant', grant_revision=1, actor_agent_id='worker', idempotency_key='retained-work',
            request_hash='retained-work-hash', created_at=now, external_session_id=proof['session_id'],
            external_secret_binding=hashlib.sha256(proof['session_secret'].encode()).hexdigest())
        conn.execute("UPDATE message_deliveries SET consumer_kind='push',consumer_operation_id='retained-operation' WHERE delivery_id=?", (delivery,))
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    assert peers == []
    return hid, worker, proof, message, epoch


@pytest.mark.parametrize('destination', ['COMPLETED', 'VERIFYING', 'REJECTED'])
def test_retained_external_work_rejects_old_writer_completion_and_ack(runtime, destination):
    deps = runtime[0]
    hid, _, _, _, epoch = retained(runtime)
    legacy = sqlite3.connect(deps.config.db_path, isolation_level=None)
    legacy.create_function('nexus_runtime_writer_v1', 0, lambda: 1)
    try:
        with pytest.raises(sqlite3.IntegrityError, match='runtime_external_work_writer_incompatible'):
            legacy.execute("UPDATE handoffs SET status=?,result=?,updated_at=? WHERE handoff_id=? AND claimed_by='worker' AND claim_epoch=? AND status='CLAIMED'",
                (destination, 'unproved legacy result', deps.clock.now_iso(), hid, epoch))
        with pytest.raises(sqlite3.IntegrityError, match='runtime_external_work_writer_incompatible'):
            legacy.execute("UPDATE message_deliveries SET status='read',read_at=? WHERE consumer_operation_id='retained-operation'", (deps.clock.now_iso(),))
    finally:
        legacy.close()
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[0] == 'CLAIMED'
        assert uow.connection.execute("SELECT status FROM message_deliveries WHERE consumer_operation_id='retained-operation'").fetchone()[0] != 'read'


def test_retained_external_session_survives_ordinary_session_retention(runtime):
    from okto_nexus.domain.base import iso_plus
    deps, client, *_ = runtime
    _, worker, proof, _, _ = retained(runtime)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        workspace = uow.connection.execute("SELECT workspace_id FROM delivery_outbox WHERE operation_id='retained-operation'").fetchone()[0]
    unrelated = tool(client, worker, 'session_open', dict(agent_id='worker', workspace_id=workspace))
    assert unrelated['ok'], unrelated
    other = unrelated['data']['session_id']
    for sid in (proof['session_id'], other):
        closed = tool(client, worker, 'session_close', dict(session_id=sid))
        assert closed['ok'], closed
    with deps.connection_factory.unit_of_work() as uow:
        cutoff = iso_plus(deps.clock.now_iso(), 60)
        assert deps.repos.sessions.count_closed_before(uow, cutoff=cutoff) == 1
        assert deps.repos.sessions.prune_closed_before(uow, cutoff=cutoff, limit=100) == 1
        assert deps.repos.sessions.get(uow, proof['session_id']) is not None
        assert deps.repos.sessions.get(uow, other) is None
        assert not uow.connection.execute('PRAGMA foreign_key_check').fetchall()


@pytest.mark.parametrize('action', ['ack', 'complete'])
def test_retired_attach_proof_cannot_resume_external_execution(runtime, action):
    deps, client, root, peers, *_ = runtime
    hid, worker, proof, message, epoch = retained(runtime)
    arguments = (dict(agent_id='worker', message_ids=[message], **proof) if action == 'ack' else
        dict(project_root=root, handoff_id=hid, agent_id='worker', claim_epoch=epoch, result='removed feature', **proof))
    denied = tool(client, worker, 'inbox_ack' if action == 'ack' else 'handoff_complete', arguments)
    assert not denied['ok'], denied
    assert peers == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT status FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()[0] == 'CLAIMED'
        assert uow.connection.execute("SELECT external_completed_at FROM delivery_outbox WHERE operation_id='retained-operation'").fetchone()[0] is None
        assert uow.connection.execute("SELECT ack_level FROM delivery_outbox WHERE operation_id='retained-operation'").fetchone()[0] == 'TRANSPORT_WRITE'
        assert not uow.connection.execute('SELECT 1 FROM runtime_results').fetchone()


def test_operator_can_reopen_retired_external_claim_without_resuming_attach(runtime):
    from test_runtime_handoff_recovery import recovery
    deps, client, root, peers, operator, _ = runtime
    hid, worker, _, _, epoch = retained(runtime)
    with deps.connection_factory.unit_of_work(write=False) as uow:
        operation = dict(uow.connection.execute("SELECT * FROM delivery_outbox WHERE operation_id='retained-operation'").fetchone())
    response = client.post('/api/v1/harness/outbox', headers={'x-api-key': operator},
        json=recovery(hid, epoch, operation))
    assert response.status_code == 200, response.text
    result = response.json()['data']
    assert result['handoff']['status'] == 'OPEN'
    assert not result['native_replayed'] and not result['result_invented']
    rejected = tool(client, worker, 'handoff_reject', dict(project_root=root, handoff_id=hid,
        agent_id='worker', reason='Decline the reopened offer'))
    assert rejected['ok'], rejected
    assert peers == []
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute("SELECT external_completion_action FROM runtime_handoff_bindings WHERE operation_id='retained-operation'").fetchone()[0] is None
        assert uow.connection.execute("SELECT status FROM handoffs WHERE handoff_id=?", (hid,)).fetchone()[0] == 'REJECTED'
        assert not uow.connection.execute('SELECT 1 FROM runtime_results').fetchone()


def test_retained_external_claim_does_not_consume_or_relabel_ordinary_inbox(runtime):
    deps, client, root, peers, _, caller = runtime
    _, worker, proof, external, _ = retained(runtime)
    ordinary = []
    for index in range(2):
        sent = tool(client, caller, 'message_create', dict(project_root=root, from_agent_id='caller',
            subject='Ordinary ' + str(index), body='Pull delivery', target=dict(strategy='direct', agent_id='worker')))
        assert sent['ok'], sent
        ordinary.append(sent['data']['message_id'])
    pulled = tool(client, worker, 'inbox_pull', dict(agent_id='worker', **proof))
    assert pulled['ok'], pulled
    messages = {m['message_id'] for m in pulled['data']['messages']}
    assert set(ordinary) <= messages and external not in messages
    mixed = tool(client, worker, 'inbox_ack', dict(agent_id='worker', message_ids=[*ordinary, external], **proof))
    assert not mixed['ok'], mixed
    with deps.connection_factory.unit_of_work(write=False) as uow:
        assert all(uow.connection.execute("SELECT status FROM message_deliveries WHERE message_id=? AND recipient_agent_id='worker'", (mid,)).fetchone()[0] != 'read' for mid in [*ordinary, external])
    ack = tool(client, worker, 'inbox_ack', dict(agent_id='worker', message_ids=ordinary, **proof))
    assert ack['ok'] and ack['data']['acknowledged'] == 2, ack
    repeated = tool(client, worker, 'inbox_ack', dict(agent_id='worker', message_ids=ordinary, **proof))
    assert repeated['ok'] and repeated['data']['acknowledged'] == 0, repeated
    with deps.connection_factory.unit_of_work(write=False) as uow:
        bodies = []
        for row in uow.connection.execute("SELECT body FROM messages WHERE from_agent_id='worker'"):
            try:
                body = json.loads(row[0])
            except ValueError:
                continue
            if isinstance(body, dict) and body.get('kind') == 'message.read_receipt':
                bodies.append(body)
        grouped = [b for b in bodies if set(b['message_ids']) == set(ordinary)]
        assert len(grouped) == 1 and 'ack_source' not in grouped[0] and 'operation_id' not in grouped[0]
        assert all(external not in b['message_ids'] for b in bodies)
    assert peers == []
