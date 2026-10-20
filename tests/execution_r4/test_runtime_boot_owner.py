"""Retained automatic boot waits for usable evidence and retries its same intent."""
import asyncio
from types import SimpleNamespace

import pytest

from okto_nexus.bootstrap.runtime_boot_owner import RuntimeBootOwner


class Inventory:
    def __init__(self, ready):
        self.wait_usable_observation = ready.wait
        self.publication = SimpleNamespace(publication_sequence=1)
        self.complete = True
        self.changed = asyncio.Event()

    def initial_observations_complete(self):
        return self.complete

    async def wait_publication_change(self, sequence):
        while self.publication.publication_sequence <= sequence:
            self.changed.clear()
            await self.changed.wait()
        return True


@pytest.mark.asyncio
async def test_boot_failure_retries_with_same_owner_and_clears_failure():
    ready = asyncio.Event()
    deps = object()
    seen = []

    def boot(current, **kwargs):
        seen.append(current)
        if len(seen) == 1:
            raise OSError('storage temporarily unavailable')

    owner = RuntimeBootOwner(deps, Inventory(ready), boot, retry_seconds=.01)
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

    def boot(deps, **kwargs):
        seen.append(True)
        raise OSError('storage unavailable')

    owner = RuntimeBootOwner(None, Inventory(ready), boot)
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


@pytest.mark.asyncio
async def test_later_harness_publication_retries_pending_boot_without_replaying_admitted_endpoint():
    ready = asyncio.Event()
    ready.set()
    inventory = Inventory(ready)
    inventory.complete = False
    seen = []
    def boot(deps, *, exclude_endpoint_ids):
        seen.append(exclude_endpoint_ids)
        if len(seen) == 1:
            return [dict(endpoint_id='codex', state='ACCEPTED'),
                    dict(endpoint_id='pi', state='blocked', retryable=True)]
        assert exclude_endpoint_ids == frozenset({'codex'})
        return [dict(endpoint_id='pi', state='ACCEPTED')]
    owner = RuntimeBootOwner(None, inventory, boot)
    owner.start()
    try:
        async with asyncio.timeout(5):
            while not seen:
                await asyncio.sleep(.01)
        inventory.complete = True
        inventory.publication.publication_sequence += 1
        inventory.changed.set()
        await asyncio.wait_for(owner.wait(), 5)
        assert seen == [frozenset(), frozenset({'codex'})]
        assert owner.failure is None
    finally:
        await owner.aclose()


@pytest.mark.asyncio
async def test_shutdown_wakes_partial_initial_boot_wait():
    ready = asyncio.Event()
    ready.set()
    inventory = Inventory(ready)
    inventory.complete = False
    calls = []
    def boot(deps, **kwargs):
        calls.append(True)
        return []
    owner = RuntimeBootOwner(None, inventory, boot)
    owner.start()
    async with asyncio.timeout(5):
        while not calls:
            await asyncio.sleep(.01)
    await asyncio.wait_for(owner.aclose(), 5)
    assert owner.drained and calls == [True]
