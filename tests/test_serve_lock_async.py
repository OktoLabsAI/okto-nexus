"""Slow diagnostic heartbeat I/O cannot stall HTTP or outlive lock ownership."""
import asyncio
import threading

import pytest

from okto_nexus.adapters.inbound.http.lock import ServeLock


@pytest.mark.asyncio
async def test_slow_heartbeat_keeps_loop_live_and_joins_before_release(tmp_path, monkeypatch):
    lock = ServeLock(tmp_path)
    lock.acquire()
    entered, unblock, finished = threading.Event(), threading.Event(), threading.Event()
    original = lock.heartbeat

    def slow_heartbeat():
        entered.set()
        assert unblock.wait(10), 'test must release its blocked filesystem operation'
        try:
            original()
        finally:
            finished.set()

    monkeypatch.setattr(lock, 'heartbeat', slow_heartbeat)
    task = asyncio.create_task(lock.heartbeat_async())
    try:
        # The deadline also distinguishes a loop-blocking implementation.
        async with asyncio.timeout(3):
            while not entered.is_set():
                await asyncio.sleep(0.001)
        assert not finished.is_set()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert lock.owned
        assert lock.path.exists()
        unblock.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
        assert lock.owned
    finally:
        unblock.set()
        if not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
        lock.release()
    assert not lock.path.exists()


@pytest.mark.asyncio
async def test_async_heartbeat_preserves_changed_generation(tmp_path):
    import json

    lock = ServeLock(tmp_path)
    lock.acquire()
    changed = dict(lock._payload(), generation='different-owner')
    lock.path.write_text(json.dumps(changed), encoding='utf-8')
    before = lock.path.stat().st_mtime_ns
    await lock.heartbeat_async()
    assert lock.path.stat().st_mtime_ns == before
    lock.release()
    assert json.loads(lock.path.read_text(encoding='utf-8')) == changed
