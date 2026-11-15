"""Accepted recovery without a direct release retains exact retirement evidence."""
import copy
import sqlite3
from dataclasses import replace

import pytest
from nexus_connector_core import CoreError, EventCursor, OperationKey, RuntimeEvent, SessionKey
from nexus_connector_core.models import OperationReceipt
from nexus_connector_core.process_launch import ProcessLaunchIdentity
from okto_nexus_connector.errors import ConnectorError
from okto_nexus_connector.services.core_host import CoreRuntimeHost
from okto_nexus_connector.services.r4_reconciliation import R4ReconciliationReporter
from okto_nexus_connector.services.r4_session_release import retire_reconciliation_checkpoint
from okto_nexus_connector.storage.r4_events import R4EventStore
from okto_nexus_connector.storage.r4_session_releases import R4SessionReleaseStore
from okto_nexus_connector.storage.state_store import ConnectorState, StateStore
from tests.unit.test_session_release_recovery import evidence, request


@pytest.fixture
async def checkpoint(tmp_path):
    original = request()
    ack, observations = evidence(original)
    opening = next(iter(observations.values()))['opening']
    state = StateStore(tmp_path/'state.json')
    state.save(ConnectorState(connector_id='connector'))
    host = CoreRuntimeHost(tmp_path,None)
    journal = await host.ensure_history_journal()
    key = SessionKey(opening['server_id'],opening['executor_id'],opening['session_id'])
    op = OperationKey(key.server_id,key.executor_id,opening['operation_id'])
    launch = ProcessLaunchIdentity(key,op.operation_id,opening['connection_generation'],
        opening['session_owner_generation'],'win32','windows_job',
        'Global\\nexus-core-'+'a'*32,'b'*32)
    await journal.admit(op,'intent',key.session_id,claim_session=True,effect_imminent=True,
        connection_generation=launch.connection_generation,session_owner_generation=launch.owner_generation,
        process_launch_identity=launch,action='runtime.open',terminal_event_expected=False)
    record = await journal.get_process_launch(key)
    for action in ('claim','fence','stop'):
        record = await journal.transition_process_launch(launch,expected_revision=record.revision,
            action=action,**({'stop_proof':'CONTAINER_STOPPED'} if action=='stop' else {}))
    await journal.record_receipt(op,OperationReceipt(op.operation_id,'intent','SUBMITTED',True,False,key.session_id))
    sequence = original['sequence']+1
    for index in range(1,sequence+1):
        await journal.append_event(RuntimeEvent(key.server_id,key.executor_id,key.session_id,
            opening['stream_epoch'],index,'lifecycle','fixture',{}))
    await journal.acknowledge_events(EventCursor(key.server_id,key.executor_id,key.session_id,opening['stream_epoch']),sequence)
    events = R4EventStore.for_state(state)
    events.register(opening)
    events.advance(opening,remote_acked=sequence)
    events.advance(opening,core_applied=sequence)
    outbox = R4SessionReleaseStore.for_state(state)
    reporter = R4ReconciliationReporter(state,host,key.server_id,key.executor_id)
    reporter.cycle = tuple(ack[k] for k in ('connection_id','connection_generation','reconcile_id'))
    reporter._report_complete = True
    reporter._release_observations = observations
    try:
        yield state,host,journal,key,original,ack,observations,outbox,reporter
    finally:
        if reporter._checkpoint_task is not None:
            await reporter._checkpoint_task
        await host.shutdown_all()


async def test_no_prior_release_retires_after_exact_accepted_cycle_and_replays(checkpoint):
    state,host,journal,key,original,ack,observations,outbox,reporter = checkpoint
    await reporter.accepted(ack)
    await reporter._checkpoint_task
    assert (await journal.claimed_sessions(key.server_id,key.executor_id,pending_only=True)).claims == ()
    assert await journal.get_session_claim(key) is not None
    with sqlite3.connect(outbox.path) as conn:
        assert conn.execute('SELECT count(*) FROM releases').fetchone()[0] == 0
        first = conn.execute('SELECT proof,digest,retired FROM reconciliation_checkpoints').fetchone()
    assert first[2] == 1
    await reporter.accepted(ack)
    await reporter._checkpoint_task
    with sqlite3.connect(outbox.path) as conn:
        assert conn.execute('SELECT proof,digest,retired FROM reconciliation_checkpoints').fetchone() == first
    assert R4EventStore.for_state(state).page(key.server_id,key.executor_id)[0] == []
    assert R4SessionReleaseStore(outbox.path).reconciliation_checkpoint_page(key.server_id,key.executor_id) == []


