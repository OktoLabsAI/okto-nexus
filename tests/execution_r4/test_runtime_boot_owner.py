"""Retained automatic boot waits for usable evidence and retries its same intent."""
import asyncio
from types import SimpleNamespace

import pytest

from okto_nexus.bootstrap.runtime_boot_owner import RuntimeBootOwner


@pytest.mark.asyncio
async def test_boot_failure_retries_with_same_owner_and_clears_failure():
    ready = asyncio.Event()
    deps = object()
    seen = []

    def boot(current):
        seen.append(current)
        if len(seen) == 1:
            raise OSError('storage temporarily unavailable')

    owner = RuntimeBootOwner(deps, SimpleNamespace(wait_usable_observation=ready.wait), boot, retry_seconds=.01)
    owner.start()
    try:
        await asyncio.sleep(0)
        assert not seen and not owner.drained
        ready.set()
        await asyncio.wait_for(owner.wait(), 5)
        assert seen == [deps, deps]
        assert owner.failure is None and owner.drained
    finally:
        await owner.aclose()


@pytest.mark.asyncio
async def test_shutdown_interrupts_retry_wait_without_replaying_boot():
    ready = asyncio.Event()
    ready.set()
    seen = []

    def boot(deps):
        seen.append(True)
        raise OSError('storage unavailable')

    owner = RuntimeBootOwner(None, SimpleNamespace(wait_usable_observation=ready.wait), boot)
    owner.start()
    try:
        async with asyncio.timeout(5):
            while owner.failure is None:
                await asyncio.sleep(.01)
        await asyncio.wait_for(owner.aclose(), 5)
        assert seen == [True] and owner.drained
        assert isinstance(owner.failure, OSError)
    finally:
        await owner.aclose()
