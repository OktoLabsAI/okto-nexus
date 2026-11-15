"""Only accepted original opening/ownership facts retire old-channel reports."""
import copy
import asyncio
import json
import sqlite3
from hashlib import sha256

import pytest
from nexus_connector_core import R4_PREVIEW_REVISION
from nexus_connector_core.session_release import encode_session_release,session_release_accepted
from okto_nexus_connector.errors import ConnectorError
from okto_nexus_connector.storage.r4_session_releases import R4SessionReleaseStore
from tests.contract.test_session_release import request
from tests.unit.test_session_release_outbox import identity


def evidence(original):
    scope = original['scope']
    ack = dict(protocol_major=1, contract_revision=R4_PREVIEW_REVISION, type='reconcile.accepted',
        server_id=original['server_id'], executor_id=original['executor_id'], connection_id='replacement',
        connection_generation=original['connection_generation'] + 1, reconcile_id='accepted-cycle',
        recovery_remaining=False, ready_lane_ids=[], session_lease_requirements=[])
    opening = {k: original[k] for k in ('server_id','executor_id','connection_id','connection_generation','stream_epoch')}
    opening.update({k: scope[k] for k in ('binding_id','agent_id','session_id','session_owner_generation')})
    opening.update(operation_id=original['opening_operation_id'], intent_hash=original['opening_intent_hash'])
    key = dict(session_id=scope['session_id'], owner_generation=scope['session_owner_generation'])
    observation = dict(opening=opening, claim=dict(**key, state='RELEASED'),
        fact=dict(**key, process_state='EXITED', proof_digest=original['proof_digest']),
        watermark=dict(session_id=scope['session_id'], stream_epoch=original['stream_epoch'], sequence=original['sequence'] + 1))
    return ack, {(scope['session_id'],scope['session_owner_generation']): observation}


def test_recovery_keeps_original_bytes_and_separate_authenticated_proof(tmp_path):
    original = request()
    outbox = R4SessionReleaseStore(tmp_path / 'releases.sqlite3')
    outbox.prepare(original)
    ack, observations = evidence(original)
    assert outbox.reconcile_page(ack, observations) is None
    rebuilt = R4SessionReleaseStore(outbox.path)
    assert rebuilt.pending(**identity(original)) is None
    assert rebuilt.reconcile_page(ack, observations) is None
    with pytest.raises(ConnectorError, match='STALE_GENERATION'):
        rebuilt.prepare(original)
    with pytest.raises(ConnectorError, match='STALE_GENERATION'):
        rebuilt.prepare(dict(original, release_id='another-observation', sequence=original['sequence'] + 1))
    with sqlite3.connect(outbox.path) as conn:
        raw, proof, state = conn.execute('SELECT request,recovery,state FROM releases').fetchone()
    assert raw == encode_session_release(original) and state == 'PENDING'
    assert json.loads(proof)['ack'] == ack
    # The original request never acquires the replacement generation or a
    # fabricated live-session ACK. Resolution has its own recorded provenance.
    assert json.loads(raw)['connection_generation'] < ack['connection_generation']
    checkpoint=rebuilt.resolved_checkpoint_page(original['server_id'],original['executor_id'])
    assert len(checkpoint)==1 and checkpoint[0][1:3]==(
        original,original['sequence']+1)
    assert checkpoint[0][3]==sha256(proof).hexdigest()


