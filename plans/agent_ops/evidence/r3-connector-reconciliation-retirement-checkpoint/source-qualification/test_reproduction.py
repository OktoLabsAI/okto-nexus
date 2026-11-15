"""Offline reproduction using actual storage/reporter, synthetic authenticated ACK."""
import asyncio
import pytest
from nexus_connector_core import OperationKey
from okto_nexus_connector.services.core_host import CoreRuntimeHost
from okto_nexus_connector.services.r4_reconciliation import R4ReconciliationReporter
from okto_nexus_connector.storage.r4_session_releases import R4SessionReleaseStore
from okto_nexus_connector.storage.r4_events import R4EventStore
from okto_nexus_connector.storage.state_store import StateStore, ConnectorState
from tests.unit.test_session_release_recovery import evidence, request

@pytest.mark.parametrize('prior_release_row',[False,True])
async def test_accepted_reconciliation_depends_on_prior_release_row(tmp_path,prior_release_row):
    original=request(); ack,observations=evidence(original)
    state=StateStore(tmp_path/'state.json'); state.save(ConnectorState(connector_id='connector'))
    outbox=R4SessionReleaseStore.for_state(state)
    if prior_release_row: outbox.prepare(original)
    events=R4EventStore.for_state(state)
    scope={**original['scope'],'stream_epoch':original['stream_epoch']}
    events.register(scope)
    sequence=original['sequence']+1
    events.advance(scope,remote_acked=sequence); events.advance(scope,core_applied=sequence)
    host=CoreRuntimeHost(tmp_path,None)
    try:
        journal=await host.ensure_history_journal()
        await journal.admit(OperationKey(original['server_id'],original['executor_id'],
            original['opening_operation_id']),'intent',original['scope']['session_id'],claim_session=True)
        reporter=R4ReconciliationReporter(state,host,original['server_id'],original['executor_id'])
        reporter.cycle=tuple(ack[k] for k in ('connection_id','connection_generation','reconcile_id'))
        reporter._report_complete=True
        reporter._release_observations=observations
        await reporter.accepted(ack)
        await asyncio.wait_for(reporter._checkpoint_task,3)
        pending=(await journal.claimed_sessions(original['server_id'],original['executor_id'],pending_only=True)).claims
        assert len(pending)==(0 if prior_release_row else 1)
        assert outbox.resolved_checkpoint_page(original['server_id'],original['executor_id'])==[]
    finally:
        await host.shutdown_all()
