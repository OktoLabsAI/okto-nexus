"""Restart from retained initial-denial facts without opening a provider."""
from contextlib import contextmanager
import json
import threading

import pytest
from fastapi.testclient import TestClient

from okto_nexus.bootstrap import embedded_initial_refusal as refusal
from okto_nexus.bootstrap.capacity_admission import build_capacity_admission
from okto_nexus.bootstrap.handoff_runtime_attempts import build_handoff_runtime_attempts
from okto_nexus.bootstrap.handoff_runtime_scheduler import build_handoff_runtime_candidates
from test_embedded_dispatch import local_setup, qualified_contract, wait_receipt
from test_embedded_inventory import app_for
from test_canonical_delivery import connected_local
from test_canonical_handoff_regressions import runtime
from test_harness_canonical import qualified_bridge
from test_handoff_automation_principal import prepare
from test_handoff_runtime_candidates import enable_capacity, lease
from test_one_shot_runtime import query, wait_until
from test_sender_sessions import Peers, configure, complete


@contextmanager
def restart_client(app):
    with TestClient(app) as client:
        try:
            yield client
        except BaseException:
            # On a regression preserve the failing evidence, rather than let
            # graceful publication retry indefinitely and hide the assertion.
            async def retain_failed_history():
                pass
            app.state.embedded_dispatch_owner._publish_shutdown_history = retain_failed_history
            raise


@pytest.mark.parametrize('cut', ['denial_before', 'denial_before_release_after', 'denial_after',
                                 'core_before', 'core_after', 'publish_after'])