async def test_reconciled_release_checkpoints_in_background_without_delaying_ready(tmp_path,monkeypatch):
    from nexus_connector_core import OperationKey,SessionKey
    from okto_nexus_connector.services.core_host import CoreRuntimeHost
    from okto_nexus_connector.services.r4_reconciliation import R4ReconciliationReporter
    from okto_nexus_connector.storage.r4_events import R4EventStore
    from okto_nexus_connector.storage.state_store import StateStore,ConnectorState

    original=request()
    ack,observations=evidence(original)
    state=StateStore(tmp_path/'state.json')
    state.save(ConnectorState(connector_id='connector'))
    outbox=R4SessionReleaseStore.for_state(state)
    outbox.prepare(original)
    events=R4EventStore.for_state(state)
    scope={**original['scope'],'stream_epoch':original['stream_epoch']}
    events.register(scope)
    sequence=original['sequence']+1
    events.advance(scope,remote_acked=sequence)
    events.advance(scope,core_applied=sequence)
    host=CoreRuntimeHost(tmp_path,None)
    try:
        journal=await host.ensure_history_journal()
        await journal.admit(OperationKey(original['server_id'],original['executor_id'],
                            original['opening_operation_id']),'intent',
                            original['scope']['session_id'],claim_session=True)
        entered,release=asyncio.Event(),asyncio.Event()
        retire=journal.retire_reconciliation_claim
        async def delayed(*args,**kwargs):
            entered.set()
            await release.wait()
            return await retire(*args,**kwargs)
        monkeypatch.setattr(journal,'retire_reconciliation_claim',delayed)
        reporter=R4ReconciliationReporter(state,host,original['server_id'],original['executor_id'])
        reporter.cycle=tuple(ack[k] for k in ('connection_id','connection_generation','reconcile_id'))
        reporter._report_complete=True
        reporter._release_observations=observations
        await reporter.accepted(ack)
        await asyncio.wait_for(entered.wait(),2)
        assert reporter._checkpoint_task is not None and not reporter._checkpoint_task.done()
        task=reporter._checkpoint_task
        await reporter.accepted(ack)
        assert reporter._checkpoint_task is task and reporter._checkpoint_epoch==2
        assert len(outbox.resolved_checkpoint_page(original['server_id'],original['executor_id']))==1
        release.set()
        await asyncio.wait_for(reporter._checkpoint_task,3)
        assert outbox.resolved_checkpoint_page(original['server_id'],original['executor_id'])==[]
        assert events.page(original['server_id'],original['executor_id'])[0]==[]
        assert events.read(scope)['remote_acked']==events.read(scope)['core_applied']==sequence
        assert (await journal.claimed_sessions(original['server_id'],original['executor_id'],
                                              pending_only=True)).claims==()
        assert await journal.get_session_claim(SessionKey(original['server_id'],
            original['executor_id'],original['scope']['session_id'])) is not None
    finally:
        release.set()
        await host.shutdown_all()


@pytest.mark.parametrize('tamper', ['server','generation','connection','opening','owner','stream','sequence','claim','agent','opening_channel','absent'])
def test_ready_channel_without_matching_release_evidence_preserves_pending(tmp_path, tamper):
    original = request()
    outbox = R4SessionReleaseStore(tmp_path / 'releases.sqlite3')
    outbox.prepare(original)
    ack, observations = evidence(original)
    observation = next(iter(observations.values()))
    if tamper == 'server': ack['server_id'] = 'another'
    elif tamper == 'generation': ack['connection_generation'] = original['connection_generation']
    elif tamper == 'connection': ack['connection_id'] = original['connection_id']
    elif tamper == 'opening': observation['opening']['operation_id'] = 'another'
    elif tamper == 'owner': observation['claim']['owner_generation'] += 1
    elif tamper == 'stream': observation['watermark']['stream_epoch'] = 'another'
    elif tamper == 'sequence': observation['watermark']['sequence'] = original['sequence'] - 1
    elif tamper == 'claim': observation['claim']['state'] = 'UNKNOWN'
    elif tamper == 'agent': observation['opening']['agent_id'] = 'another'
    elif tamper == 'opening_channel': observation['opening']['connection_id'] = 'another'
    else: observations = {}
    assert outbox.reconcile_page(ack, observations) is None
    assert R4SessionReleaseStore(outbox.path).pending(**identity(original)) == original
    assert outbox.resolved_checkpoint_page(original['server_id'],original['executor_id']) == []


def test_recovery_ack_commit_failure_rolls_back_and_identical_retry_resolves(tmp_path):
    original = request()
    outbox = R4SessionReleaseStore(tmp_path / 'releases.sqlite3')
    outbox.prepare(original)
    ack, observations = evidence(original)
    with sqlite3.connect(outbox.path) as conn:
        conn.execute("CREATE TRIGGER fail_recovery BEFORE UPDATE ON releases BEGIN SELECT RAISE(ABORT,'fault'); END")
    with pytest.raises(ConnectorError, match='JOURNAL_UNAVAILABLE'):
        outbox.reconcile_page(ack, observations)
    assert outbox.pending(**identity(original)) == original
    with sqlite3.connect(outbox.path) as conn:
        assert conn.execute('SELECT recovery FROM releases').fetchone() == (None,)
        conn.execute('DROP TRIGGER fail_recovery')
    R4SessionReleaseStore(outbox.path).reconcile_page(ack, observations)
    assert outbox.pending(**identity(original)) is None


