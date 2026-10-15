"""Reconciliation retires containment only with exact resource/stream proof."""
import json
from types import SimpleNamespace

import pytest
from nexus_connector_core import r4_resource_release_digest

from okto_nexus.application.execution_session_containment import ExecutionSessionContainment
from okto_nexus.adapters.outbound.sqlite.execution_session_containment import SqliteSessionContainmentRepository
from test_reconciliation import recovery, seed_receipt
from test_binding_operator import onboarding


@pytest.mark.parametrize('fault', [None, 'digest', 'stream', 'generation', 'new_receipt', 'commit_failure'])
def test_obligation_requires_reconciled_original_resource_and_commits_atomically(recovery, monkeypatch, fault):
    factory, service, report, _, frame = recovery
    c = service.channel
    repository = SqliteSessionContainmentRepository()
    service.containment = ExecutionSessionContainment(factory=factory, repository=repository,
        clock=SimpleNamespace(now_iso=lambda: '2026-10-14T00:00:00Z'))
    with factory.unit_of_work() as uow:
        conn = uow.connection
        conn.execute("UPDATE execution_operations SET action='runtime.open'")
        conn.execute("UPDATE execution_sessions SET open_operation_id='close'")
        conn.execute('INSERT INTO execution_session_containment(server_id,executor_id,session_id,owner_generation,'
            "opening_operation_id,opening_intent_hash,request_json,recorded_at) VALUES (?,?,'session',1,'close',?,'{}','before')",
            (c.server_id, c.executor_id, frame['intent_hash']))
    report['ownership_facts'][0]['proof_digest'] = r4_resource_release_digest(
        server_id=c.server_id, executor_id=c.executor_id, session_id='session',
        opening_operation_id='close', opening_intent_hash=frame['intent_hash'], owner_generation=1)
    if fault == 'digest':
        report['ownership_facts'][0]['proof_digest'] = 'sha256:' + 'f' * 64
    elif fault == 'stream':
        report['stream_watermarks'][0]['sequence'] = 1
    elif fault == 'generation':
        report['ownership_facts'][0]['owner_generation'] = report['claims'][0]['owner_generation'] = 2
    elif fault == 'new_receipt':
        seed_receipt(factory, dict(frame, receipt_revision=2))
    elif fault == 'commit_failure':
        original = repository.complete_verified
        def failed(*args):
            original(*args)
            raise RuntimeError('injected after obligation update')
        monkeypatch.setattr(repository, 'complete_verified', failed)
    if fault == 'commit_failure':
        with pytest.raises(RuntimeError, match='after obligation'):
            service.accept(report)
    else:
        assert service.accept(report)['recovery_remaining'] is (fault is not None)
    with factory.unit_of_work(write=False) as uow:
        row = uow.connection.execute('SELECT * FROM execution_session_containment').fetchone()
        assert row['state'] == ('RELEASED' if fault is None else 'REQUESTED')
        if fault is None:
            assert json.loads(row['release_proof_json']) == dict(
                ownership=report['ownership_facts'][0], stream=report['stream_watermarks'][0])
            assert row['released_at'] == '2026-10-14T00:00:00Z'
        else:
            assert row['release_proof_json'] is None and row['released_at'] is None
        if fault == 'commit_failure':
            assert uow.connection.execute('SELECT control_state FROM execution_executors WHERE executor_id=?',
                (c.executor_id,)).fetchone()[0] == 'RECOVERING'
            assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions').fetchone()[0] == 'READY'
        assert uow.connection.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == (2 if fault == 'new_receipt' else 1)
        assert not uow.connection.execute("SELECT 1 FROM execution_operations WHERE action='runtime.close'").fetchone()
