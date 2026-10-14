"""Authenticated live-link release does not require whole-executor recovery."""
import copy
import json
import threading

import pytest
from nexus_connector_core import r4_resource_release_digest, encode_r4_frame
from nexus_connector_core.session_release import SESSION_RELEASE_REVISION, encode_session_release, session_receipts_digest

from test_session_containment_obligation import active_lease
from test_ns02_receipts import _receipt
from test_reconciliation import seed_receipt


def evidence(setup, channel, opened):
    deps, _, _, _, canonical, *_ = setup
    scope = opened['scope']
    receipt = _receipt(channel.server_id, channel.executor_id, session_id=scope['session_id'],
        binding_id=scope['binding_id'], agent_id=scope['agent_id'], operation_id=opened['operation_id'],
        intent_hash=opened['intent_hash'], stage='SUCCEEDED', possible_effect=True, retry_safe=False,
        connection_id=channel.connection_id, connection_generation=channel.connection_generation)
    seed_receipt(deps.connection_factory, receipt)
    with deps.connection_factory.unit_of_work() as uow:
        uow.connection.execute("UPDATE execution_sessions SET lifecycle_state='READY',stream_epoch='epoch' WHERE session_id=?",
                               (scope['session_id'],))
        uow.connection.execute("INSERT INTO execution_event_watermarks(server_id,executor_id,session_id,stream_epoch,"
            "committed_contiguous,gap_state) VALUES (?,?,?,'epoch',2,'none')",
            (channel.server_id,channel.executor_id,scope['session_id']))
    count, digest = session_receipts_digest([receipt])
    request = dict(contract_revision=SESSION_RELEASE_REVISION, type='session.release', release_id='original-release',
        server_id=channel.server_id, executor_id=channel.executor_id, connection_id=channel.connection_id,
        connection_generation=channel.connection_generation, scope=scope, opening_operation_id=opened['operation_id'],
        opening_intent_hash=opened['intent_hash'], stream_epoch='epoch', sequence=2, receipt_count=count,
        receipt_digest=digest, proof_digest=r4_resource_release_digest(server_id=channel.server_id,
            executor_id=channel.executor_id,session_id=scope['session_id'],opening_operation_id=opened['operation_id'],
            opening_intent_hash=opened['intent_hash'], owner_generation=scope['session_owner_generation']))
    return request, receipt


@pytest.mark.parametrize('fault', [None,'proof','receipt_digest','missing_receipt','receipt_changed','stream_gap','stream_epoch',
                                 'owner','opening','scope','no_obligation','changed_during_validation','commit_failure'])
def test_live_release_requires_all_facts_and_keeps_executor_ready(tmp_path, monkeypatch, fault):
    with active_lease(tmp_path, monkeypatch, extra_capabilities=(SESSION_RELEASE_REVISION,)) as values:
        setup, ws, channel, opened, renewal = values
        deps, app, access, operator, canonical, *_ = setup
        original, receipt = evidence(setup, channel, opened)
        if fault != 'no_obligation':
            access.revoke(operator, grant_id=canonical['grant_id'])
            ws.send_text(encode_r4_frame(renewal).decode())
            assert ws.receive_json()['type'] == 'lease.denied'
        request = copy.deepcopy(original)
        if fault == 'proof': request['proof_digest'] = 'sha256:'+'f'*64
        if fault == 'receipt_digest': request['receipt_digest'] = 'sha256:'+'f'*64
        if fault == 'stream_epoch': request['stream_epoch'] = 'foreign'
        if fault == 'owner': request['scope']['session_owner_generation'] += 1
        if fault == 'opening': request['opening_operation_id'] = 'foreign'
        if fault == 'scope': request['scope']['agent_id'] = 'foreign'
        if fault == 'receipt_changed': seed_receipt(deps.connection_factory, dict(receipt, receipt_revision=2))
        if fault == 'changed_during_validation':
            from okto_nexus.adapters.outbound.sqlite.execution_session_release import SqliteSessionReleaseRepository
            original_observe = SqliteSessionReleaseRepository.observe
            def changing_observation(self, uow, request, channel):
                assert not uow._write
                observed = original_observe(self, uow, request, channel)
                # A real concurrent SQLite writer can progress during the full
                # history read. Its revision invalidates the final short commit.
                seed_receipt(deps.connection_factory, dict(receipt, receipt_revision=2))
                return observed
            monkeypatch.setattr(SqliteSessionReleaseRepository, 'observe', changing_observation)
        if fault == 'commit_failure':
            from okto_nexus.adapters.outbound.sqlite.execution_session_containment import SqliteSessionContainmentRepository
            original_complete = SqliteSessionContainmentRepository.complete_verified
            def fail_after_update(self, *args):
                original_complete(self, *args)
                raise RuntimeError('injected release commit failure')
            monkeypatch.setattr(SqliteSessionContainmentRepository, 'complete_verified', fail_after_update)
        with deps.connection_factory.unit_of_work() as uow:
            if fault == 'missing_receipt': uow.connection.execute('DELETE FROM execution_receipts')
            if fault == 'stream_gap': uow.connection.execute("UPDATE execution_event_watermarks SET gap_state='pending'")
        ws.send_text(encode_session_release(request).decode())
        reply = ws.receive_json()
        assert reply['type'] == ('session.release.accepted' if fault is None else 'session.release.deferred')
        assert reply['request'] == request
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT control_state FROM execution_executors WHERE executor_id=?',
                (channel.executor_id,)).fetchone()[0] == 'CONTROL_READY'
            assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions WHERE session_id=?',
                (opened['session_id'],)).fetchone()[0] == ('CLOSED' if fault is None else 'READY')
            row = uow.connection.execute('SELECT * FROM execution_session_containment').fetchone()
            if fault != 'no_obligation':
                assert row['state'] == ('RELEASED' if fault is None else 'REQUESTED')
                if fault is None: assert json.loads(row['release_proof_json'])['request'] == original
            assert not uow.connection.execute("SELECT 1 FROM execution_operations WHERE action='runtime.close'").fetchone()
        if fault is None:
            ws.send_text(encode_session_release(request).decode())
            assert ws.receive_json() == reply  # Lost ACK is idempotent.
            ws.send_text(encode_session_release(dict(request, release_id='replacement')).decode())
            assert ws.receive_json()['type'] == 'session.release.deferred'