def test_prior_schema_upgrades_without_replacing_pending_request(tmp_path):
    original, path = request(), tmp_path / 'old.sqlite3'
    raw = encode_session_release(original)
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE releases (release_id TEXT PRIMARY KEY,identity TEXT NOT NULL,'
                     'request BLOB NOT NULL,digest TEXT NOT NULL,state TEXT NOT NULL,reply BLOB)')
        conn.execute('INSERT INTO releases VALUES (?,?,?,?,?,?)', (original['release_id'],
            R4SessionReleaseStore._identity(**identity(original)), raw, sha256(raw).hexdigest(), 'PENDING', None))
        conn.execute('PRAGMA user_version=1')
    assert R4SessionReleaseStore(path).pending(**identity(original)) == original
    with sqlite3.connect(path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 6
        assert conn.execute('SELECT request,recovery,event_retired,claim_retired FROM releases').fetchone() == (raw, None, 0, 0)


def test_accepted_event_checkpoint_from_schema_three_still_retires_core_claim(tmp_path):
    original,path=request(),tmp_path/'schema-three.sqlite3'
    raw=encode_session_release(original)
    reply=encode_session_release(session_release_accepted(original))
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE releases (release_id TEXT PRIMARY KEY,identity TEXT NOT NULL,'
                     'request BLOB NOT NULL,digest TEXT NOT NULL,state TEXT NOT NULL,reply BLOB,'
                     'recovery BLOB,recovery_digest TEXT,event_retired INTEGER NOT NULL DEFAULT 0)')
        conn.execute('INSERT INTO releases VALUES (?,?,?,?,?,?,?,?,?)',(
            original['release_id'],R4SessionReleaseStore._identity(**identity(original)),raw,
            sha256(raw).hexdigest(),'ACCEPTED',reply,None,None,1))
        conn.execute('PRAGMA user_version=3')
    store=R4SessionReleaseStore(path)
    assert [item[1] for item in store.accepted_event_page(original['server_id'],original['executor_id'])] == [original]
    with sqlite3.connect(path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 6
        assert conn.execute('SELECT event_retired,claim_retired FROM releases').fetchone() == (1,0)


def test_schema_four_rebuilds_pending_index_for_reconciliation_proofs(tmp_path):
    original=request()
    store=R4SessionReleaseStore(tmp_path/'schema-four.sqlite3')
    store.prepare(original)
    ack,observations=evidence(original)
    store.reconcile_page(ack,observations)
    with sqlite3.connect(store.path) as conn:
        conn.execute('DROP INDEX release_event_retirement')
        conn.execute('CREATE INDEX release_event_retirement ON releases(identity) '
                     "WHERE state='ACCEPTED' AND (event_retired=0 OR claim_retired=0)")
        conn.execute('PRAGMA user_version=4')
    page=R4SessionReleaseStore(store.path).resolved_checkpoint_page(
        original['server_id'],original['executor_id'])
    assert len(page)==1 and page[0][1:3]==(original,original['sequence']+1)
    with sqlite3.connect(store.path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==6
        definition=conn.execute("SELECT sql FROM sqlite_master WHERE name='release_event_retirement'").fetchone()[0]
        assert 'recovery IS NOT NULL' in definition


def test_recovery_pages_do_not_skip_an_unmatched_record_or_rewrite_history(tmp_path):
    original = request()
    outbox = R4SessionReleaseStore(tmp_path / 'releases.sqlite3')
    observations, originals = {}, []
    for index in range(130):
        value = copy.deepcopy(original)
        value['release_id'] = f'release-{index}'
        value['scope']['session_id'] = f'session-{index}'
        outbox.prepare(value)
        ack, facts = evidence(value)
        if index != 64: observations.update(facts)
        originals.append(value)
    after = 0
    for page in range(3):
        after = outbox.reconcile_page(ack, observations, after=after, limit=64)
        assert (after is None) == (page == 2)
    for index, value in enumerate(originals):
        assert outbox.pending(**identity(value)) == (value if index == 64 else None)
