"""Existing-runtime birth reads preserve passivity, cancellation and shutdown ownership."""
import asyncio
from types import SimpleNamespace

import pytest
from nexus_connector_core import CoreError
from nexus_connector_core.models import ProcessBirthEvidence, ProcessBirthRecord, SessionKey


from okto_nexus.bootstrap import runtime_host as candidate
KEY = SessionKey('server', 'executor', 'session')
SELECT = dict(server_id='server', executor_id='executor', session_id='session')
PROOF = ProcessBirthRecord(KEY, 'open_operation', ProcessBirthEvidence(
    platform='win32', pid=123, birth_token='filetime:0000000000000001', containment='owned'))


async def forbidden(*args, **kwargs):
    raise AssertionError('A passive reader attempted composition or historical opening.')


class Journal:
    def __init__(self):
        self.closed = False
        self.reader_active = False

    async def aclose(self):
        assert not self.reader_active, 'Journal closed while a birth reader was active.'
        self.closed = True


class Runtime:
    def __init__(self, journal, *, blocked=False, proof=PROOF, failure=None):
        self.journal, self.proof, self.failure = journal, proof, failure
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.finished, self.shutdown_called = asyncio.Event(), asyncio.Event()
        self.calls = []
        if not blocked:
            self.release.set()

    async def process_birth(self, key):
        self.calls.append(key)
        assert not self.journal.closed
        self.journal.reader_active = True
        self.entered.set()
        try:
            await self.release.wait()
            assert not self.journal.closed
            if self.failure:
                raise self.failure
            return self.proof
        finally:
            self.journal.reader_active = False
            self.finished.set()

    async def shutdown(self, policy):
        self.shutdown_called.set()
        return SimpleNamespace(session_outcomes={KEY: 'released'})


def host(tmp_path):
    value = candidate.EmbeddedRuntimeHost(tmp_path / 'never-created')
    value.acquire = value.with_history = value._compose = value._open_ledger = forbidden
    return value


async def ready(value, *, blocked=False, proof=PROOF, failure=None):
    journal = Journal()
    runtime = Runtime(journal, blocked=blocked, proof=proof, failure=failure)
    async def loaded():
        return runtime, journal
    task = asyncio.create_task(loaded())
    await task
    value._runtime_tasks[('executor', 'session')] = task
    value._selections[('executor', 'session')] = ({}, {}, None, False, 'server')
    return runtime, journal


@pytest.fixture(autouse=True)
def no_creation(monkeypatch):
    monkeypatch.setattr(candidate, 'open_journal', forbidden)
    monkeypatch.setattr(candidate, 'create_runtime', forbidden)


def run(coroutine):
    return asyncio.run(asyncio.wait_for(coroutine, timeout=3))


def test_absent_runtime_does_not_open_a_retained_journal(tmp_path):
    async def scenario():
        value = host(tmp_path)
        with pytest.raises(CoreError) as caught:
            await value.read_existing_process_birth(**SELECT)
        assert caught.value.code == 'SESSION_UNKNOWN'
        assert not value._runtime_tasks and not value._history_tasks
        assert not value.store_dir.exists()
    run(scenario())


def test_pending_composition_is_not_awaited_or_cancelled(tmp_path):
    async def scenario():
        value = host(tmp_path)
        entered, release = asyncio.Event(), asyncio.Event()
        async def composing():
            entered.set()
            await release.wait()
        task = asyncio.create_task(composing())
        value._runtime_tasks[('executor', 'session')] = task
        await entered.wait()
        with pytest.raises(CoreError) as caught:
            await value.read_existing_process_birth(**SELECT)
        assert caught.value.code == 'SESSION_UNKNOWN'
        assert not task.done() and not value._history_tasks
        release.set()
        await task
    run(scenario())


@pytest.mark.parametrize('state', ['failed', 'cancelled'])
def test_failed_or_cancelled_composition_is_refused(tmp_path, state):
    async def scenario():
        value = host(tmp_path)
        async def unavailable():
            if state == 'failed':
                raise RuntimeError('synthetic composition failure')
            raise asyncio.CancelledError
        task = asyncio.create_task(unavailable())
        await asyncio.gather(task, return_exceptions=True)
        value._runtime_tasks[('executor', 'session')] = task
        with pytest.raises(CoreError) as caught:
            await value.read_existing_process_birth(**SELECT)
        assert caught.value.code == 'SESSION_UNKNOWN'
        assert not value._history_tasks
    run(scenario())


@pytest.mark.parametrize('namespace', ['other_server', None])
def test_namespace_must_match_existing_composition(tmp_path, namespace):
    async def scenario():
        value = host(tmp_path)
        runtime, _ = await ready(value)
        if namespace is None:
            value._selections.clear()
        else:
            value._selections[('executor', 'session')] = ({}, {}, None, False, namespace)
        with pytest.raises(CoreError) as caught:
            await value.read_existing_process_birth(**SELECT)
        assert caught.value.code == 'SCOPE_MISMATCH'
        assert runtime.calls == [] and not value._history_tasks
    run(scenario())


@pytest.mark.parametrize('field', ['server_id', 'executor_id', 'session_id'])
@pytest.mark.parametrize('invalid', ['', True, '../other', 'non ascii é'])
def test_invalid_selection_never_accesses_runtime(tmp_path, field, invalid):
    async def scenario():
        value = host(tmp_path)
        runtime, _ = await ready(value)
        with pytest.raises(ValueError, match='Invalid process birth selection'):
            await value.read_existing_process_birth(**(SELECT | {field: invalid}))
        assert runtime.calls == [] and not value._history_tasks
    run(scenario())


