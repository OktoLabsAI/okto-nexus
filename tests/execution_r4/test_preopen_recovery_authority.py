"""A remote preopening proof requires exact admission and replacement owner."""
import asyncio
from contextlib import contextmanager

import pytest
from starlette.testclient import TestClient
from nexus_connector_core import OperationKey, R4_PREVIEW_REVISION, encode_r4_frame, project_r4_bound_receipt
from nexus_connector_core.journal import open_journal
from nexus_connector_core.preopen_refusal_r4 import prepare_r4_preopen_refusal, persist_r4_preopen_refusal

from okto_nexus.adapters.outbound.sqlite.execution_preopen_recovery import SqlitePreopenRecoveryRepository
from okto_nexus.application.execution_preopen_recovery import ExecutionPreopenRecovery
from okto_nexus.application.execution_dispatch import reserve_execution_dispatch, begin_execution_send
from okto_nexus.application.execution_leases import ExecutionChannel
from okto_nexus.errors import OktoNexusError
from test_ns09 import setup_authority, negotiate, admit


@contextmanager
def recovery(tmp_path, monkeypatch):
    deps, app, access, _, _, _, info, revisions, link_ticket, lane_ticket, server_id, executor_id = setup_authority(tmp_path, monkeypatch)
    path = f'wss://127.0.0.1:8202/v1/runtime/executors/{executor_id}/link'
    with TestClient(app, base_url='https://127.0.0.1:8202') as client:
        with client.websocket_connect(path, headers={'Authorization': f'Bearer {link_ticket}'}, subprotocols=['nxl.v1']) as ws:
            negotiate(ws, info, revisions, lane_ticket, server_id, executor_id)
            resolved = admit(deps, app)
            reserved = reserve_execution_dispatch(deps.connection_factory, server_id=server_id,
                                                   executor_id=executor_id, remote_ready=True)
            original = begin_execution_send(deps.connection_factory, reservation=reserved, remote_ready=True,
                fresh_publications=app.state.inventory_fresh_publications, access=access).frame
        with client.websocket_connect(path, headers={'Authorization': f'Bearer {link_ticket}'}, subprotocols=['nxl.v1']) as ws:
            base = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, server_id=server_id, executor_id=executor_id)
            ws.send_text(encode_r4_frame(dict(base, type='hello', link_attempt_id='replacement', core_version=info['core_version'],
                management_revision=info['management_revision'], supported_nxl=[R4_PREVIEW_REVISION],
                snapshot_formats=[info['executor_snapshot_format']], control_capabilities=['nexus-preopen-refusal-v1'])).decode())
            welcome = ws.receive_json()
            assert welcome['type'] == 'welcome'
            request = ws.receive_json()
            assert request['preopen_refusal_supported'] is True
            channel = ExecutionChannel(server_id, executor_id, welcome['connection_id'], welcome['connection_generation'])
            yield deps, original, resolved, channel, request, ws


def report_for(original, channel, tmp_path, *, change=None):
    source = {k: original[k] for k in ('protocol_major', 'contract_revision', 'server_id', 'executor_id',
        'binding_id', 'agent_id', 'session_id', 'connection_id', 'connection_generation', 'operation_id', 'intent_hash')}
    generation = original['session_owner_generation']
    if change == 'connection': source['connection_id'] = 'unrelated-original'
    elif change == 'session': source['session_id'] = 'unrelated-session'
    elif change == 'operation': source['operation_id'] = 'unrelated-operation'
    elif change == 'hash': source['intent_hash'] = 'sha256:' + 'f' * 64
    elif change == 'owner': generation += 1
    refusal = prepare_r4_preopen_refusal(source, session_owner_generation=generation,
        recovery=dict(connection_id=channel.connection_id, connection_generation=channel.connection_generation))
    async def persist():
        journal = await open_journal(tmp_path / ('proof-' + str(change) + '.db'))
        try:
            fact = await persist_r4_preopen_refusal(journal, refusal)
            return project_r4_bound_receipt(refusal['binding'], fact,
                key=OperationKey(source['server_id'], source['executor_id'], source['operation_id']), receipt_revision=1)
        finally:
            await journal.aclose()
    return dict(refusal=refusal, receipt=asyncio.run(persist()), capacity=None, slot=None)


