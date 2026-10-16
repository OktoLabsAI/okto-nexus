"""An authenticated never-started proof closes only its original failed open."""
from dataclasses import asdict

import pytest

from nexus_connector_core import CoreError, SessionKey, encode_r4_frame, decode_r4_frame
from nexus_connector_core.launch_release_r4 import unstarted_release_digest
from nexus_connector_core.process_launch import ProcessLaunchIdentity, ProcessLaunchRecord
from okto_nexus.application.execution_reconciliation import ExecutionReconciliation
from test_reconciliation import onboarding, recovery, seed_receipt, state


def never_started(recovery, *, marked=True):
    factory, old_service, _, _, old_frame = recovery
    channel = old_service.channel
    with factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute("UPDATE execution_operations SET action='runtime.open'")
        conn.execute("UPDATE execution_sessions SET open_operation_id='close',lifecycle_state='OPENING'")
        conn.execute('DELETE FROM execution_receipts')
    opening = dict(old_frame, stage='FAILED', possible_effect=marked, retry_safe=not marked,
                   error_code='PROCESS_LAUNCH_FENCED')
    seed_receipt(factory, opening)
    service = ExecutionReconciliation(factory, channel, launch_recovery=True)
    request = service.request()
    proof = asdict(ProcessLaunchRecord(ProcessLaunchIdentity(
        SessionKey(channel.server_id, channel.executor_id, 'session'), 'close',
        opening['connection_generation'], 1, 'win32', 'windows_job',
        'Global\\nexus-core-' + 'a'*32, 'b'*32),
        revision=3, producer_fenced=True, stop_proof='NEVER_CLAIMED'))
    report = {k: v for k, v in request.items() if k not in ('operation_ids','session_ids','stream_watermarks')}
    report.update(type='reconcile.report', complete=True, next_cursor=None,
        receipts=[{k: opening[k] for k in ('operation_id','intent_hash','receipt_revision','stage')}],
        claims=[dict(session_id='session', owner_generation=1, state='RELEASED')],
        ownership_facts=[dict(session_id='session', owner_generation=1, process_state='NOT_STARTED',
            launch_proof=proof, proof_digest=unstarted_release_digest(proof, opening['intent_hash']))],
        stream_watermarks=[dict(session_id='session', stream_epoch='epoch', sequence=0)])
    return factory, service, report, opening


@pytest.mark.parametrize('marked', [False, True])
def test_never_started_releases_failed_session_without_exit_or_receipt_rewrite(recovery, marked):
    factory, service, report, opening = never_started(recovery, marked=marked)
    report = decode_r4_frame(encode_r4_frame(report))
    assert not service.accept(report)['recovery_remaining']
    assert state(factory) == 'CONTROL_READY'
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        row = conn.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()
        assert tuple(row) == ('FAILED','CLOSED')
        row = conn.execute('SELECT stage,possible_effect,retry_safe FROM execution_receipts').fetchone()
        assert tuple(row) == ('FAILED',int(marked),int(not marked))
        assert not conn.execute("SELECT 1 FROM execution_operations WHERE action='runtime.close'").fetchone()


def test_initial_turn_without_receipt_is_retired_only_after_failed_open_proof(recovery):
    factory, service, report, opening = never_started(recovery)
    with factory.unit_of_work() as uow:
        conn = uow.connection
        original = dict(conn.execute('SELECT * FROM execution_operations').fetchone())
        original.update(operation_id='unsent-child', action='turn.submit', parent_operation_id='close',
                        admission_state='ACCEPTED', semantic_payload='{}')
        conn.execute('INSERT INTO execution_operations (' + ','.join(original) + ') VALUES (' +
                     ','.join('?' for _ in original) + ')',tuple(original.values()))
        # Authenticated FAILED receipt publication resolves the parent before
        # recovery can prove the resource was never started.
        conn.execute("UPDATE execution_operations SET admission_state='RESOLVED_TERMINAL' WHERE operation_id='close'")
    service.pending['operation_ids'].append('unsent-child')
    service.op_high += 1
    service.next_op += 1
    assert service.accept(report)['recovery_remaining']
    assert state(factory) == 'RECOVERING'
    service.retry()
    request = service.request()
    assert request['operation_ids'] == []
    with factory.unit_of_work(write=False) as uow:
        conn = uow.connection
        child = conn.execute("SELECT admission_state FROM execution_operations WHERE operation_id='unsent-child'").fetchone()
        assert child[0] == 'RESOLVED_TERMINAL'
        assert not conn.execute("SELECT 1 FROM execution_receipts WHERE operation_id='unsent-child'").fetchone()
        assert conn.execute("SELECT 1 FROM execution_unsent_dispatch_proofs WHERE operation_id='unsent-child'").fetchone()
    report.update({k: request[k] for k in ('reconcile_id','cursor')},receipts=[])
    assert not service.accept(report)['recovery_remaining']


@pytest.mark.parametrize('fault', ['digest','claimed','old_owner','foreign_operation','confirmed_native',
                                  'confirmed_success','unnegotiated'])
def test_contradictory_or_stale_proof_rolls_back_without_releasing_session(recovery, fault):
    factory, service, report, opening = never_started(recovery)
    fact = report['ownership_facts'][0]
    if fault == 'digest': fact['proof_digest'] = 'sha256:' + 'f'*64
    elif fault == 'claimed': fact['launch_proof']['spawn_claimed'] = True
    elif fault == 'foreign_operation': fact['launch_proof']['identity']['opening_operation_id'] = 'foreign'
    elif fault == 'unnegotiated': service.launch_recovery = False
    elif fault == 'old_owner':
        with factory.unit_of_work() as uow:
            uow.connection.execute('UPDATE execution_executors SET generation=3')
    else:
        with factory.unit_of_work() as uow:
            conn = uow.connection
            if fault == 'confirmed_native':
                conn.execute("UPDATE execution_receipts SET native_id='native-original'")
            else:
                seed = dict(opening, stage='SUCCEEDED', receipt_revision=2)
                # Seed outside the active writer transaction below.
        if fault == 'confirmed_success':
            seed_receipt(factory, seed)
    with pytest.raises((CoreError, ValueError)):
        service.accept(report)
    assert state(factory) == 'RECOVERING'
    with factory.unit_of_work(write=False) as uow:
        assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions').fetchone()[0] == 'OPENING'