@pytest.mark.parametrize('proof', [PROOF, None])
def test_ready_runtime_uses_public_process_birth_and_leaves_store_owned(tmp_path, proof):
    async def scenario():
        value = host(tmp_path)
        runtime, journal = await ready(value, proof=proof)
        assert await value.read_existing_process_birth(**SELECT) is proof
        assert runtime.calls == [KEY]
        assert not value._history_tasks and not journal.closed
        assert ('executor', 'session') in value._runtime_tasks
        assert not value.store_dir.exists()
    run(scenario())


def test_reader_failure_propagates_and_releases_tracking(tmp_path):
    async def scenario():
        value = host(tmp_path)
        failure = RuntimeError('synthetic journal read failure')
        _, journal = await ready(value, failure=failure)
        with pytest.raises(RuntimeError) as caught:
            await value.read_existing_process_birth(**SELECT)
        assert caught.value is failure
        assert not value._history_tasks and not journal.closed
        await value.shutdown()
        assert journal.closed
    run(scenario())


@pytest.mark.parametrize('flag', ['_closing', '_history_closing'])
def test_closing_host_refuses_new_reader(tmp_path, flag):
    async def scenario():
        value = host(tmp_path)
        runtime, _ = await ready(value)
        setattr(value, flag, True)
        with pytest.raises(CoreError) as caught:
            await value.read_existing_process_birth(**SELECT)
        assert caught.value.code == 'RUNTIME_DRAINING'
        assert runtime.calls == [] and not value._history_tasks
    run(scenario())


def test_final_shutdown_waits_for_admitted_reader(tmp_path):
    async def scenario():
        value = host(tmp_path)
        runtime, journal = await ready(value, blocked=True)
        reader = asyncio.create_task(value.read_existing_process_birth(**SELECT))
        await runtime.entered.wait()
        closing = asyncio.create_task(value.shutdown())
        async with value._lock:
            pass
        # Give shutdown one event-loop turn to register its closed admission gate.
        await asyncio.sleep(0)
        assert value._closing and value._history_closing
        assert not journal.closed and not closing.done()
        assert not runtime.shutdown_called.is_set()
        runtime.release.set()
        assert await reader is PROOF
        await closing
        assert journal.closed and runtime.finished.is_set()
        assert not value._history_tasks and not value._runtime_tasks
    run(scenario())


@pytest.mark.parametrize('failure', [False, True])
def test_caller_cancellation_retains_reader_until_final_shutdown(tmp_path, failure):
    async def scenario():
        value = host(tmp_path)
        runtime, journal = await ready(value, blocked=True,
            failure=RuntimeError('synthetic detached reader failure') if failure else None)
        reader = asyncio.create_task(value.read_existing_process_birth(**SELECT))
        await runtime.entered.wait()
        tracked = next(iter(value._history_tasks))
        reader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reader
        assert not tracked.cancelled() and not tracked.done()
        assert tracked in value._history_tasks and not journal.closed
        closing = asyncio.create_task(value.shutdown())
        await asyncio.sleep(0)
        assert not closing.done() and not journal.closed
        runtime.release.set()
        await closing
        assert tracked.done() and not tracked.cancelled()
        assert not value._history_tasks and journal.closed
    run(scenario())


def test_containment_phase_keeps_journal_and_refuses_new_readers(tmp_path):
    async def scenario():
        value = host(tmp_path)
        runtime, journal = await ready(value, blocked=True)
        reader = asyncio.create_task(value.read_existing_process_birth(**SELECT))
        await runtime.entered.wait()
        await value.shutdown(close_stores=False)
        assert runtime.shutdown_called.is_set() and not journal.closed
        assert value._closing and not value._history_closing
        with pytest.raises(CoreError) as caught:
            await value.read_existing_process_birth(**SELECT)
        assert caught.value.code == 'RUNTIME_DRAINING'
        runtime.release.set()
        assert await reader is PROOF
        await value.shutdown()
        assert journal.closed
    run(scenario())


def test_completed_runtime_from_other_loop_is_refused(tmp_path):
    value = host(tmp_path)
    runtime, _ = run(ready(value))
    async def scenario():
        with pytest.raises(CoreError) as caught:
            await value.read_existing_process_birth(**SELECT)
        assert caught.value.code == 'SCOPE_MISMATCH'
        assert runtime.calls == [] and not value._history_tasks
    run(scenario())


def test_cross_loop_refused_before_acquiring_contended_owner_lock(tmp_path):
    value = host(tmp_path)

    async def bind_owner_lock():
        runtime, _ = await ready(value)
        await value._lock.acquire()
        waiter = asyncio.create_task(value._lock.acquire())
        await asyncio.sleep(0)
        assert not waiter.done()
        # A waiting acquire binds asyncio.Lock to this owner loop. Preserve the
        # held/bound lock but clean up its waiter before leaving that loop.
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert value._lock.locked()
        return runtime

    runtime = run(bind_owner_lock())

    async def scenario():
        with pytest.raises(CoreError) as caught:
            await value.read_existing_process_birth(**SELECT)
        assert caught.value.code == 'SCOPE_MISMATCH'
        assert runtime.calls == [] and not value._history_tasks
        assert value._lock.locked()
    run(scenario())