@pytest.mark.parametrize('change', ['connection', 'session', 'operation', 'hash', 'owner', 'current_owner', 'existing_receipt'])
def test_preopen_recovery_rejects_forged_admission_or_current_control_scope(tmp_path, monkeypatch, change):
    with recovery(tmp_path, monkeypatch) as (deps, original, _, channel, _, _):
        report = report_for(original, channel, tmp_path, change=change)
        if change == 'existing_receipt':
            from test_reconciliation import seed_receipt
            seed_receipt(deps.connection_factory, dict(report['receipt'], stage='OUTCOME_UNKNOWN',
                possible_effect=True, retry_safe=False, error_code='OUTCOME_UNKNOWN'))
        if change == 'current_owner':
            channel = ExecutionChannel(channel.server_id, channel.executor_id, 'foreign-current', channel.connection_generation)
        service = ExecutionPreopenRecovery(SqlitePreopenRecoveryRepository())
        with pytest.raises((OktoNexusError, ValueError)):
            with deps.connection_factory.unit_of_work() as uow:
                service.accept(uow, channel, [report])
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT count(*) FROM execution_preopen_refusals').fetchone()[0] == 0
            assert uow.connection.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == int(change == 'existing_receipt')
            if change == 'existing_receipt':
                assert tuple(uow.connection.execute('SELECT stage,possible_effect,retry_safe FROM execution_receipts').fetchone()) == ('OUTCOME_UNKNOWN', 1, 0)
            assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions').fetchone()[0] == 'OPEN_PENDING'


def test_preopen_extension_requires_explicit_negotiation(tmp_path, monkeypatch):
    from okto_nexus.application.execution_reconciliation import ExecutionReconciliation
    with recovery(tmp_path, monkeypatch) as (deps, original, _, channel, _, _):
        item = report_for(original, channel, tmp_path)
        unnegotiated = ExecutionReconciliation(deps.connection_factory, channel)
        request = unnegotiated.request()
        report = {k: request[k] for k in ('protocol_major', 'contract_revision', 'server_id', 'executor_id',
            'connection_id', 'connection_generation', 'reconcile_id', 'cursor')} | dict(type='reconcile.report',
            next_cursor=None, complete=True, receipts=[], claims=[], ownership_facts=[], stream_watermarks=[], preopen_refusals=[item])
        with pytest.raises(ValueError, match='not negotiated'):
            unnegotiated.accept(report)
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT count(*) FROM execution_preopen_refusals').fetchone()[0] == 0


@pytest.mark.parametrize('cut', ['rollback', 'lost_reply'])
def test_preopen_receipt_and_session_close_commit_together_and_replay(tmp_path, monkeypatch, cut):
    from okto_nexus.adapters.outbound.sqlite import execution_preopen_recovery as adapter
    with recovery(tmp_path, monkeypatch) as (deps, original, _, channel, _, _):
        report = report_for(original, channel, tmp_path)
        service = ExecutionPreopenRecovery(SqlitePreopenRecoveryRepository())
        if cut == 'rollback':
            original_finish = adapter.finish_preopen_recovery
            def interrupted(*args):
                original_finish(*args)
                raise OSError('Synthetic failure after receipt and closure writes')
            with monkeypatch.context() as patch:
                patch.setattr(adapter, 'finish_preopen_recovery', interrupted)
                with pytest.raises(OSError):
                    with deps.connection_factory.unit_of_work() as uow:
                        service.accept(uow, channel, [report])
            with deps.connection_factory.unit_of_work(write=False) as uow:
                assert uow.connection.execute('SELECT count(*) FROM execution_preopen_refusals').fetchone()[0] == 0
                assert uow.connection.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == 0
                assert uow.connection.execute('SELECT lifecycle_state FROM execution_sessions').fetchone()[0] == 'OPEN_PENDING'
        else:
            with deps.connection_factory.unit_of_work() as uow:
                service.accept(uow, channel, [report])
        with deps.connection_factory.unit_of_work() as uow:
            service.accept(uow, channel, [report])
        with deps.connection_factory.unit_of_work(write=False) as uow:
            assert uow.connection.execute('SELECT count(*) FROM execution_preopen_refusals').fetchone()[0] == 1
            assert uow.connection.execute('SELECT count(*) FROM execution_receipts').fetchone()[0] == 1
            assert tuple(uow.connection.execute('SELECT lifecycle_state,lease_state FROM execution_sessions').fetchone()) == ('CLOSED', 'CLOSED')
