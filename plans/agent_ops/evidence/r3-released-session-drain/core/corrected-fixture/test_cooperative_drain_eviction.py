"""Local eviction evidence discharges only its exact historic claim resource."""
import asyncio
import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from nexus_connector_core import EventCursor, OperationKey, SessionKey, combine_drain_status
from nexus_connector_core.models import CloseOperation, OperationReceipt, RuntimeEvent, ShutdownPolicy, TurnOperation
from nexus_connector_core.runtime import LocalRuntimeCore, _SessionTombstones
from test_cooperative_drain import finish, opened, terminal
from test_cooperative_drain_composition import cleanup, siblings
from test_runtime import FakeFactory, FakeNative


KEY = SessionKey('srv', 'exe', 'session')


async def wait_evicted(runtime, key=KEY):
    async def wait():
        while key in runtime._sessions or any(not task.done() for task in runtime._cleanup_tasks):
            await asyncio.sleep(0)
    await asyncio.wait_for(wait(), 3)


async def completed(runtime, journal, factory, auth, *, ack=True):
    await runtime.submit(TurnOperation('turn', 'session', 'synthetic'), auth)
    cursor = await terminal(runtime, factory.native)
    if ack:
        await runtime.acknowledge_events(cursor, await journal.contiguous_watermark(cursor))


async def close(runtime, auth):
    receipt = await runtime.close(CloseOperation('close', 'session', 'Done', ShutdownPolicy(.01, .01)), auth)
    assert receipt.stage == 'SUCCEEDED'
    await wait_evicted(runtime)
    runtime.begin_drain()


@pytest.mark.asyncio
async def test_normal_close_eviction_drains_without_retiring_history_or_claim(tmp_path):
    runtime, journal, factory, auth, _, _ = await opened(tmp_path)
    try:
        await completed(runtime, journal, factory, auth)
        await close(runtime, auth)
        before = await journal._run(lambda db: (db.total_changes, tuple(db.iterdump())))
        report = await runtime.drain_status()
        assert report['state'] == 'QUIESCENT' and report['quiescent']
        assert report['owned_sessions'] == [] and report['resources'] == []
        assert report['released_sessions'] == [{
            'server_id': 'srv', 'executor_id': 'exe', 'session_id': 'session',
            'opening_operation_id': 'open', 'stream_epoch': 'epoch',
            'session_owner_generation': auth.session_owner_generation}]
        assert runtime.drain_revision() == report['activity_revision']
        assert await journal._run(lambda db: (db.total_changes, tuple(db.iterdump()))) == before
        assert (await journal.drain_snapshot())['claims'][0]['operation_id'] == 'open'
        snapshot = await runtime.inspect(KEY)
        assert snapshot.ownership == 'released' and snapshot.process_state == 'UNKNOWN'
        assert factory.open_count == 1 and [call[0] for call in factory.native.sent] == ['submit']
    finally:
        await finish(runtime, journal)


@pytest.mark.asyncio
async def test_restart_cannot_inherit_process_local_release_proof(tmp_path):
    runtime, journal, factory, auth, _, _ = await opened(tmp_path)
    restarted = None
    try:
        await completed(runtime, journal, factory, auth)
        await close(runtime, auth)
        assert (await runtime.drain_status())['quiescent']
        restarted = LocalRuntimeCore(journal, FakeFactory(), candidates=runtime._candidates,
                                     workspace_roots=runtime._workspace_roots)
        restarted.begin_drain()
        report = await restarted.drain_status()
        assert report['state'] == 'UNKNOWN' and report['released_sessions'] == []
        assert {row['reason'] for row in report['resources']} == {'SESSION_RECONCILIATION_PENDING'}
    finally:
        if restarted is not None:
            await restarted.shutdown(ShutdownPolicy(.01, .01))
        await finish(runtime, journal)