def test_slow_session_history_does_not_block_another_sessions_lease(tmp_path, monkeypatch):
    from okto_nexus.adapters.outbound.sqlite import execution_session_release as adapter
    from okto_nexus.application.execution_intents import resolve_execution_intent
    from okto_nexus.application.execution_admission import submit_execution_operation
    from okto_nexus.domain.base import iso_plus
    with active_lease(tmp_path, monkeypatch, extra_capabilities=(SESSION_RELEASE_REVISION,)) as values:
        setup, ws, channel, opened, renewal = values
        deps, app, access, operator, canonical, *_ = setup
        request, _ = evidence(setup, channel, opened)
        access.revoke(operator, grant_id=canonical['grant_id'])
        ws.send_text(encode_r4_frame(renewal).decode())
        assert ws.receive_json()['type'] == 'lease.denied'
        other = resolve_execution_intent(deps.connection_factory, actor_agent_id='subject',
            request=dict(client_intent_id='sibling-open', intent='runtime.start', binding_id='binding',
                         workspace_binding_id='wxb', new_session=True), remote_ready=True,
            fresh_publications=app.state.inventory_fresh_publications)
        assert other['can_submit'], other['blockers']
        submit_execution_operation(deps.connection_factory, actor_agent_id='subject',
            request={k: other[k] for k in ('client_intent_id','operation_id','resolution_revision','intent_hash')},
            remote_ready=True, fresh_publications=app.state.inventory_fresh_publications)
        grant = access.issue(operator, actor_agent_id='subject', endpoint_id='ep',
            actions=['open','send','close','interrupt'], max_executions=2,
            expires_at=iso_plus(deps.clock.now_iso(), 600))
        healthy = dict(renewal, scope=other['scope'], request_id='healthy-request',
                       grant_id=grant['grant_id'], purpose='initial', expected_lease_serial=0)
        entered, release = threading.Event(), threading.Event()
        original_receipt = adapter._receipt
        def slow_receipt(row):
            entered.set()
            assert release.wait(10), 'The reader/SQLite writer blocked sibling lease issuance.'
            return original_receipt(row)
        monkeypatch.setattr(adapter, '_receipt', slow_receipt)
        try:
            ws.send_text(encode_session_release(request).decode())
            assert entered.wait(5)
            ws.send_text(encode_r4_frame(healthy).decode())
            reply = ws.receive_json()
            assert reply['type'] == 'lease.granted' and reply['scope'] == other['scope']
            assert not release.is_set()
        finally:
            release.set()
        assert ws.receive_json()['type'] == 'session.release.accepted'