def test_restart_recovers_initial_refusal_without_native_execution(tmp_path, monkeypatch, cut):
    peers = Peers()
    hit = threading.Event()
    with monkeypatch.context() as patch:
        with contextmanager(local_setup.__wrapped__)(tmp_path, monkeypatch, None) as setup:
            rt = runtime.__wrapped__(connected_local.__wrapped__(setup), monkeypatch)
            setup, binding, _ = rt
            deps, app, client, headers, *_ = setup
            owner = app.state.embedded_dispatch_owner
            owner.native_factory = peers
            configure(setup, binding, 'one_shot')
            _, hid, _ = prepare(rt)
            enable_capacity(rt)
            page = build_handoff_runtime_candidates(deps).prepare_page(lease(rt, hid), limit=4)
            assert len(page.attempt_ids) == 1
            attempts = build_handoff_runtime_attempts(deps)
            aid = page.attempt_ids[0]
            assert client.portal.call(attempts.reserve, aid).state == 'RESERVED'
            committed = attempts.claim(aid)
            sid = committed.request.scope.session_id
            with deps.connection_factory.unit_of_work() as uow:
                uow.connection.execute('UPDATE one_shot_calls SET admission_deadline=0')
            if cut.startswith('denial_before'):
                original_record = owner.access.session_containment.repository.record
                def rollback_denial(*args, **kwargs):
                    original_record(*args, **kwargs)
                    hit.set()
                    raise OSError('Rollback initial-denial commit until restart')
                patch.setattr(owner.access.session_containment.repository, 'record', rollback_denial)
            elif cut == 'denial_after':
                original_denied = owner.access.session_containment.denied
                def lost_denial_reply(*args, **kwargs):
                    original_denied(*args, **kwargs)
                    hit.set()
                    raise OSError('Lost committed initial-denial result until restart')
                patch.setattr(owner.access.session_containment, 'denied', lost_denial_reply)
            elif cut.startswith('core'):
                original = refusal.persist_r4_lease_refusal
                async def fault(journal, proof):
                    if cut == 'core_after':
                        await original(journal, proof)
                    hit.set()
                    raise OSError('Retained initial-refusal crash boundary')
                patch.setattr(refusal, 'persist_r4_lease_refusal', fault)
            else:
                original_publish = owner._publish
                async def fault_publish(binding, receipt):
                    await original_publish(binding, receipt)
                    if receipt.error_code == 'LEASE_REVALIDATION_REQUIRED':
                        hit.set()
                        raise OSError('Lost initial-refusal publication result')
                patch.setattr(owner, '_publish', fault_publish)
            # Model process exit before the final history publication. Actual
            # journals and capacity ledgers are retained and closed normally.
            async def exit_before_publication():
                assert not peers.sessions
            patch.setattr(owner, '_publish_shutdown_history', exit_before_publication)
            client.portal.call(build_capacity_admission(deps).consume, committed.operation_id)
            wait_until(setup, hit.is_set)
            assert not peers.sessions
            assert owner.failure is None and not owner.agents.blocked
            original_generation = owner.channel.connection_generation
            operation_ids = query(setup, 'SELECT operation_id FROM execution_operations ORDER BY operation_id')
            assert query(setup, 'SELECT count(*) FROM execution_local_publications')[0][0] == int(not cut.startswith('denial_'))
    deps, app = app_for(tmp_path / 'home')
    release_retries = []
    if cut == 'denial_before_release_after':
        from okto_nexus.application.execution_preopen_capacity import ExecutionPreopenCapacity
        original_release = ExecutionPreopenCapacity.release
        async def lost_release_reply(service, **kwargs):
            await original_release(service, **kwargs)
            release_retries.append(kwargs)
            if len(release_retries) == 1:
                raise OSError('Lost pre-open physical release result before session retirement')
        monkeypatch.setattr(ExecutionPreopenCapacity, 'release', lost_release_reply)
    # Enable the real serve-owned acquisition loop for post-restart work.
    # Cleanup-only mode intentionally cancels manually introduced candidates.
    deps.config.runtime_handoff_auto_claim_enabled = True
    with restart_client(app) as client:
        restarted = deps, app, client, headers
        owner = app.state.embedded_dispatch_owner
        wait_until(restarted, lambda: not query(restarted, 'SELECT * FROM one_shot_slots'))

        wait_until(restarted, lambda: not owner.agents.blocked)
        assert owner.channel.connection_generation > original_generation
        assert owner.failure is None and owner.recovery_failure is None
        assert not owner.host._runtime_tasks and not peers.sessions
        assert query(restarted, 'SELECT operation_id FROM execution_operations ORDER BY operation_id') == operation_ids
        assert query(restarted, 'SELECT count(*) FROM handoff_runtime_attempts')[0][0] == 1
        assert query(restarted, 'SELECT count(*) FROM execution_capacity_admissions')[0][0] == 1
        expected_claim = 'CLAIMED' if cut.startswith('denial_before') else 'OPEN'
        assert query(restarted, 'SELECT status,claim_epoch FROM handoffs WHERE handoff_id=?', (hid,))[0][:] == (expected_claim, 1)
        expected_lifecycle = 'FAILED' if cut.startswith('denial_before') else 'CLOSED'
        assert query(restarted, 'SELECT lifecycle_state,lease_state FROM execution_sessions WHERE session_id=?', (sid,))[0][:] == (expected_lifecycle, 'CLOSED')
        if cut.startswith('denial_before'):
            assert not query(restarted, 'SELECT * FROM execution_session_containment')
            assert not query(restarted, 'SELECT * FROM execution_receipts')
        else:
            assert query(restarted, 'SELECT state FROM execution_session_containment')[0][0] == 'RELEASED'
            assert query(restarted, 'SELECT stage,error_code,possible_effect,retry_safe FROM execution_receipts')[0][:] == ('FAILED', 'LEASE_REVALIDATION_REQUIRED', 0, 1)
            assert query(restarted, 'SELECT state,active FROM handoff_runtime_attempts WHERE handoff_id=?', (hid,))[0][:] == ('FAILED_NO_EFFECT', 0)
            assert query(restarted, 'SELECT failure_count FROM handoff_runtime_no_effect_retries WHERE handoff_id=?', (hid,))[0][0] == 1
        assert query(restarted, 'SELECT count(*) FROM execution_local_streams')[0][0] == 0
        # No native stream existed. Retire only the separately proven refusal,
        # so a later boot need not reopen this already verified history.
        wait_until(restarted, lambda: query(restarted,
            'SELECT local_retirement_json FROM execution_sessions WHERE session_id=?', (sid,))[0][0] is not None)
        checkpoint = json.loads(query(restarted,
            'SELECT local_retirement_json FROM execution_sessions WHERE session_id=?', (sid,))[0][0])
        assert checkpoint['release_kind'] == 'no_native_admission'
        assert checkpoint['evidence_kind'] == ('dispatch_refusal' if cut.startswith('denial_before') else 'initial_lease_refusal')
        assert 'stream_epoch' not in checkpoint and 'process_state' not in checkpoint
        if cut == 'denial_before_release_after':
            assert len(release_retries) >= 2
            assert all(value == release_retries[0] for value in release_retries)
        # Readiness must allow new work with fresh authority, without replaying
        # the original failed operation or requiring an operator recovery action.
        owner.native_factory = peers
        client.headers['host'] = '127.0.0.1:8000'
        rt = restarted, binding, peers
        _, next_hid, _ = prepare(rt)
        enable_capacity(rt)
        wait_until(restarted, lambda: bool(query(restarted, 'SELECT 1 FROM handoff_runtime_attempts '
            'WHERE handoff_id=? AND operation_id IS NOT NULL', (next_hid,))))
        next_aid = query(restarted, 'SELECT attempt_id FROM handoff_runtime_attempts '
            'WHERE handoff_id=? AND operation_id IS NOT NULL', (next_hid,))[0][0]
        next_attempt = build_handoff_runtime_attempts(deps).get(next_aid)
        turn = dict(query(restarted, "SELECT operation_id,session_id FROM execution_operations "
            "WHERE action='turn.submit' AND session_id=?", (next_attempt.request.scope.session_id,))[0])
        wait_receipt(restarted, turn)
        assert turn['session_id'] != sid
        assert len(peers.sessions) == 1 and len(peers.sessions[turn['session_id']].sent) == 1
        complete(restarted, peers, turn, 'Fresh work after initial refusal recovery')
        wait_until(restarted, lambda: not query(restarted, 'SELECT * FROM one_shot_slots'))

    if cut in ('denial_before', 'publish_after'):
        # A second boot must consume the checkpoint, not reopen the original
        # no-stream journal and repeat its evidence work indefinitely.
        from okto_nexus.bootstrap import runtime_host
        old_path = owner.host._journal_path(owner.channel.executor_id, sid)
        original_open = runtime_host.open_journal
        reopened = []
        async def observe_open(path):
            if path == old_path:
                reopened.append(path)
            return await original_open(path)
        monkeypatch.setattr(runtime_host, 'open_journal', observe_open)
        next_deps, next_app = app_for(tmp_path / 'home')
        with restart_client(next_app) as next_client:
            next_setup = next_deps, next_app, next_client, headers
            next_owner = next_app.state.embedded_dispatch_owner
            wait_until(next_setup, lambda: next_owner.agents.initialized and not next_owner.agents.blocked)
            assert not reopened
            assert json.loads(query(next_setup, 'SELECT local_retirement_json FROM execution_sessions '
                'WHERE session_id=?', (sid,))[0][0]) == checkpoint