@pytest.mark.asyncio
async def test_eviction_does_not_attest_unjoined_event_producer_or_late_event(tmp_path):
    release = asyncio.Event()

    class LateProducer(FakeNative):
        async def events(self):
            async for event in super().events():
                yield event
            await release.wait()
            yield RuntimeEvent('srv', 'exe', 'session', 'epoch', 0,
                               'tool_activity', 'late-notice', {})

    runtime, journal, factory, auth, _, _ = await opened(tmp_path, native=LateProducer())
    runtime._cleanup_budget_seconds = .01
    binding = runtime._sessions[KEY]
    try:
        await completed(runtime, journal, factory, auth)
        await close(runtime, auth)
        assert not binding.pump.done()
        assert runtime._session_tombstones.released_proof(KEY) is None
        assert (await runtime.drain_status())['state'] == 'UNKNOWN'
        release.set()
        await asyncio.wait_for(binding.pump, 2)
        report = await runtime.drain_status()
        assert {'SESSION_RECONCILIATION_PENDING', 'EVENT_ACK_PENDING'} <= {row['reason'] for row in report['resources']}
        cursor = EventCursor('srv', 'exe', 'session', 'epoch')
        await runtime.acknowledge_events(cursor, await journal.contiguous_watermark(cursor))
        assert (await runtime.drain_status())['state'] == 'UNKNOWN'
    finally:
        release.set()
        await finish(runtime, journal)


@pytest.mark.asyncio
@pytest.mark.parametrize('mismatch', ['opening', 'epoch', 'owner', 'missing_generation', 'ambiguous_epoch', 'no_epoch'])
async def test_release_proof_requires_exact_unambiguous_durable_identity(tmp_path, mismatch):
    runtime, journal, factory, auth, _, _ = await opened(tmp_path)
    try:
        if mismatch != 'no_epoch':
            await completed(runtime, journal, factory, auth)
        await close(runtime, auth)
        if mismatch in {'opening', 'epoch', 'owner'}:
            proof = runtime._session_tombstones.released_proof(KEY)
            field, value = {'opening': ('opening_operation_id', 'other'),
                            'epoch': ('stream_epoch', 'other'),
                            'owner': ('session_owner_generation', 99)}[mismatch]
            runtime._session_tombstones.record(KEY, 'released', replace(proof, **{field: value}))
        elif mismatch == 'missing_generation':
            await journal._run(lambda db: db.execute('DELETE FROM session_open_generations'))
        elif mismatch == 'ambiguous_epoch':
            event = RuntimeEvent('srv', 'exe', 'session', 'other', 1, 'turn_state', 'notice', {})
            await journal.append_event(event)
            await runtime.acknowledge_events(EventCursor('srv', 'exe', 'session', 'other'), 1)
        report = await runtime.drain_status()
        assert report['state'] == 'UNKNOWN' and not report['released_sessions']
        assert 'SESSION_RECONCILIATION_PENDING' in {row['reason'] for row in report['resources']}
    finally:
        await finish(runtime, journal)


@pytest.mark.asyncio
@pytest.mark.parametrize('obligation', ['unacked', 'unresolved', 'late_handle', 'slot_pending', 'producer'])
async def test_release_proof_never_hides_other_obligations(tmp_path, obligation):
    runtime, journal, factory, auth, _, _ = await opened(tmp_path)
    producer = None
    try:
        await completed(runtime, journal, factory, auth, ack=obligation != 'unacked')
        await close(runtime, auth)
        if obligation == 'unresolved':
            key = OperationKey('srv', 'exe', 'uncertain')
            await journal.admit(key, 'digest', 'session', action='turn.submit')
            await journal.mark_possible_effect(key)
            await journal.record_receipt(key, OperationReceipt('uncertain', 'digest', 'OUTCOME_UNKNOWN', True, False, 'session'))
        elif obligation == 'late_handle':
            runtime._late_handles[KEY] = SimpleNamespace(last_state='UNKNOWN')
        elif obligation == 'slot_pending':
            runtime._release_obligations[KEY] = object()
        elif obligation == 'producer':
            producer = asyncio.create_task(asyncio.Event().wait())
            runtime._release_producers.add(producer)
        report = await runtime.drain_status()
        assert not report['quiescent']
        expected = {'unacked': 'EVENT_ACK_PENDING', 'unresolved': 'JOURNAL_OPERATION_PENDING',
                    'late_handle': 'LATE_NATIVE_HANDLE', 'slot_pending': 'OWNERSHIP_RELEASE_PENDING',
                    'producer': 'RELEASE_PRODUCER_PENDING'}[obligation]
        assert expected in {row['reason'] for row in report['resources']}
    finally:
        runtime._late_handles.pop(KEY, None)
        runtime._release_obligations.pop(KEY, None)
        if producer is not None:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)
            runtime._release_producers.discard(producer)
        await finish(runtime, journal)