@pytest.mark.parametrize('retired',[False,True])
async def test_accepted_reconciliation_fences_late_direct_release(checkpoint,retired):
    state,_,journal,key,original,ack,observations,outbox,_ = checkpoint
    outbox.record_reconciliation_checkpoints(ack,observations)
    if retired:
        _,proof,digest=outbox.reconciliation_checkpoint_page(key.server_id,key.executor_id)[0]
        await retire_reconciliation_checkpoint(state,proof,digest,journal)
    with pytest.raises(ConnectorError,match='STALE_GENERATION'):
        outbox.prepare(original)
    with sqlite3.connect(outbox.path) as conn:
        assert conn.execute('SELECT count(*) FROM releases').fetchone()[0]==0


async def test_direct_release_winning_transaction_keeps_original_path(checkpoint):
    _,_,_,key,original,ack,observations,outbox,_ = checkpoint
    outbox.prepare(original)
    outbox.reconcile_page(ack,observations)
    outbox.record_reconciliation_checkpoints(ack,observations)
    assert outbox.reconciliation_checkpoint_page(key.server_id,key.executor_id)==[]
    assert outbox.resolved_checkpoint_page(key.server_id,key.executor_id)[0][1]==original


async def test_next_report_cannot_lend_its_facts_to_prior_ack(checkpoint,monkeypatch):
    _,_,journal,key,_,ack,observations,outbox,reporter=checkpoint
    original=outbox.reconcile_page
    # This worker boundary represents a new report arriving during accepted().
    def next_cycle(*args,**kwargs):
        reporter._release_observations=copy.deepcopy(observations)
        next(iter(reporter._release_observations.values()))['watermark']['stream_epoch']='next-epoch'
        return original(*args,**kwargs)
    monkeypatch.setattr(reporter.release_outbox,'reconcile_page',next_cycle)
    await reporter.accepted(ack)
    await reporter._checkpoint_task
    assert (await journal.claimed_sessions(key.server_id,key.executor_id,pending_only=True)).claims==()
    with sqlite3.connect(outbox.path) as conn:
        raw=conn.execute('SELECT proof FROM reconciliation_checkpoints').fetchone()[0]
    import json
    assert json.loads(raw)['observation']==next(iter(observations.values()))


@pytest.mark.parametrize('cut',['cycle','generation','cursor','incomplete','blocked'])
async def test_unaccepted_cycle_never_creates_checkpoint(checkpoint,cut):
    _,_,journal,key,_,ack,_,outbox,reporter = checkpoint
    ack = dict(ack)
    if cut=='cycle': ack['reconcile_id']='other'
    elif cut=='generation': ack['connection_generation']+=1
    elif cut=='cursor': reporter.cursor='page-pending'
    elif cut=='incomplete': reporter._report_complete=False
    else: reporter.blocked=True
    with pytest.raises(ConnectorError,match='RECONCILIATION_REQUIRED'):
        await reporter.accepted(ack)
    assert len((await journal.claimed_sessions(key.server_id,key.executor_id,pending_only=True)).claims)==1
    assert outbox.reconciliation_checkpoint_page(key.server_id,key.executor_id)==[]


