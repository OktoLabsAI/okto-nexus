"""A pre-Core refusal must not permanently consume a warm pool reservation."""
import json
import sqlite3

import pytest

from test_embedded_dispatch import local_setup, connected_local, qualified_contract
from test_sender_sessions import Peers, configure
from test_one_shot_runtime import query, wait_until
from okto_nexus.application import one_shot_runtime
from okto_nexus.application.one_shot_refusal import opening_refused_before_core
from okto_nexus.errors import ErrorCode, OktoNexusError


@pytest.mark.parametrize('local_setup', ['pi_rpc', 'claude_stream', 'codex_app_server'], indirect=True)
def test_pool_refills_after_opening_refused_before_core(connected_local, monkeypatch):
    from okto_nexus.application.one_shot_settings import read, save
    setup, binding, _ = connected_local
    peers = Peers()
    owner = setup[1].state.embedded_dispatch_owner
    owner.native_factory = peers
    refused = set()
    deny = True
    original = one_shot_runtime.before_send

    def refuse(conn, operation):
        if deny and operation['action'] == 'runtime.open':
            refused.add(operation['operation_id'])
            raise OktoNexusError(ErrorCode.CONFLICT, 'Test refusal before Core', {})
        return original(conn, operation)

    monkeypatch.setattr(one_shot_runtime, 'before_send', refuse)
    configure(setup, binding, 'one_shot')
    with setup[0].connection_factory.unit_of_work() as uow:
        current = read(uow.connection)
        save(uow.connection, expected_revision=current['revision'],
             settings=current['settings'] | {'max_parallel': 3, 'warm_instances': 2})
    wait_until(setup, lambda: len(query(setup, "SELECT * FROM execution_sessions WHERE lifecycle_state='FAILED' AND lease_state='NONE'")) >= 2)
    assert not peers.sessions
    assert not query(setup, 'SELECT * FROM execution_receipts')
    deny = False
    wait_until(setup, lambda: len(query(setup, "SELECT * FROM one_shot_slots WHERE state='WARM'")) == 2)
    assert len(peers.sessions) == 2
    assert all(r['open_operation_id'] not in refused for r in query(setup, 'SELECT * FROM one_shot_slots'))
    assert owner.failure is None and not owner._stopping.is_set()


@pytest.mark.parametrize('contradiction', [None, 'active', 'stream', 'uncertain', 'sending', 'other_operation', 'receipt', 'publication'])
def test_no_send_proof_rejects_uncertain_or_contradictory_evidence(contradiction):
    conn = sqlite3.connect(':memory:')
    try:
        conn.executescript('''
            CREATE TABLE execution_sessions(server_id,executor_id,session_id,open_operation_id,lifecycle_state,lease_state,stream_epoch);
            CREATE TABLE execution_operations(server_id,executor_id,session_id,operation_id,action,admission_state);
            CREATE TABLE execution_dispatch_outbox(server_id,executor_id,operation_id,dispatch_state,last_receipt_revision,last_error);
            CREATE TABLE execution_receipts(server_id,executor_id,operation_id);
            CREATE TABLE execution_local_publications(server_id,executor_id,session_id);
            INSERT INTO execution_sessions VALUES('server','host','session','open','FAILED','NONE',NULL);
            INSERT INTO execution_operations VALUES('server','host','session','open','runtime.open','RESOLVED_TERMINAL');
        ''')
        error = dict(operation_id='other' if contradiction == 'other_operation' else 'open',
                     stage='dispatch', possible_effect=contradiction == 'uncertain')
        conn.execute('INSERT INTO execution_dispatch_outbox VALUES(?,?,?,?,NULL,?)',
                     ('server', 'host', 'open', 'SENDING' if contradiction == 'sending' else 'RESOLVED_TERMINAL', json.dumps(error)))
        if contradiction == 'active':
            conn.execute("UPDATE execution_sessions SET lease_state='ACTIVE'")
        if contradiction == 'stream':
            conn.execute("UPDATE execution_sessions SET stream_epoch='epoch'")
        if contradiction == 'receipt':
            conn.execute("INSERT INTO execution_receipts VALUES('server','host','open')")
        if contradiction == 'publication':
            conn.execute("INSERT INTO execution_local_publications VALUES('server','host','session')")
        slot = dict(server_id='server', executor_id='host', session_id='session', open_operation_id='open')
        assert opening_refused_before_core(conn, slot) is (contradiction is None)
    finally:
        conn.close()