@pytest.mark.asyncio
async def test_tombstone_change_fences_inflight_read_and_capacity_drops_proof(tmp_path):
    runtime, journal, factory, auth, _, _ = await opened(tmp_path)
    original = journal.drain_snapshot
    try:
        runtime._session_tombstones = _SessionTombstones(1)
        await completed(runtime, journal, factory, auth)
        await close(runtime, auth)
        previous = await runtime.drain_status()
        entered, release = asyncio.Event(), asyncio.Event()

        async def paused():
            facts = await original()
            entered.set()
            await release.wait()
            return facts

        journal.drain_snapshot = paused
        pending = asyncio.create_task(runtime.drain_status())
        await entered.wait()
        runtime._session_tombstones.record(SessionKey('srv', 'exe', 'new'), 'unknown')
        assert runtime._session_tombstones.released_proof(KEY) is None
        assert runtime.drain_revision() != previous['activity_revision']
        release.set()
        report = await pending
        assert report['state'] == 'UNKNOWN'
        assert {'SNAPSHOT_CHANGED', 'SESSION_RECONCILIATION_PENDING'} <= {row['reason'] for row in report['resources']}
    finally:
        journal.drain_snapshot = original
        await finish(runtime, journal)


async def released_sibling(tmp_path, *, ack=True):
    first, second, journal, auth = await siblings(tmp_path)
    key = SessionKey('srv', 'exe', 'session-0')
    event = RuntimeEvent('srv', 'exe', 'session-0', 'epoch-0', 1, 'tool_activity', 'notice', {})
    await journal.append_event(event)
    if ack:
        await first.acknowledge_events(EventCursor('srv', 'exe', 'session-0', 'epoch-0'), 1)
    assert (await first.close(CloseOperation('close-0', 'session-0', 'Done', ShutdownPolicy(.01, .01)), auth)).stage == 'SUCCEEDED'
    await wait_evicted(first, key)
    return first, second, journal


@pytest.mark.asyncio
@pytest.mark.parametrize('ack', [True, False])
async def test_shared_journal_composes_exact_eviction_without_hiding_ack(tmp_path, ack):
    first, second, journal = await released_sibling(tmp_path, ack=ack)
    try:
        reports = [await first.drain_status(), await second.drain_status()]
        assert all(runtime.drain_revision() == report['activity_revision']
                   for runtime, report in zip((first, second), reports))
        result = combine_drain_status(reports)
        assert result['quiescent'] is ack
        assert {row['reason'] for row in result['resources']} == (set() if ack else {'EVENT_ACK_PENDING'})
    finally:
        await cleanup(first, second, journal)


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['epoch', 'owner', 'opening', 'namespace', 'duplicate', 'missing_revision', 'live_owner'])
async def test_shared_release_proof_mismatch_or_multiple_owners_stays_unknown(tmp_path, mutation):
    first, second, journal = await released_sibling(tmp_path)
    try:
        reports = copy.deepcopy([await first.drain_status(), await second.drain_status()])
        proof = reports[0]['released_sessions'][0]
        if mutation == 'duplicate':
            reports.append(copy.deepcopy(reports[0]))
        elif mutation == 'missing_revision':
            reports[0].pop('activity_revision')
        elif mutation == 'live_owner':
            reports[1]['owned_sessions'].append({key: value for key, value in proof.items()
                                                if key != 'session_owner_generation'})
        else:
            field, value = {'epoch': ('stream_epoch', 'other'), 'owner': ('session_owner_generation', 99),
                            'opening': ('opening_operation_id', 'other'), 'namespace': ('server_id', 'other')}[mutation]
            proof[field] = value
        assert combine_drain_status(reports)['state'] == 'UNKNOWN'
    finally:
        await cleanup(first, second, journal)
