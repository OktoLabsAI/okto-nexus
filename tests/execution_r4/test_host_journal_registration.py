"""The embedded host records physical intent before opening a session journal."""
import asyncio

import pytest
from nexus_connector_core import CoreError, JournalLocation, SessionKey
from okto_nexus.bootstrap import runtime_host
from test_ns07 import _candidate


def options(tmp_path, *, server='server'):
    async def environment(_):
        return {}
    return dict(server_id=server, executor_id='executor', session_id='session',
        candidates={'codex': _candidate()}, workspace_roots={'workspace': str(tmp_path)},
        environment=environment)


@pytest.mark.asyncio
async def test_registration_commits_before_file_creation_and_is_exact(tmp_path, monkeypatch):
    host = runtime_host.EmbeddedRuntimeHost(tmp_path / 'store')
    original, opened = runtime_host.open_journal, []
    async def observe(path):
        record = await (await host._ledger()).journal_location(path.name)
        assert record.location == JournalLocation(path.name, SessionKey('server', 'executor', 'session'))
        assert not path.exists()
        opened.append(record)
        return await original(path)
    monkeypatch.setattr(runtime_host, 'open_journal', observe)
    selected = options(tmp_path)
    try:
        runtime = await host.acquire(**selected)
        assert await host.acquire(**selected) is runtime
        with pytest.raises(RuntimeError, match='changed'):
            await host.acquire(**dict(selected, server_id='other'))
        assert len(opened) == 1
        assert not (await (await host._ledger()).owned_slot_page()).reservations
    finally:
        await host.shutdown()


@pytest.mark.asyncio
async def test_failed_file_open_retains_intent_for_new_host_retry(tmp_path, monkeypatch):
    host = runtime_host.EmbeddedRuntimeHost(tmp_path / 'store')
    original = runtime_host.open_journal
    async def fail(_):
        raise OSError('creation cut')
    monkeypatch.setattr(runtime_host, 'open_journal', fail)
    try:
        with pytest.raises(OSError, match='creation cut'):
            await host.acquire(**options(tmp_path))
        name = host._journal_path('executor', 'session').name
        registered = await (await host._ledger()).journal_location(name)
        assert registered is not None and not (host.store_dir / name).exists()
    finally:
        await host.shutdown()
    monkeypatch.setattr(runtime_host, 'open_journal', original)
    replacement = runtime_host.EmbeddedRuntimeHost(host.store_dir)
    try:
        await replacement.acquire(**options(tmp_path))
        assert await (await replacement._ledger()).journal_location(name) == registered
    finally:
        await replacement.shutdown()


@pytest.mark.asyncio
async def test_scope_conflict_cannot_create_or_retarget_file(tmp_path):
    host = runtime_host.EmbeddedRuntimeHost(tmp_path / 'store')
    path = host._journal_path('executor', 'session')
    try:
        ledger = await host._ledger()
        record, = await ledger.register_journal_locations((JournalLocation(path.name,
            SessionKey('other-server', 'executor', 'session')),))
        with pytest.raises(CoreError, match='PROFILE_DRIFT'):
            await host.acquire(**options(tmp_path))
        assert not path.exists()
        assert await ledger.journal_location(path.name) == record
    finally:
        await host.shutdown()


@pytest.mark.asyncio
async def test_cancelled_observer_keeps_one_owned_composition(tmp_path, monkeypatch):
    host = runtime_host.EmbeddedRuntimeHost(tmp_path / 'store')
    entered, release, calls = asyncio.Event(), asyncio.Event(), []
    original = runtime_host.open_journal
    async def delayed(path):
        calls.append(path)
        assert await (await host._ledger()).journal_location(path.name) is not None
        entered.set()
        await release.wait()
        return await original(path)
    monkeypatch.setattr(runtime_host, 'open_journal', delayed)
    selected = options(tmp_path)
    observer = asyncio.create_task(host.acquire(**selected))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        observer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await observer
        assert not host._runtime_tasks[('executor', 'session')].done()
        release.set()
        await host.acquire(**selected)
        assert len(calls) == 1
    finally:
        release.set()
        await host.shutdown()


@pytest.mark.asyncio
async def test_late_composition_cannot_create_ledger_after_final_shutdown_snapshot(tmp_path, monkeypatch):
    host = runtime_host.EmbeddedRuntimeHost(tmp_path / 'store')
    entered, release = asyncio.Event(), asyncio.Event()
    original = host._compose
    async def delayed(*args):
        entered.set()
        await release.wait()
        return await original(*args)
    monkeypatch.setattr(host, '_compose', delayed)
    observer = asyncio.create_task(host.acquire(**options(tmp_path)))
    closing = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert host._ledger_task is None
        closing = asyncio.create_task(host.shutdown())
        async with asyncio.timeout(5):
            while not host._history_closing:
                await asyncio.sleep(0)
        release.set()
        assert await asyncio.wait_for(closing, 5) == {}
        with pytest.raises(CoreError, match='RUNTIME_DRAINING'):
            await observer
        assert host._ledger_task is None and not host.store_dir.exists()
        assert not host._runtime_tasks and not host._selections
    finally:
        release.set()
        await asyncio.gather(observer, *([closing] if closing is not None else []), return_exceptions=True)
        await host.shutdown()


@pytest.mark.asyncio
async def test_ledger_creation_failure_leaves_no_uncertain_composition(tmp_path, monkeypatch):
    host = runtime_host.EmbeddedRuntimeHost(tmp_path / 'store')
    async def fail():
        raise OSError('ledger construction cut')
    monkeypatch.setattr(host, '_open_ledger', fail)
    with pytest.raises(OSError, match='ledger construction cut'):
        await host.acquire(**options(tmp_path))
    assert await host.shutdown() == {}
    assert not host._runtime_tasks and not host._selections
    assert host.shutdown_resources() == []


@pytest.mark.asyncio
async def test_final_store_fence_cannot_be_reopened_by_containment_only_pass(tmp_path):
    host = runtime_host.EmbeddedRuntimeHost(tmp_path / 'store')
    ledger = await host._ledger()
    try:
        await host.shutdown(close_stores=False)
        assert await host._ledger() is ledger
        await host.shutdown()
        await host.shutdown(close_stores=False)
        with pytest.raises(CoreError, match='RUNTIME_DRAINING'):
            await host._ledger()
        with pytest.raises(CoreError, match='JOURNAL_CLOSED'):
            await ledger.owned_slot_page()
    finally:
        await host.shutdown()