@pytest.mark.parametrize('cut',['epoch','owner','state','watermark','server'])
async def test_changed_observation_is_not_a_release_proof(checkpoint,cut):
    _,_,_,key,_,ack,observations,outbox,_ = checkpoint
    changed=copy.deepcopy(observations)
    observation=next(iter(changed.values()))
    if cut=='epoch': observation['watermark']['stream_epoch']='other'
    elif cut=='owner': observation['claim']['owner_generation']+=1
    elif cut=='state': observation['fact']['process_state']='UNKNOWN'
    elif cut=='watermark': observation['watermark']['sequence']=True
    else: observation['opening']['server_id']='other'
    with pytest.raises(ConnectorError):
        outbox.record_reconciliation_checkpoints(ack,changed)
    assert outbox.reconciliation_checkpoint_page(key.server_id,key.executor_id)==[]


@pytest.mark.parametrize('cut',['unfenced','unproven','new_owner','new_opening','new_event'])
async def test_current_owner_or_watermark_change_keeps_claim_unknown(checkpoint,monkeypatch,cut):
    state,_,journal,key,_,ack,observations,outbox,_ = checkpoint
    outbox.record_reconciliation_checkpoints(ack,observations)
    _,proof,digest=outbox.reconciliation_checkpoint_page(key.server_id,key.executor_id)[0]
    if cut in ('unfenced','unproven'):
        launch=await journal.get_process_launch(key)
        async def changed(_):
            return replace(launch,**({'producer_fenced':False} if cut=='unfenced' else {'stop_proof':None}))
        monkeypatch.setattr(journal,'get_process_launch',changed)
    elif cut in ('new_owner','new_opening'):
        claim=await journal.get_session_claim(key)
        async def changed(_):
            return replace(claim,**({'opening_owner_generation':claim.opening_owner_generation+1}
                if cut=='new_owner' else {'opening_operation_id':'new-opening'}))
        monkeypatch.setattr(journal,'get_session_claim',changed)
    else:
        opening=proof['observation']['opening']
        await journal.append_event(RuntimeEvent(key.server_id,key.executor_id,key.session_id,
            opening['stream_epoch'],original_sequence(proof)+1,'lifecycle','late',{}))
    with pytest.raises(CoreError,match='RECONCILIATION_REQUIRED'):
        await retire_reconciliation_checkpoint(state,proof,digest,journal)
    assert len((await journal.claimed_sessions(key.server_id,key.executor_id,pending_only=True)).claims)==1
    assert len(outbox.reconciliation_checkpoint_page(key.server_id,key.executor_id))==1


def original_sequence(proof):
    return proof['observation']['watermark']['sequence']


@pytest.mark.parametrize('cut',['claim','marker'])
async def test_crash_between_stores_reopens_and_retries_exact_proof(checkpoint,monkeypatch,cut):
    state,_,journal,key,_,ack,observations,outbox,_ = checkpoint
    outbox.record_reconciliation_checkpoints(ack,observations)
    _,proof,digest=outbox.reconciliation_checkpoint_page(key.server_id,key.executor_id)[0]
    if cut=='claim':
        original=journal.retire_reconciliation_claim
        async def interrupted(*args,**kwargs):
            raise OSError('Injected before claim retirement')
        monkeypatch.setattr(journal,'retire_reconciliation_claim',interrupted)
    else:
        original=R4SessionReleaseStore.mark_reconciliation_checkpoint_retired
        def interrupted(*args,**kwargs):
            raise OSError('Injected before marker commit')
        monkeypatch.setattr(R4SessionReleaseStore,'mark_reconciliation_checkpoint_retired',interrupted)
    with pytest.raises(OSError):
        await retire_reconciliation_checkpoint(state,proof,digest,journal)
    if cut=='claim': monkeypatch.setattr(journal,'retire_reconciliation_claim',original)
    else: monkeypatch.setattr(R4SessionReleaseStore,'mark_reconciliation_checkpoint_retired',original)
    _,retained,retained_digest=R4SessionReleaseStore(outbox.path).reconciliation_checkpoint_page(key.server_id,key.executor_id)[0]
    assert (retained,retained_digest)==(proof,digest)
    await retire_reconciliation_checkpoint(state,retained,retained_digest,journal)
    assert (await journal.claimed_sessions(key.server_id,key.executor_id,pending_only=True)).claims==()
    assert outbox.reconciliation_checkpoint_page(key.server_id,key.executor_id)==[]
